"""Same-origin patient API. Django owns passwords, sessions and patient data."""
import hashlib
import hmac
import json
import re
import time
import unicodedata
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import HASH_SESSION_KEY, authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.http import FileResponse, Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.csrf import csrf_failure as default_csrf_failure
from django.views.decorators.http import require_GET

from .access import role_for
from .forms import DocumentForm, PatientForm, normalize
from .models import AuditEvent, Document, LoginThrottle, Patient, PortalAccount, PortalRecoveryRequest, SiteActivity


class PortalError(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status


def answer(data, status=200):
    response = JsonResponse(data, status=status)
    response['Cache-Control'] = 'private, no-store'
    response['X-Robots-Tag'] = 'noindex,nofollow'
    if status == 429:
        response['Retry-After'] = '900'
    return response


def csrf_failure(request, reason=''):
    if request.path.startswith('/dash/api/portal/'):
        return answer({'error': 'csrf_rejected'}, 403)
    return default_csrf_failure(request, reason=reason)


def data_body(request, allowed):
    if request.content_type != 'application/json':
        raise PortalError('json_required', 415)
    if len(request.body) > 262144:
        raise PortalError('payload_too_large', 413)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise PortalError('invalid_payload')
    if not isinstance(data, dict) or set(data) - set(allowed):
        raise PortalError('invalid_fields')
    return data


def text(value, maximum, minimum=0):
    if not isinstance(value, str) or len(value) > maximum or len(value.strip()) < minimum or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', value):
        raise PortalError('invalid_fields')
    return value.strip()


def rate(request, purpose, limit, identity=''):
    source = identity or request.headers.get('CF-Connecting-IP') or request.META.get('REMOTE_ADDR', 'unknown')
    key = hashlib.sha256((purpose + '|' + source).encode()).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        bucket, _ = LoginThrottle.objects.get_or_create(key=key, defaults={'expires': now + timedelta(minutes=15)})
        bucket = LoginThrottle.objects.select_for_update().get(pk=bucket.pk)
        if bucket.expires <= now:
            bucket.failures, bucket.expires = 0, now + timedelta(minutes=15)
        if bucket.failures >= limit:
            raise PortalError('try_later', 429)
        bucket.failures += 1
        bucket.save(update_fields=['failures', 'expires'])


def account_for(request, required=False):
    if not request.user.is_authenticated or not request.user.is_active:
        if required:
            raise PortalError('sign_in_required', 401)
        return None
    try:
        account = request.user.portal_account
    except PortalAccount.DoesNotExist:
        if required:
            raise PortalError('patient_account_required', 403)
        return None
    if request.session.get('portal_auth_version') != account.auth_version:
        logout(request)
        if required:
            raise PortalError('sign_in_required', 401)
        return None
    return account


def locked_account(request, account):
    # Keep the same lock order as credential/reset/management changes. Lock only
    # the account, not the nullable joined Patient side of a PostgreSQL outer join.
    user = User.objects.select_for_update(no_key=True).get(pk=account.user_id)
    current = PortalAccount.objects.select_for_update(of=('self',)).select_related('user', 'patient').get(pk=account.pk)
    if not user.is_active or request.session.get('portal_auth_version') != current.auth_version or not constant_time_compare(request.session.get(HASH_SESSION_KEY, ''), user.get_session_auth_hash()):
        raise PortalError('sign_in_required', 401)
    return current


def safe_user(user, account=None):
    return {
        'id': 'clinic:' + str(account.pk) if account else 'clinic-staff:' + str(user.pk),
        'username': user.username, 'email': account.email if account else user.email,
        'display_name': user.get_full_name() or user.username,
        'phone': (account.patient.phone if account.patient_id else account.phone) if account else '',
        'provider': 'clinic', 'email_verified': 0,
        'role': account.site_role if account else 'admin' if role_for(user) == 'manager' else 'member',
        'clinic_role': role_for(user), 'status': 'active' if user.is_active else 'suspended',
        'created_at': int(user.date_joined.timestamp()), 'updated_at': int(account.updated_at.timestamp()) if account else int(user.date_joined.timestamp()),
        'last_login_at': int(user.last_login.timestamp()) if user.last_login else None,
    }


def session_state(request):
    account = account_for(request)
    staff_role = role_for(request.user)
    user = safe_user(request.user, account) if request.user.is_authenticated and (account or staff_role) else None
    manage = bool(user and (staff_role == 'manager' or account and account.site_role == 'admin'))
    return {'user': user, 'csrf_token': get_token(request), 'identity_provider': 'clinic',
            'patient_portal': {'available': True, 'is_patient': bool(account), 'profile_complete': bool(account and account.patient_id),
                               'track_activity': bool(account and account.track_activity), 'share_activity': bool(account and account.share_activity)},
            'capabilities': {'manageUsers': manage, 'manageRoles': False, 'siteStudio': False, 'clinic': bool(user), 'patientPortal': bool(account), 'privateWorkspace': False}}


def check_password(value, user=None):
    if not isinstance(value, str) or len(value) < 12 or len(value.encode()) > 256:
        raise PortalError('password_too_short')
    try:
        validate_password(value, user=user)
    except ValidationError:
        raise PortalError('password_too_short')
    return value


def signup(request):
    data = data_body(request, ['username', 'email', 'display_name', 'phone', 'password'])
    username = unicodedata.normalize('NFKC', text(data.get('username'), 32, 3)).lower()
    if not re.fullmatch(r'[a-z][a-z0-9_-]{2,31}', username) or username in {'admin', 'owner', 'root', 'support', '4mirgr'}:
        raise PortalError('invalid_username')
    email = text(data.get('email'), 254, 3).lower()
    from django.core.validators import validate_email
    try:
        validate_email(email)
    except ValidationError:
        raise PortalError('invalid_email')
    name = text(data.get('display_name'), 100, 1)
    password = check_password(data.get('password'))
    phone = normalize(text(data.get('phone', ''), 24))
    rate(request, 'portal-signup', 8)
    if User.objects.filter(username__iexact=username).exists() or PortalAccount.objects.filter(email=email).exists():
        raise PortalError('registration_unavailable', 409)
    try:
        with transaction.atomic():
            user = User.objects.create_user(username, email=email, password=password, first_name=name)
            account = PortalAccount.objects.create(user=user, email=email, phone=phone)
    except IntegrityError:
        raise PortalError('registration_unavailable', 409)
    login(request, user)
    request.session['portal_auth_version'] = account.auth_version
    request.session.set_expiry(86400)
    AuditEvent.objects.create(actor=user, action='portal.signup', target=str(account.pk))
    return {'user': safe_user(user, account)}


def sign_in(request):
    data = data_body(request, ['identifier', 'password'])
    identifier = unicodedata.normalize('NFKC', text(data.get('identifier'), 254, 1)).casefold()
    password = data.get('password')
    if not isinstance(password, str) or not password or len(password.encode()) > 256:
        raise PortalError('invalid_credentials', 401)
    rate(request, 'portal-login-ip', 30)
    rate(request, 'portal-login-account', 10, identifier)
    if '@' in identifier:
        found = PortalAccount.objects.select_related('user').filter(email=identifier).first()
        username = found.user.username if found else identifier
    else:
        existing = User.objects.filter(username__iexact=identifier).first()
        username = existing.username if existing else identifier
    user = authenticate(request, username=username, password=password)
    if user is None:
        raise PortalError('invalid_credentials', 401)
    account = PortalAccount.objects.filter(user=user).first()
    if not account and not role_for(user):
        raise PortalError('invalid_credentials', 401)
    login(request, user)
    if account:
        request.session['portal_auth_version'] = account.auth_version
    request.session.set_expiry(86400 if account else 1800)
    return {'user': safe_user(user, account)}


def profile_data(account):
    patient = account.patient
    return {'display_name': account.user.get_full_name(), 'first_name': patient.first_name if patient else '',
            'last_name': patient.last_name if patient else '', 'phone': patient.phone if patient else account.phone,
            'reported_history': account.reported_history, 'reported_medications': account.reported_medications,
            'reported_allergies': account.reported_allergies, 'profile_complete': bool(patient)}


def profile(request):
    account = account_for(request, True)
    if request.method == 'GET':
        return {'profile': profile_data(account)}
    data = data_body(request, ['display_name', 'phone', 'first_name', 'last_name', 'reported_history', 'reported_medications', 'reported_allergies'])
    with transaction.atomic():
        account = locked_account(request, account)
        if account.patient_id and 'phone' not in data:
            account.phone = account.patient.phone
        name = text(data.get('display_name', account.user.get_full_name()), 100, 1)
        account.user.first_name, account.user.last_name = name, ''
        account.user.save(update_fields=['first_name', 'last_name'])
        if 'phone' in data:
            phone = text(data['phone'], 30)
            if phone:
                validator = PatientForm({'phone': phone, 'first_name': 'x', 'last_name': 'x'})
                validator.is_valid()
                if 'phone' in validator.errors:
                    raise PortalError('invalid_phone')
                phone = validator.cleaned_data['phone']
            account.phone = phone
        first = text(data.get('first_name', account.patient.first_name if account.patient_id else ''), 100)
        last = text(data.get('last_name', account.patient.last_name if account.patient_id else ''), 100)
        if account.patient_id:
            if not first or not last or not account.phone:
                raise PortalError('invalid_fields')
            Patient.objects.filter(pk=account.patient_id).update(first_name=normalize(first), last_name=normalize(last), phone=account.phone)
        elif first and last and account.phone:
            # Never match an existing record using a self-declared phone/email/ID.
            account.patient = Patient.objects.create(first_name=normalize(first), last_name=normalize(last), phone=account.phone)
        for key, maximum in [('reported_history', 10000), ('reported_medications', 5000), ('reported_allergies', 5000)]:
            if key in data:
                setattr(account, key, text(data[key], maximum))
        account.save()
        AuditEvent.objects.create(actor=request.user, action='portal.profile', target=str(account.pk))
    account.refresh_from_db()
    return {'profile': profile_data(account), 'user': safe_user(account.user, account)}


def password_change(request):
    account = account_for(request, True)
    data = data_body(request, ['current_password', 'password'])
    rate(request, 'portal-password', 8, str(account.pk))
    new_password = check_password(data.get('password'), request.user)
    with transaction.atomic():
        account = locked_account(request, account)
        user = account.user
        if not user.check_password(data.get('current_password', '')):
            raise PortalError('invalid_credentials', 401)
        user.set_password(new_password); user.save(update_fields=['password'])
        PortalAccount.objects.filter(pk=account.pk).update(auth_version=F('auth_version') + 1)
        account.refresh_from_db()
        update_session_auth_hash(request, user)
        request.session['portal_auth_version'] = account.auth_version
    return {'changed': True}


def privacy(request):
    account = account_for(request, True)
    if request.method == 'POST':
        data = data_body(request, ['track_activity', 'share_activity'])
        if set(data) != {'track_activity', 'share_activity'} or any(type(value) is not bool for value in data.values()):
            raise PortalError('invalid_fields')
        with transaction.atomic():
            account = locked_account(request, account)
            account.track_activity, account.share_activity = data['track_activity'], data['share_activity'] and data['track_activity']
            account.consent_updated_at = timezone.now(); account.save()
            if not account.track_activity:
                account.site_activity.all().delete()
    return {'privacy': {'track_activity': account.track_activity, 'share_activity': account.share_activity, 'retention_days': 90}}


def activity(request):
    account = account_for(request, True)
    if request.method == 'POST':
        data = data_body(request, ['kind', 'value', 'category', 'action'])
        if data.get('action') == 'erase' and set(data) == {'action'}:
            account.site_activity.all().delete()
            return {'erased': True}
        if data.get('kind') not in {'search', 'article_open'}:
            raise PortalError('invalid_fields')
        value = unicodedata.normalize('NFKC', normalize(text(data.get('value'), 160, 1)))
        category = normalize(text(data.get('category', ''), 100))
        # Do not store personal identifiers, URL fragments or contact details as search history.
        number_like = re.sub(r'[\s()+./‐‑‒–—−-]', '', value)
        domain_like = re.search(r'(?<!\w)(?:[\w-]+\.)+(?:[^\W\d_]{2,}|xn--[a-z0-9-]+)(?=[/:\s]|$)', value, re.I)
        if re.search(r'\d{6,}', number_like) or domain_like or re.search(r'@|https?://|www\.|[?#=&]', value, re.I):
            return {'recorded': False}
        if data['kind'] == 'article_open' and not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', value):
            raise PortalError('invalid_fields')
        rate(request, 'portal-activity', 120, str(account.pk))
        with transaction.atomic():
            account = locked_account(request, account)
            if not account.track_activity:
                return {'recorded': False}
            account.site_activity.filter(day__lt=timezone.localdate() - timedelta(days=90)).delete()
            if account.site_activity.count() >= 1000:
                return {'recorded': False}
            event, created = SiteActivity.objects.get_or_create(account=account, kind=data['kind'], value=value, day=timezone.localdate(), defaults={'category': category})
            if not created:
                SiteActivity.objects.filter(pk=event.pk, count__lt=1000).update(count=F('count') + 1, updated_at=timezone.now())
        return {'recorded': True}
    account.site_activity.filter(day__lt=timezone.localdate() - timedelta(days=90)).delete()
    return {'events': list(account.site_activity.order_by('-updated_at').values('kind', 'value', 'category', 'count', 'day')[:100]), 'topics': list(account.site_activity.exclude(category='').values('category').annotate(total=Sum('count')).order_by('-total')[:10])}


def document_data(document):
    return {'id': str(document.pk), 'title': document.title, 'category': document.category,
            'created_at': document.created_at.isoformat(), 'download_url': f'/dash/api/portal/documents/{document.pk}/download'}


def documents(request):
    account = account_for(request, True)
    if request.method == 'GET':
        return {'documents': [document_data(d) for d in Document.objects.filter(patient_id=account.patient_id)[:100]] if account.patient_id else []}
    if not account.patient_id:
        raise PortalError('profile_incomplete')
    rate(request, 'portal-upload', 15, str(account.pk))
    if set(request.POST) - {'title', 'category'} or set(request.FILES) != {'file'}:
        raise PortalError('invalid_fields')
    file = request.FILES['file']
    if file.size > 5 * 1024 * 1024:
        raise PortalError('invalid_file')
    form = DocumentForm(request.POST, request.FILES)
    if not form.is_valid():
        raise PortalError('invalid_file')
    suffix = Path(file.name).suffix.lower()
    if suffix in {'.jpg', '.jpeg', '.png'}:
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(file) as image:
                if image.width * image.height > 25000000 or image.format not in {'PNG', 'JPEG'}:
                    raise PortalError('invalid_file')
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise PortalError('invalid_file')
        finally:
            file.seek(0)
    else:
        file.seek(max(0, file.size - 1024)); tail = file.read(); file.seek(0)
        if b'%%EOF' not in tail:
            raise PortalError('invalid_file')
    document = form.save(commit=False); document.patient_id = account.patient_id; document.uploaded_by = request.user
    try:
        with transaction.atomic():
            current = locked_account(request, account)
            if not current.patient_id or Document.objects.filter(patient_id=current.patient_id).count() >= 100:
                raise PortalError('document_limit')
            document.patient_id = current.patient_id
            document.save()
            AuditEvent.objects.create(actor=request.user, action='portal.document_upload', target=str(document.pk))
    except Exception:
        if document.file.name and document.file._committed:
            document.file.delete(save=False)
        raise
    return {'document': document_data(document)}


@require_GET
def document_download(request, pk):
    try:
        account = account_for(request, True)
    except PortalError as error:
        return answer({'error': error.code}, error.status)
    document = Document.objects.filter(pk=pk, patient_id=account.patient_id).first() if account.patient_id else None
    if not document:
        raise Http404
    AuditEvent.objects.create(actor=request.user, action='portal.document_download', target=str(document.pk))
    return FileResponse(document.file.open('rb'), as_attachment=True, filename='medical-document' + Path(document.file.name).suffix.lower(), content_type='application/octet-stream')


def verified_owner(request):
    key = getattr(settings, 'CLINIC_PROXY_KEY', '')
    actor, stamp = request.headers.get('X-Website-Owner', ''), request.headers.get('X-Website-Timestamp', '')
    if actor != 'github:208800626' or len(key) < 32 or not re.fullmatch(r'[0-9]{10,11}', stamp) or abs(time.time() - int(stamp)) > 30:
        return False
    message = '\n'.join([stamp, request.method, request.get_full_path(), hashlib.sha256(request.body).hexdigest(), actor])
    expected = hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()
    return constant_time_compare(request.headers.get('X-Website-Signature', ''), expected)


class PortalResetTokens(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return super()._make_hash_value(user, timestamp) + str(user.portal_account.auth_version)


reset_tokens = PortalResetTokens()


def recovery(request):
    data = data_body(request, ['email']); email = text(data.get('email'), 254, 3).lower()
    rate(request, 'portal-recovery-ip', 5); rate(request, 'portal-recovery-account', 2, email)
    account = PortalAccount.objects.filter(email=email, user__is_active=True).first()
    if account:
        PortalRecoveryRequest.objects.create(account=account)
    return {'requested': True}


def reset_password(request):
    data = data_body(request, ['token', 'password'])
    raw = text(data.get('token'), 256, 1); parts = raw.split('.', 1)
    if len(parts) != 2:
        raise PortalError('reset_link_invalid')
    rate(request, 'portal-reset', 8)
    try:
        account = PortalAccount.objects.select_related('user').get(pk=parts[0], user__is_active=True)
    except (PortalAccount.DoesNotExist, ValidationError):
        raise PortalError('reset_link_invalid')
    new_password = check_password(data.get('password'), account.user)
    with transaction.atomic():
        user = User.objects.select_for_update(no_key=True).get(pk=account.user_id)
        if not reset_tokens.check_token(user, parts[1]):
            raise PortalError('reset_link_invalid')
        user.set_password(new_password); user.save(update_fields=['password'])
        PortalAccount.objects.filter(pk=account.pk).update(auth_version=F('auth_version') + 1)
        PortalRecoveryRequest.objects.filter(account=account, resolved_at=None).update(resolved_at=timezone.now())
    return {'reset': True}


def directory(request, target=None):
    owner = verified_owner(request)
    account = account_for(request)
    if not owner and not (role_for(request.user) == 'manager' or account and account.site_role == 'admin'):
        raise PortalError('permission_denied', 403)
    if request.method == 'GET' and target is None:
        search = request.GET.get('search', '')[:100]
        records = PortalAccount.objects.select_related('user', 'patient').filter(Q(user__username__icontains=search) | Q(user__first_name__icontains=search) | Q(email__icontains=search))
        role, status = request.GET.get('role', ''), request.GET.get('status', '')
        if role:
            records = records.filter(site_role=role)
        if status:
            records = records.filter(user__is_active=status == 'active')
        page = Paginator(records.order_by('-created_at'), 25).get_page(request.GET.get('page', 1))
        total = PortalAccount.objects.count(); active = PortalAccount.objects.filter(user__is_active=True).count()
        requests = PortalRecoveryRequest.objects.select_related('account__user').filter(resolved_at=None).order_by('-created_at')[:25]
        return {'users': [safe_user(a.user, a) for a in page], 'page': page.number, 'pages': page.paginator.num_pages, 'total': page.paginator.count,
                'stats': {'total': total, 'active': active, 'suspended': total-active, 'administrators': PortalAccount.objects.filter(site_role='admin').count()},
                'recovery_requests': [{'id': r.pk, 'created_at': int(r.created_at.timestamp()), 'user_id': 'clinic:'+str(r.account_id), 'username': r.account.user.username, 'display_name': r.account.user.get_full_name(), 'email': r.account.email} for r in requests]}
    if request.method != 'POST' or not owner:
        raise PortalError('permission_denied', 403)
    data = data_body(request, ['role', 'status', 'display_name', 'phone', 'action'])
    if not target or not target.startswith('clinic:'):
        raise PortalError('protected_user', 403)
    try:
        account = PortalAccount.objects.select_related('user', 'patient').get(pk=target[7:])
    except (PortalAccount.DoesNotExist, ValidationError):
        raise PortalError('user_not_found', 404)
    if role_for(account.user) or account.user.is_staff or account.user.is_superuser:
        raise PortalError('protected_user', 403)
    if data.get('action') == 'reset-link':
        if not account.user.is_active:
            raise PortalError('reset_not_available')
        token = str(account.pk) + '.' + reset_tokens.make_token(account.user)
        return {'reset_url': settings.CLINIC_SITE + '/account/#reset/' + token, 'expires_in': settings.PASSWORD_RESET_TIMEOUT}
    if data.get('action') == 'revoke-sessions':
        PortalAccount.objects.filter(pk=account.pk).update(auth_version=F('auth_version') + 1)
        return {'revoked': True}
    if data.get('action') is not None or data.get('role', account.site_role) not in {'member', 'admin'} or data.get('status', 'active') not in {'active', 'suspended'}:
        raise PortalError('invalid_fields')
    with transaction.atomic():
        User.objects.select_for_update(no_key=True).get(pk=account.user_id)
        account = PortalAccount.objects.select_for_update(of=('self',)).select_related('user').get(pk=account.pk)
        account.site_role = data.get('role', account.site_role); account.auth_version += 1
        account.user.is_active = data.get('status', 'active' if account.user.is_active else 'suspended') == 'active'
        if 'display_name' in data:
            account.user.first_name = text(data['display_name'], 100, 1); account.user.last_name = ''
        if 'phone' in data:
            phone = text(data['phone'], 30)
            if phone:
                validator = PatientForm({'phone':phone, 'first_name':'x', 'last_name':'x'}); validator.is_valid()
                if 'phone' in validator.errors:
                    raise PortalError('invalid_phone')
                phone = validator.cleaned_data['phone']
            if account.patient_id and not phone:
                raise PortalError('invalid_phone')
            account.phone = phone
            if account.patient_id:
                Patient.objects.filter(pk=account.patient_id).update(phone=phone)
        account.user.save(update_fields=['is_active', 'first_name', 'last_name']); account.save()
        AuditEvent.objects.create(action='portal.user_updated', target=str(account.pk))
    return {'user': safe_user(account.user, account)}


def endpoint(request, route):
    try:
        if request.method not in {'GET', 'POST'}:
            raise PortalError('method_not_allowed', 405)
        if route == 'session' and request.method == 'GET':
            return answer(session_state(request))
        if route == 'admin/users' or route.startswith('admin/users/'):
            return answer(directory(request, route.removeprefix('admin/users/') if route.startswith('admin/users/') else None))
        actions = {'signup': signup, 'login': sign_in, 'profile': profile, 'password': password_change, 'privacy': privacy, 'activity': activity, 'documents': documents, 'recovery': recovery, 'reset-password': reset_password}
        if route == 'logout' and request.method == 'POST':
            data_body(request, []); logout(request); return answer({'signed_out': True})
        if route not in actions or request.method == 'GET' and route not in {'profile', 'privacy', 'activity', 'documents'}:
            raise PortalError('not_found', 404)
        return answer(actions[route](request), 201 if route == 'signup' or route == 'documents' and request.method == 'POST' else 200)
    except PortalError as error:
        return answer({'error': error.code}, error.status)


@require_GET
def patient_home(request):
    try:
        account_for(request, True)
    except PortalError as error:
        if error.status == 401:
            return redirect('/account/?next=%2Fdash%2Fportal%2F')
        return answer({'error': error.code}, error.status)
    return render(request, 'clinic/portal.html')
