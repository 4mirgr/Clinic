"""Consent-aware reminder planning and bounded external delivery.

Web requests never deliver. An operator runs the explicit dispatch command.
No medical text, patient name, identifiers or token-bearing links leave here.
"""
import hashlib
import re
import smtplib
from datetime import datetime, time, timedelta
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from .communication_models import CHANNELS, ContactPreference, PatientNotification
from .access import role_for
from .jalali import TZ, today_tehran
from .models import AdviceDelivery, AdvicePacket, Appointment, PortalAccount, Visit

PREFERENCE_FIELDS = ('email_opt_in', 'telegram_opt_in', 'whatsapp_opt_in', 'appointment_reminders', 'followup_reminders', 'advice_notifications')
KIND_PREFERENCE = {'appointment': 'appointment_reminders', 'followup': 'followup_reminders', 'advice': 'advice_notifications'}
MAX_ATTEMPTS = 3


def setting(name, default=''):
    return getattr(settings, name, default)


def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def portal_url():
    url = setting('COMMUNICATION_PORTAL_URL', 'https://drgerami-md.ir/dash/portal/')
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        return ''
    return url


def readiness(channel):
    enabled = bool(setting('COMMUNICATIONS_ENABLED', False))
    prefix = '' if enabled else 'ارسال خودکار خاموش است. '
    if not portal_url():
        return False, 'نشانی امن پرتال تنظیم نشده است.'
    if channel == 'email':
        ready = (setting('EMAIL_BACKEND') == 'django.core.mail.backends.smtp.EmailBackend'
                 and bool(setting('EMAIL_HOST')) and bool(setting('DEFAULT_FROM_EMAIL')))
        return ready and enabled, prefix + ('SMTP و نشانی فرستنده باید تنظیم شوند.' if not ready else 'تنظیمات موجود است؛ اتصال زنده باید آزموده شود.')
    if channel == 'telegram':
        ready = bool(setting('TELEGRAM_BOT_TOKEN'))
        return ready and enabled, prefix + ('توکن ربات تلگرام تنظیم نشده است.' if not ready else 'توکن موجود است؛ بیمار باید ربات را شروع کرده باشد.')
    if channel == 'whatsapp':
        ready = all(setting(key) for key in ('WHATSAPP_ACCESS_TOKEN', 'WHATSAPP_PHONE_NUMBER_ID', 'WHATSAPP_TEMPLATE_NAME', 'WHATSAPP_TEMPLATE_LANGUAGE', 'WHATSAPP_API_VERSION'))
        ready = bool(ready and re.fullmatch(r'v[0-9]+\.[0-9]+', setting('WHATSAPP_API_VERSION')) and re.fullmatch(r'[0-9]+', setting('WHATSAPP_PHONE_NUMBER_ID')))
        return ready and enabled, prefix + ('تنظیمات WhatsApp Business و قالب تأییدشده لازم است.' if not ready else 'تنظیمات موجود است؛ تأیید قالب و اتصال زنده هنوز باید بررسی شود.')
    return False, 'کانال ناشناخته است.'


def whatsapp_phone(account):
    phone = account.patient.phone if account.patient_id else ''
    if re.fullmatch(r'09[0-9]{9}', phone):
        return '98' + phone[1:]
    return ''


def telegram_link_available():
    username = setting('TELEGRAM_BOT_USERNAME')
    return bool(setting('TELEGRAM_BOT_TOKEN') and len(setting('TELEGRAM_WEBHOOK_SECRET')) >= 32
                and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', username)
                and username.casefold().endswith('bot'))


def destination(account, preference, channel):
    if channel == 'email' and preference.verified_email.casefold() == account.email.casefold():
        return account.email
    if channel == 'whatsapp' and preference.verified_whatsapp == whatsapp_phone(account):
        return preference.verified_whatsapp
    if channel == 'telegram' and re.fullmatch(r'[1-9][0-9]{3,19}', preference.verified_telegram):
        return preference.verified_telegram
    return ''


def preferences_data(account):
    preference, _ = ContactPreference.objects.get_or_create(account=account)
    channels = []
    for key, label in CHANNELS:
        configured, reason = readiness(key)
        verified = bool(destination(account, preference, key))
        channels.append({'key': key, 'label': label, 'configured': configured, 'reason': reason,
                         'verified': verified, 'enabled': bool(configured and verified and getattr(preference, key + '_opt_in'))})
    return {'preferences': {field: getattr(preference, field) for field in PREFERENCE_FIELDS}, 'channels': channels, 'portal_url': portal_url(), 'telegram_link_available': telegram_link_available()}


def source(kind, source_id):
    """Return current patient/version for revalidation; never send source text."""
    if kind == 'appointment':
        obj = Appointment.objects.filter(pk=source_id, status='confirmed').first()
        return (obj.patient_id, digest(f'{obj.starts_at.isoformat()}:{obj.ends_at.isoformat()}')) if obj else None
    if kind == 'followup':
        obj = Visit.objects.filter(pk=source_id, follow_up_done=False, follow_up_on__isnull=False).first()
        return (obj.patient_id, digest(obj.follow_up_on.isoformat())) if obj else None
    if kind == 'advice':
        model, pk = source_id.split(':', 1)
        obj = (AdvicePacket if model == 'packet' else AdviceDelivery).objects.filter(pk=pk).first()
        return (obj.patient_id, digest(obj.created_at.isoformat())) if obj else None
    return None


def eligible(record, now=None):
    now = now or timezone.now()
    account = PortalAccount.objects.select_related('user', 'patient').filter(pk=record.account_id).first()
    if not account or not account.user.is_active or role_for(account.user) == 'secretary' or account.auth_version != record.auth_version or account.patient_id != record.patient_id or now >= record.expires_at:
        return '', 'account_or_event_changed'
    preference = ContactPreference.objects.filter(account=account).first()
    if not preference or not getattr(preference, record.channel + '_opt_in') or not getattr(preference, KIND_PREFERENCE[record.kind]):
        return '', 'consent_withdrawn'
    target = destination(account, preference, record.channel)
    if not target or digest(target) != record.destination_hash:
        return '', 'contact_changed'
    try:
        current = source(record.kind, record.source_id)
    except (ValueError, TypeError):
        current = None
    if current != (record.patient_id, record.source_version):
        return '', 'event_changed'
    return target, ''


def _plan(account, preference, kind, source_id, version, due_at, expires_at):
    made = 0
    if not getattr(preference, KIND_PREFERENCE[kind]):
        return made
    for channel, _ in CHANNELS:
        target = destination(account, preference, channel)
        if not getattr(preference, channel + '_opt_in') or not target:
            continue
        # A contact or session-generation change can replace cancelled pending
        # work, but an accepted/uncertain attempt must never be sent again.
        if PatientNotification.objects.filter(account=account, kind=kind, source_id=str(source_id), source_version=version, channel=channel, status__in=['sent', 'unknown', 'sending']).exists():
            continue
        key = digest(f'{account.pk}:{kind}:{source_id}:{version}:{channel}:{digest(target)}:{account.auth_version}')
        record, created = PatientNotification.objects.get_or_create(dedup_key=key, defaults={
            'account': account, 'patient_id': account.patient_id, 'channel': channel, 'kind': kind,
            'source_id': str(source_id), 'source_version': version, 'destination_hash': digest(target),
            'auth_version': account.auth_version, 'due_at': due_at, 'expires_at': expires_at})
        made += created
        if not created and record.status == 'cancelled' and record.attempts < MAX_ATTEMPTS:
            # A fresh opt-in can resume an unsent reminder for the same event.
            # Accepted/uncertain attempts were excluded above, and safe-attempt
            # counters are retained rather than resetting the retry bound.
            made += PatientNotification.objects.filter(pk=record.pk, status='cancelled', attempts__lt=MAX_ATTEMPTS).update(status='queued', due_at=due_at, expires_at=expires_at, error_code='')
    return made


def plan_reminders(now=None):
    now = now or timezone.now()
    made = 0
    # Reject stale queued messages, including changed appointment time/cancellation.
    for record in PatientNotification.objects.filter(status__in=['queued', 'failed']).iterator():
        _, reason = eligible(record, now)
        if reason:
            PatientNotification.objects.filter(pk=record.pk, status__in=['queued', 'failed']).update(status='cancelled', error_code=reason)
    for preference in ContactPreference.objects.select_related('account__user', 'account__patient').filter(account__user__is_active=True, account__patient__isnull=False):
        account = preference.account
        if role_for(account.user) == 'secretary':
            continue
        for event in Appointment.objects.filter(patient_id=account.patient_id, status='confirmed', starts_at__gt=now, starts_at__lte=now + timedelta(days=30)):
            version = digest(f'{event.starts_at.isoformat()}:{event.ends_at.isoformat()}')
            made += _plan(account, preference, 'appointment', str(event.pk), version, event.starts_at - timedelta(hours=24), event.starts_at)
        for visit in Visit.objects.filter(patient_id=account.patient_id, follow_up_done=False, follow_up_on__gte=today_tehran(), follow_up_on__lte=today_tehran() + timedelta(days=30)):
            due = timezone.make_aware(datetime.combine(visit.follow_up_on - timedelta(days=1), time(8)), TZ)
            expires = timezone.make_aware(datetime.combine(visit.follow_up_on + timedelta(days=1), time.min), TZ)
            made += _plan(account, preference, 'followup', str(visit.pk), digest(visit.follow_up_on.isoformat()), due, expires)
        for model, prefix in ((AdvicePacket, 'packet'), (AdviceDelivery, 'delivery')):
            records = model.objects.filter(patient_id=account.patient_id, created_at__gte=now - timedelta(days=7))
            if model is AdviceDelivery:
                records = records.filter(packet__isnull=True)
            for record in records:
                made += _plan(account, preference, 'advice', f'{prefix}:{record.pk}', digest(record.created_at.isoformat()), now, record.created_at + timedelta(days=7))
    return made


def message_text(record):
    title = {'appointment': 'یادآوری نوبت شما', 'followup': 'یادآوری پیگیری شما', 'advice': 'اطلاعات تازه در پرتال شما'}[record.kind]
    return f'{title}\nبرای مشاهده جزئیات، وارد حساب خود در پرتال دکتر گرامی شوید:\n{portal_url()}\nانتخاب یا لغو کانال یادآوری در تنظیمات ارتباطی پرتال امکان‌پذیر است.'


class DeliveryFailure(Exception):
    def __init__(self, code, ambiguous=False):
        self.code, self.ambiguous = code, ambiguous


def _http(channel, url, **kwargs):
    try:
        response = requests.post(url, timeout=(5, 15), allow_redirects=False, **kwargs)
    except requests.ConnectTimeout:
        raise DeliveryFailure('connection_timeout')
    except requests.RequestException:
        raise DeliveryFailure('provider_result_unknown', ambiguous=True)
    if response.status_code == 429:
        raise DeliveryFailure('provider_rate_limited')
    if 400 <= response.status_code < 500:
        raise DeliveryFailure('provider_rejected')
    if not 200 <= response.status_code < 300:
        raise DeliveryFailure('provider_result_unknown', ambiguous=True)
    try:
        data = response.json()
        if not isinstance(data, dict):
            raise DeliveryFailure('provider_result_unknown', ambiguous=True)
        if channel == 'telegram':
            if data.get('ok') is False:
                raise DeliveryFailure('provider_rejected')
            if data.get('ok') is not True:
                raise DeliveryFailure('provider_result_unknown', ambiguous=True)
            return str(data['result']['message_id'])[:160]
        return str(data['messages'][0]['id'])[:160]
    except (KeyError, TypeError, ValueError):
        raise DeliveryFailure('provider_result_unknown', ambiguous=True)


def deliver(record, target):
    if record.channel == 'email':
        try:
            accepted = EmailMessage('یادآوری پرتال دکتر گرامی', message_text(record), setting('DEFAULT_FROM_EMAIL'), [target]).send(fail_silently=False)
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPConnectError, ConnectionRefusedError):
            raise DeliveryFailure('smtp_connection_rejected')
        except Exception:
            raise DeliveryFailure('smtp_result_unknown', ambiguous=True)
        if accepted != 1:
            raise DeliveryFailure('smtp_not_accepted')
        return ''
    if record.channel == 'telegram':
        return _http('telegram', 'https://api.telegram.org/bot' + setting('TELEGRAM_BOT_TOKEN') + '/sendMessage', json={'chat_id': target, 'text': message_text(record), 'link_preview_options': {'is_disabled': True}})
    if record.channel == 'whatsapp':
        # The approved template must contain only a generic portal reminder and
        # the fixed portal URL. No variable medical content is submitted.
        url = f"https://graph.facebook.com/{setting('WHATSAPP_API_VERSION')}/{setting('WHATSAPP_PHONE_NUMBER_ID')}/messages"
        return _http('whatsapp', url, headers={'Authorization': 'Bearer ' + setting('WHATSAPP_ACCESS_TOKEN')}, json={
            'messaging_product': 'whatsapp', 'to': target, 'type': 'template',
            'template': {'name': setting('WHATSAPP_TEMPLATE_NAME'), 'language': {'code': setting('WHATSAPP_TEMPLATE_LANGUAGE')}}})
    raise DeliveryFailure('unknown_channel')


def dispatch(*, dry_run=True, limit=50, now=None):
    now = now or timezone.now()
    result = {'sent': 0, 'failed': 0, 'unknown': 0, 'cancelled': 0, 'disabled': 0, 'ready': 0}
    # A process killed after sending cannot safely retry; require investigation.
    if not dry_run:
        PatientNotification.objects.filter(status='sending', claimed_at__lt=now - timedelta(minutes=15)).update(status='unknown', error_code='worker_interrupted')
    due = PatientNotification.objects.filter(status__in=['queued', 'failed'], due_at__lte=now, attempts__lt=MAX_ATTEMPTS)
    ready_channels = [channel for channel, _ in CHANNELS if readiness(channel)[0]]
    result['disabled'] = due.exclude(channel__in=ready_channels).count()
    # An unconfigured channel must not occupy every slot and starve a connected
    # channel forever. Limit only candidates whose provider is configured.
    ids = list(due.filter(channel__in=ready_channels).order_by('due_at', 'pk').values_list('pk', flat=True)[:max(1, min(limit, 500))])
    for pk in ids:
        with transaction.atomic():
            # A conditional update claims each row once on SQLite and PostgreSQL.
            record = PatientNotification.objects.get(pk=pk)
            if record.status not in ('queued', 'failed'):
                continue
            target, reason = eligible(record, now)
            if reason:
                if not dry_run:
                    PatientNotification.objects.filter(pk=pk, status__in=['queued', 'failed']).update(status='cancelled', error_code=reason)
                result['cancelled'] += 1
                continue
            if not readiness(record.channel)[0]:
                result['disabled'] += 1
                continue
            result['ready'] += 1
            if dry_run:
                continue
            claimed = PatientNotification.objects.filter(pk=pk, status=record.status, attempts=record.attempts).update(status='sending', attempts=record.attempts + 1, claimed_at=now, error_code='')
            if not claimed:
                continue
        # Recheck contact/consent/event immediately before network I/O.
        target, reason = eligible(record)
        if reason:
            PatientNotification.objects.filter(pk=pk, status='sending').update(status='cancelled', error_code=reason)
            result['cancelled'] += 1
            continue
        try:
            reference = deliver(record, target)
        except DeliveryFailure as error:
            status = 'unknown' if error.ambiguous else 'failed'
            PatientNotification.objects.filter(pk=pk, status='sending').update(status=status, error_code=error.code, due_at=now + timedelta(minutes=15))
            result[status] += 1
        except Exception:
            # Do not print provider exceptions: some include token-bearing URLs.
            PatientNotification.objects.filter(pk=pk, status='sending').update(status='unknown', error_code='provider_result_unknown')
            result['unknown'] += 1
        else:
            PatientNotification.objects.filter(pk=pk, status='sending').update(status='sent', provider_reference=reference, sent_at=timezone.now())
            result['sent'] += 1
    return result
