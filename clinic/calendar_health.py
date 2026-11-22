"""Local Calendar readiness and an explicitly requested, read-only provider probe.

Results contain safe identifiers and explanations, never provider responses,
credentials, event data or exception text. No result is persisted as proof that a
later booking will succeed.
"""
from datetime import timedelta
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone

from .calendar_api import GoogleCalendar
from .calendar_models import AvailabilityOverride, CalendarConnection, ScheduleSettings
from .jalali import today_tehran


REQUIRED_SETTINGS = (
    'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_TOKEN_ENCRYPTION_KEY',
    'GOOGLE_REDIRECT_URI', 'GOOGLE_CALENDAR_ACCOUNT',
)
MESSAGES = {
    'private_backend_not_deployed': 'این صفحه پیش‌نمایش ساختگی است؛ backend خصوصی تقویم در این مسیر مستقر نشده و اتصال یا رزرو واقعی انجام نمی‌شود.',
    'not_configured': 'تنظیمات امن Google Calendar کامل نیست؛ نام تنظیمات لازم در ادامه آمده است.',
    'invalid_configuration': 'قالب کلید رمزنگاری، نشانی بازگشت HTTPS یا حساب مورد انتظار معتبر نیست؛ تنظیمات مشخص‌شده باید اصلاح شوند.',
    'not_connected': 'حساب Google Calendar هنوز متصل نشده است؛ پس از تکمیل تنظیمات، مدیر باید اجازه دسترسی بدهد.',
    'account_mismatch': 'اتصال ذخیره‌شده با حساب مورد انتظار یا هویت گوگل تطابق ندارد؛ اتصال دوباره لازم است.',
    'token_key_mismatch': 'توکن اتصال با کلید فعلی قابل خواندن نیست یا خالی است؛ کلید اصلی را بازیابی یا حساب را دوباره متصل کنید.',
    'working_hours_unset': 'رزرو فعال نیست؛ برنامه هفتگی یا بازه معتبر روزهای آینده و فعال‌سازی نوبت‌دهی را تکمیل کنید.',
    'provider_failed': 'بررسی فقط‌خواندنی گوگل موفق نشد؛ دسترسی، اعتبار اجازه، فعال بودن Calendar API و ارتباط شبکه بررسی شود. هیچ نوبتی تأیید نشده است.',
    'connection_changed': 'اتصال حین بررسی تغییر یا قطع شد؛ نتیجه برای اتصال فعلی معتبر نیست. دوباره بررسی کنید.',
}


def configuration_issues():
    """Inspect only local settings, without network or database access."""
    missing = [name for name in REQUIRED_SETTINGS if not getattr(settings, name, '')]
    invalid = []
    if 'GOOGLE_TOKEN_ENCRYPTION_KEY' not in missing:
        try:
            Fernet(settings.GOOGLE_TOKEN_ENCRYPTION_KEY.encode())
        except (ValueError, TypeError, AttributeError, UnicodeError):
            invalid.append('GOOGLE_TOKEN_ENCRYPTION_KEY')
    if 'GOOGLE_REDIRECT_URI' not in missing:
        try:
            uri = urlsplit(settings.GOOGLE_REDIRECT_URI)
            if (uri.scheme != 'https' or not uri.hostname or uri.username or uri.password
                    or not uri.path.startswith('/') or uri.fragment or uri.query):
                raise ValueError()
            uri.port  # Reject malformed ports without echoing their values.
        except (ValueError, TypeError, AttributeError):
            invalid.append('GOOGLE_REDIRECT_URI')
    if 'GOOGLE_CALENDAR_ACCOUNT' not in missing:
        try:
            validate_email(settings.GOOGLE_CALENDAR_ACCOUNT)
        except (ValidationError, TypeError, AttributeError):
            invalid.append('GOOGLE_CALENDAR_ACCOUNT')
    return missing, invalid


def _hours_ready(schedule):
    if not schedule or not schedule.enabled or not 5 <= schedule.slot_minutes <= 180:
        return False
    if (schedule.weekdays and all(type(day) is int and 0 <= day <= 6 for day in schedule.weekdays)
            and schedule.opens_at and schedule.closes_at and schedule.opens_at < schedule.closes_at):
        available = ((schedule.closes_at.hour * 60 + schedule.closes_at.minute)
                     - (schedule.opens_at.hour * 60 + schedule.opens_at.minute))
        if available >= schedule.slot_minutes:
            return True
    # An override-only schedule is supported; expired or malformed overrides do
    # not make the booking controls appear ready.
    from datetime import time
    today = today_tehran()
    overrides = AvailabilityOverride.objects.filter(
        closed=False, day__gte=today, day__lte=today + timedelta(days=schedule.horizon_days))
    for override in overrides:
        try:
            for window in override.windows:
                start, end = time.fromisoformat(window['start']), time.fromisoformat(window['end'])
                if ((end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)) >= schedule.slot_minutes:
                    return True
        except (KeyError, TypeError, ValueError):
            continue
    return False


def _binding(connection):
    return (connection.generation, connection.active, connection.account_email,
            connection.google_subject, connection.calendar_id, connection.refresh_token_encrypted)


def diagnose_calendar(*, probe=False, preview=None):
    """Read local readiness; only ``probe=True`` permits one future FreeBusy call.

    The provider probe creates/edits/deletes no event and writes no local model.
    A successful FreeBusy read proves access only at the time of that check.
    """
    if preview is None:
        preview = getattr(settings, 'CLINIC_PREVIEW_EXPORT', False)
    missing, invalid = configuration_issues()
    codes = []
    if preview:
        codes.append('private_backend_not_deployed')
    if missing:
        codes.append('not_configured')
    if invalid:
        codes.append('invalid_configuration')
    connection = CalendarConnection.objects.filter(pk=1).first()
    if not connection or not connection.active:
        codes.append('not_connected')
    else:
        expected = str(getattr(settings, 'GOOGLE_CALENDAR_ACCOUNT', '')).strip().casefold()
        if (connection.account_email.strip().casefold() != expected
                or not connection.google_subject or not connection.calendar_id):
            codes.append('account_mismatch')
        if not missing and not invalid:
            try:
                if not connection.get_refresh_token():
                    raise ValueError()
            except Exception:
                # CalendarUnavailable and malformed local ciphertext are equally
                # safe to report without their exception text.
                codes.append('token_key_mismatch')
    hours_ready = _hours_ready(ScheduleSettings.objects.filter(pk=1).first())
    if not hours_ready:
        codes.append('working_hours_unset')
    can_probe = not any(code != 'working_hours_unset' for code in codes)
    verified = False
    attempted = bool(probe and can_probe)
    if attempted:
        binding = _binding(connection)
        try:
            start = timezone.now() + timedelta(days=1)
            GoogleCalendar(connection).free_busy(start, start + timedelta(minutes=10))
            current = CalendarConnection.objects.filter(pk=1).first()
            if current is None or _binding(current) != binding:
                codes.append('connection_changed')
            else:
                verified = True
        except Exception:
            # Neither provider response bodies nor exception representations are
            # safe for a management command, log, flash message or HTML.
            codes.append('provider_failed')
    summary = ('بررسی فقط‌خواندنی FreeBusy موفق بود؛ هیچ رویدادی ساخته یا ویرایش نشد. '
               'این نتیجه، تأیید نوبت یا تضمین دسترسی آینده نیست.' if verified else
               MESSAGES[codes[0]] if codes else
               'تنظیمات محلی آماده است؛ دسترسی واقعی به گوگل هنوز بررسی نشده است.')
    return {
        'status': codes[0] if codes else ('verified' if verified else 'locally_ready'),
        'issues': [{'code': code, 'message': MESSAGES[code]} for code in codes],
        'missing_settings': missing, 'invalid_settings': invalid,
        'can_connect': not preview and not missing and not invalid,
        'can_probe': can_probe, 'probe_attempted': attempted, 'probe_verified': verified,
        'hours_ready': hours_ready, 'local_ready': can_probe and hours_ready,
        'summary': summary, 'preview': bool(preview),
    }
