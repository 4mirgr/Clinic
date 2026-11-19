"""Optional same-origin identity bridge; never links patients by email or ID."""
import re
import uuid
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.models import AnonymousUser, Group, User
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import PortalAccount, SharedIdentity

ISSUER = 'https://upwbktvnybsjugdegjji.supabase.co/auth/v1'
SESSION_URL = 'https://drgerami-md.ir/api/account/session'
LOGIN_URL = '/pages/account.html'


class SharedIdentityError(Exception):
    def __init__(self, code, status=401):
        self.code, self.status = code, status


def verified_account(token):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,3800}', token):
        raise SharedIdentityError('shared_sign_in_required')
    try:
        response = requests.get(SESSION_URL, headers={
            'Cookie': '__Host-gerami-access=' + token, 'Accept': 'application/json',
            'Cache-Control': 'no-store',
        }, timeout=(3, 10), allow_redirects=False)
        if response.status_code == 401:
            raise SharedIdentityError('shared_sign_in_required')
        if response.status_code != 200 or len(response.content) > 16384:
            raise SharedIdentityError('shared_identity_unavailable', 503)
        value = response.json()
        account = value.get('account') or {}
        uuid.UUID(account.get('id', ''))
        started = parse_datetime(account.get('sessionStartedAt', ''))
        if value.get('authenticated') is not True or account.get('role') not in {'admin','secretary','user'} or not started or timezone.is_naive(started):
            raise ValueError('Invalid verified identity')
        if not isinstance(account.get('email'), str) or not account['email'] or len(account['email']) > 254:
            raise ValueError('Invalid verified email')
        return account, started
    except SharedIdentityError:
        raise
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        raise SharedIdentityError('shared_identity_unavailable', 503) from None


def resolve_user(account, started):
    subject = uuid.UUID(account['id'])
    with transaction.atomic():
        identity = SharedIdentity.objects.select_for_update().select_related('user').filter(issuer=ISSUER, subject=subject).first()
        email = account['email'].strip().lower()
        if identity is None:
            # An existing local email requires deliberate verified migration.
            # It must never implicitly attach a medical record or staff account.
            if PortalAccount.objects.filter(email__iexact=email).exists() or User.objects.filter(email__iexact=email).exists():
                raise SharedIdentityError('explicit_account_link_required', 409)
            user = User(username='shared_' + uuid.uuid4().hex, email=email)
            user.set_unusable_password()
            user.save()
            portal = PortalAccount.objects.create(user=user, email=email)
            identity = SharedIdentity.objects.create(issuer=ISSUER, subject=subject, user=user, auth_version=portal.auth_version)
        else:
            user = identity.user
            portal = PortalAccount.objects.select_for_update().get(user=user)
        if not user.is_active or user.is_superuser or user.is_staff:
            raise SharedIdentityError('account_inactive', 403)
        if identity.auth_version != portal.auth_version:
            identity.auth_version = portal.auth_version
            identity.revoked_before = timezone.now()
            identity.save(update_fields=['auth_version','revoked_before'])
        # Persist a changed revocation boundary before rejecting below. Raising
        # inside this transaction would roll it back and allow repeat bypasses.
        revoked = bool(identity.revoked_before and started <= identity.revoked_before)
        if not revoked:
            user.first_name = str(account.get('name') or account.get('username') or '')[:150]
            user.email = email
            user.save(update_fields=['first_name','email'])
            portal.site_role = 'admin' if account['role'] == 'admin' else 'member'
            if portal.email != email and PortalAccount.objects.exclude(pk=portal.pk).filter(email__iexact=email).exists():
                raise SharedIdentityError('explicit_account_link_required', 409)
            portal.email = email
            portal.save(update_fields=['site_role','email','updated_at'])
            for name, role in [('clinic_manager','admin'),('clinic_secretary','secretary')]:
                group, _ = Group.objects.get_or_create(name=name)
                if account['role'] == role:
                    user.groups.add(group)
                else:
                    user.groups.remove(group)
    if revoked:
        raise SharedIdentityError('fresh_shared_sign_in_required')
    return user, portal


class SharedIdentityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, 'SHARED_AUTH_ENABLED', False) or not (request.path == '/dash' or request.path.startswith('/dash/')):
            return self.get_response(request)
        entry = LOGIN_URL + '?' + urlencode({'next': '/dash/portal/' if request.path.startswith('/dash/portal') else '/dash/'})
        credential_routes = ('/dash/api/portal/login','/dash/api/portal/signup','/dash/api/portal/password','/dash/api/portal/recovery','/dash/api/portal/reset-password','/dash/api/portal/logout')
        if request.path in credential_routes:
            return JsonResponse({'error':'shared_sign_in_required','account_url':LOGIN_URL}, status=409)
        if request.path == '/dash/logout/':
            # Shared logout must revoke the provider session, not only Django.
            return redirect(LOGIN_URL + '?logout=1')
        if request.path.startswith('/dash/login') or request.path.startswith('/dash/account/'):
            return redirect(entry)
        token = request.COOKIES.get('__Host-gerami-access', '')
        if not token:
            if request.user.is_authenticated:
                logout(request)
            request.user = AnonymousUser()
            return self.get_response(request)
        try:
            account, started = verified_account(token)
            try:
                user, portal = resolve_user(account, started)
            except IntegrityError:
                # A simultaneous first request may have completed the binding.
                # Retry the lookup once; no email-based linking is introduced.
                try:
                    user, portal = resolve_user(account, started)
                except IntegrityError:
                    raise SharedIdentityError('explicit_account_link_required',409) from None
            if not request.user.is_authenticated or request.user.pk != user.pk:
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            request.user = user
            request.session['portal_auth_version'] = portal.auth_version
            return self.get_response(request)
        except SharedIdentityError as error:
            if error.status == 401:
                if request.user.is_authenticated:
                    logout(request)
                return redirect(entry+('&reauth=1' if error.code=='fresh_shared_sign_in_required' else ''))
            return JsonResponse({'error':error.code}, status=error.status)
