"""Opt-in only. No campaigns, open tracking or patient-data export."""
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.models import User
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from clinic.models import PortalAccount
from clinic.portal_api import PortalError, account_for, data_body, locked_account, rate
from .models import Subscription

CONSENT_VERSION = 'education-email-v1'


def available():
    origin = urlsplit(settings.NEWSLETTER_SITE_ORIGIN)
    try:
        validate_email(settings.NEWSLETTER_FROM_EMAIL)
    except ValidationError:
        return False
    backend = settings.EMAIL_BACKEND
    transport = backend == 'django.core.mail.backends.smtp.EmailBackend' and bool(settings.EMAIL_HOST) and settings.EMAIL_USE_TLS
    local_test = not settings.PRODUCTION and backend == 'django.core.mail.backends.locmem.EmailBackend'
    return bool(settings.NEWSLETTER_ENABLED and (transport or local_test) and origin.scheme == 'https' and origin.netloc
                and not origin.username and not origin.password and origin.path in ('', '/') and not origin.query and not origin.fragment)


def state(subscription=None):
    return {'newsletter': {'status': subscription.status if subscription else 'unsubscribed',
                          'delivery_available': available(), 'consent_version': CONSENT_VERSION}}


def stop(subscription):
    subscription.status = 'unsubscribed'
    subscription.confirmation_hash = None
    subscription.confirmation_email = ''
    subscription.confirmation_expires_at = None
    subscription.unsubscribed_at = timezone.now()
    subscription.save()


def preferences(request):
    account = account_for(request, True)
    if request.method == 'GET':
        return state(Subscription.objects.filter(account=account).first())
    data = data_body(request, ['subscribe'])
    if type(data.get('subscribe')) is not bool:
        raise PortalError('invalid_fields')
    if data['subscribe'] and not available():
        raise PortalError('newsletter_unavailable', 503)
    if data['subscribe']:
        rate(request, 'newsletter-opt-in', 3, str(account.pk))
    token = None
    with transaction.atomic():
        account = locked_account(request, account)
        subscription, _ = Subscription.objects.get_or_create(account=account)
        subscription = Subscription.objects.select_for_update().get(pk=subscription.pk)
        if not data['subscribe']:
            stop(subscription)
        elif subscription.status != 'active' or subscription.confirmed_email != account.email:
            token = secrets.token_urlsafe(32)
            subscription.status = 'pending'
            subscription.confirmation_hash = hashlib.sha256(token.encode()).hexdigest()
            subscription.confirmation_email = account.email
            subscription.confirmation_expires_at = timezone.now() + timedelta(hours=24)
            subscription.requested_at = timezone.now()
            subscription.consent_version = CONSENT_VERSION
            subscription.save()
    if token:
        origin = settings.NEWSLETTER_SITE_ORIGIN.rstrip('/')
        text = ('درخواست عضویت در خبرنامهٔ آموزشی دکتر گرامی\n\n'
                'برای تأیید دریافت ایمیل‌های آموزشی، پیوند زیر را باز کنید و دکمهٔ تأیید را بزنید. اعتبار پیوند ۲۴ ساعت است.\n'
                f'{origin}/newsletter/#confirm={token}\n\n'
                'عضویت اختیاری است و به دریافت خدمات یا تکمیل پروندهٔ پزشکی وابسته نیست. '
                'اگر درخواست نداده‌اید، این ایمیل را نادیده بگیرید؛ عضویت فعال نخواهد شد. '
                'در هر زمان از بخش خبرنامهٔ حساب خود می‌توانید لغو عضویت کنید.')
        message = EmailMultiAlternatives('تأیید عضویت خبرنامهٔ آموزشی', text, settings.NEWSLETTER_FROM_EMAIL, [account.email])
        try:
            sent = message.send(fail_silently=False)
        except Exception:
            # Do not log addresses, confirmation links, credentials or provider messages.
            raise PortalError('newsletter_delivery_failed', 503) from None
        if sent != 1:
            raise PortalError('newsletter_delivery_failed', 503)
    return state(subscription)


def confirm(request):
    data = data_body(request, ['token'])
    token = data.get('token')
    if not isinstance(token, str) or not 20 <= len(token) <= 128:
        raise PortalError('newsletter_link_invalid')
    rate(request, 'newsletter-confirm', 20)
    digest = hashlib.sha256(token.encode()).hexdigest()
    sub = Subscription.objects.filter(confirmation_hash=digest).first()
    if not sub:
        raise PortalError('newsletter_link_invalid')
    with transaction.atomic():
        user = User.objects.select_for_update(no_key=True).get(pk=sub.account.user_id)
        account = PortalAccount.objects.select_for_update(of=('self',)).get(pk=sub.account_id)
        sub = Subscription.objects.select_for_update().get(pk=sub.pk)
        if (not user.is_active or sub.status != 'pending' or sub.confirmation_hash != digest
                or not sub.confirmation_expires_at or sub.confirmation_expires_at <= timezone.now()
                or sub.confirmation_email != account.email):
            raise PortalError('newsletter_link_invalid')
        sub.status = 'active'
        sub.confirmed_email = account.email
        sub.confirmed_at = timezone.now()
        sub.confirmation_hash = None
        sub.confirmation_email = ''
        sub.confirmation_expires_at = None
        sub.save()
    return state(sub)


def unsubscribe_token(subscription):
    # This bearer proof only stops educational email; it never authenticates a user.
    return signing.dumps(str(subscription.pk), salt='newsletter-unsubscribe')


def unsubscribe(request):
    data = data_body(request, ['token'])
    token = data.get('token')
    if not isinstance(token, str) or len(token) > 256:
        raise PortalError('newsletter_link_invalid')
    try:
        ident = signing.loads(token, salt='newsletter-unsubscribe')
        sub = Subscription.objects.get(pk=ident)
    except (signing.BadSignature, Subscription.DoesNotExist, ValidationError, ValueError, TypeError):
        raise PortalError('newsletter_link_invalid') from None
    with transaction.atomic():
        sub = Subscription.objects.select_for_update().get(pk=sub.pk)
        stop(sub)
    return state(sub)


def statistics(request):
    from clinic.portal_api import verified_owner
    if not verified_owner(request):
        raise PortalError('permission_denied', 403)
    from django.db.models import Count
    counts = {row['status']: row['total'] for row in Subscription.objects.values('status').annotate(total=Count('pk'))}
    return {'newsletter': {'delivery_available': available(), 'counts': {
        key: counts.get(key, 0) for key in ('pending', 'active', 'unsubscribed')}, 'campaigns_enabled': False}}
