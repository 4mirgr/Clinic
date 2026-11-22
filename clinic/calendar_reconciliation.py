"""Conservative reconciliation of future, previously confirmed clinic events.

Never import personal events or create/update/delete a Google event. Explicit
apply mode adopts owned provider changes locally; report mode does not. Network
calls finish before taking any database locks. Reports contain
counts and fixed codes only; provider payloads and identifiers stay private.
"""
from datetime import datetime

from django.conf import settings
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F, Q
from django.utils import timezone

from .calendar_api import GoogleCalendar
from .calendar_health import configuration_issues
from .calendar_models import Appointment, CalendarConnection, ScheduleSettings
from .models import AuditEvent


MISMATCH_MESSAGES = {
    'moved': '[calendar_event_moved] زمان رویداد در گوگل تغییر کرده است؛ زمان محلی تا بررسی پزشک محفوظ می‌ماند.',
    'missing': '[calendar_event_missing] رویداد تأییدشده در گوگل پیدا نشد یا حذف شده است؛ زمان محلی تا بررسی پزشک محفوظ می‌ماند.',
    'overlap': '[calendar_event_overlap] زمان جدید گوگل با نوبت محفوظ دیگری تداخل دارد؛ زمان قبلی تا تعیین تکلیف پزشک محفوظ است.',
}
SNAPSHOT_FIELDS = (
    'status', 'starts_at', 'ends_at', 'previous_starts_at', 'previous_ends_at',
    'connection_generation', 'google_event_id', 'calendar_review_required',
    'sync_operation', 'sync_attempts', 'next_retry_at', 'last_error',
    'patient_id', 'created_by_id',
    'calendar_checked_at',
)


def _snapshot(appointment):
    return tuple(getattr(appointment, key) for key in SNAPSHOT_FIELDS)


def _binding(connection):
    if connection is None:
        return None
    return (connection.pk, connection.active, connection.generation,
            connection.owner_id, connection.account_email, connection.google_subject,
            connection.calendar_id, connection.refresh_token_encrypted)


def _finish_probe(appointment, binding, result, *, flag, apply, actor):
    """Recheck the exact read snapshot under the existing scheduling mutex."""
    state = result['state']
    if flag or apply:
        ScheduleSettings.objects.get_or_create(pk=1)
    with transaction.atomic():
        # OAuth, appointment sync and cancellation take this mutex too. Do not
        # create settings as a side effect of a report-only command.
        ScheduleSettings.objects.select_for_update().filter(pk=1).first()
        current_connection = CalendarConnection.objects.select_for_update().filter(pk=1).first()
        if _binding(current_connection) != binding:
            return 'connection_changed'
        current = Appointment.objects.select_for_update().filter(pk=appointment.pk).first()
        if (current is None or _snapshot(current) != _snapshot(appointment)
                or current.starts_at <= timezone.now()):
            return 'stale'
        if flag or apply:
            # A timestamp records an attempt, NEVER proof of provider success.
            # Rotate failed/unknown reads too, but only after the binding and
            # exact local snapshot were rechecked. Read-only probes never write.
            current.calendar_checked_at = timezone.now()
            current.save(update_fields=['calendar_checked_at'])
        if apply and state == 'moved':
            start, end = result['starts_at'], result['ends_at']
            collision = Appointment.objects.filter(status__in=Appointment.RESERVING).exclude(pk=current.pk).filter(
                Q(starts_at__lt=end, ends_at__gt=start) |
                Q(previous_starts_at__lt=end, previous_ends_at__gt=start)
            ).exists()
            if collision:
                changed = not current.calendar_review_required or current.last_error != MISMATCH_MESSAGES['overlap']
                current.status, current.calendar_review_required = 'attention', True
                current.last_error = MISMATCH_MESSAGES['overlap']
                current.save(update_fields=['status', 'calendar_review_required', 'last_error'])
                if changed:
                    AuditEvent.objects.create(actor=actor, action='calendar.reconcile_overlap', target=str(current.pk))
                return 'overlap'
            current.starts_at, current.ends_at = start, end
            current.previous_starts_at = current.previous_ends_at = None
            current.status, current.calendar_review_required, current.last_error = 'confirmed', False, ''
            current.save(update_fields=['starts_at', 'ends_at', 'previous_starts_at', 'previous_ends_at',
                                        'status', 'calendar_review_required', 'last_error'])
            AuditEvent.objects.create(actor=actor, action='calendar.reconcile_adopt_move', target=str(current.pk))
            return 'applied_moved'
        if apply and state == 'missing':
            current.status, current.calendar_review_required, current.last_error = 'cancelled', False, ''
            current.previous_starts_at = current.previous_ends_at = None
            current.save(update_fields=['status', 'calendar_review_required', 'last_error',
                                        'previous_starts_at', 'previous_ends_at'])
            AuditEvent.objects.create(actor=actor, action='calendar.reconcile_adopt_delete', target=str(current.pk))
            return 'applied_missing'
        if not (flag or apply):
            return state
        if state in ('moved', 'missing'):
            message = MISMATCH_MESSAGES[state]
            if current.calendar_review_required and current.last_error == message:
                return state
            current.status = 'attention'
            current.calendar_review_required = True
            current.last_error = message
            current.save(update_fields=['status', 'calendar_review_required', 'last_error'])
            AuditEvent.objects.create(actor=actor, action='calendar.reconcile_'+state,
                                      target=str(current.pk))
            return 'flagged'
        if state == 'matching' and current.calendar_review_required:
            current.status = 'confirmed'
            current.calendar_review_required = False
            current.last_error = ''
            current.save(update_fields=['status', 'calendar_review_required', 'last_error'])
            AuditEvent.objects.create(actor=actor, action='calendar.reconcile_restored',
                                      target=str(current.pk))
            return 'restored'
        return state


def reconcile_calendar(*, probe=False, flag_reviewed_mismatches=False, apply_google=False, limit=50, actor=None):
    """Count locally by default; explicit flags permit provider reads/local flags.

    Both mutation options require ``probe`` and are mutually exclusive. Flag mode
    preserves local holds. Apply mode adopts moved/deleted owned Google events;
    colliding moves stay flagged with original holds. Neither writes to Google.
    """
    if (flag_reviewed_mismatches or apply_google) and not probe:
        raise ValueError('Local reconciliation writes require an explicit probe.')
    if flag_reviewed_mismatches and apply_google:
        raise ValueError('Choose either flagging or applying Google changes.')
    limit = max(1, min(int(limit), 500))
    candidates = Appointment.objects.filter(
        Q(status='confirmed') | Q(status='attention', calendar_review_required=True),
        starts_at__gt=timezone.now(),
    ).order_by(F('calendar_checked_at').asc(nulls_first=True), 'starts_at', 'pk')
    eligible = candidates.count()
    report = {
        'status': 'local_only', 'probe_requested': bool(probe),
        'flag_requested': bool(flag_reviewed_mismatches),
        'apply_requested': bool(apply_google),
        'eligible': eligible, 'inspected': 0, 'matching': 0,
        'moved': 0, 'missing': 0, 'unknown': 0, 'stale': 0,
        'skipped_binding': 0, 'flagged': 0, 'restored': 0,
        'provider_failed': 0, 'issues': [],
        'applied_moved': 0, 'applied_missing': 0, 'overlap': 0,
        'local_failed': 0, 'considered': 0, 'remaining': eligible,
    }
    if not probe:
        return report
    if getattr(settings, 'CLINIC_PREVIEW_EXPORT', False):
        report.update(status='preview_disabled', issues=['preview_disabled'])
        return report
    missing, invalid = configuration_issues()
    if missing or invalid:
        report.update(status='not_configured', issues=['not_configured'])
        return report
    connection = CalendarConnection.objects.filter(pk=1, active=True).first()
    if not connection:
        report.update(status='not_connected', issues=['not_connected'])
        return report
    if (connection.account_email.strip().casefold() != settings.GOOGLE_CALENDAR_ACCOUNT.strip().casefold()
            or not connection.google_subject or not connection.calendar_id):
        report.update(status='account_mismatch', issues=['account_mismatch'])
        return report
    try:
        if not connection.get_refresh_token():
            raise ValueError()
        provider = GoogleCalendar(connection)
    except Exception:
        report.update(status='connection_unavailable', issues=['connection_unavailable'])
        return report
    binding = _binding(connection)
    report['status'] = 'checked'
    # Old-account records cannot be read or safely marked checked on this
    # binding. Count them separately so they cannot starve current events.
    report['skipped_binding'] = candidates.exclude(connection_generation=connection.generation).count()
    for appointment in candidates.filter(connection_generation=connection.generation)[:limit]:
        report['considered'] += 1
        # Recheck the binding before each read, and again under locks afterwards.
        if _binding(CalendarConnection.objects.filter(pk=1).first()) != binding:
            report['issues'].append('connection_changed')
            report['status'] = 'connection_changed'
            break
        try:
            if appointment.google_event_id != appointment.pk.hex:
                result = {'state': 'unknown'}
            else:
                report['inspected'] += 1
                result = provider.inspect_event(appointment)
            state = result.get('state') if isinstance(result, dict) else 'unknown'
            if state not in ('matching', 'moved', 'missing', 'unknown'):
                state = 'unknown'
            if state == 'moved':
                start, end = result.get('starts_at'), result.get('ends_at')
                if (not isinstance(start, datetime) or not isinstance(end, datetime)
                        or timezone.is_naive(start) or timezone.is_naive(end) or end <= start):
                    state = 'unknown'
            result = {**result, 'state': state} if isinstance(result, dict) else {'state': 'unknown'}
        except Exception:
            # Includes transport/auth/provider decoding failures. Never print an
            # exception, which may contain credentials or private event content.
            state, result = 'provider_failed', {'state': 'provider_failed'}
        try:
            outcome = _finish_probe(appointment, binding, result,
                                    flag=flag_reviewed_mismatches, apply=apply_google, actor=actor)
        except (IntegrityError, OperationalError):
            # Atomic rollback preserves reservations on contention/constraint
            # failure. Database exception text can include record identifiers.
            report['local_failed'] += 1
            continue
        if outcome == 'connection_changed':
            report['issues'].append('connection_changed')
            report['status'] = 'connection_changed'
            break
        if outcome == 'stale':
            report['stale'] += 1
            continue
        report[state] += 1
        if outcome in ('flagged', 'restored', 'applied_moved', 'applied_missing', 'overlap'):
            report[outcome] += 1
    if report['provider_failed']:
        report['issues'].append('provider_failed')
    if report['unknown']:
        report['issues'].append('untrusted_event')
    if report['skipped_binding']:
        report['issues'].append('old_binding')
    if report['stale']:
        report['issues'].append('local_state_changed')
    if report['overlap']:
        report['issues'].append('local_overlap')
    if report['local_failed']:
        report['issues'].append('local_write_failed')
    report['remaining'] = max(0, report['eligible'] - report['considered'] - report['skipped_binding'])
    if report['remaining']:
        report['issues'].append('limit_reached' if report['considered'] == limit else 'probe_interrupted')
    if report['issues'] and report['status'] == 'checked':
        report['status'] = 'incomplete'
    return report
