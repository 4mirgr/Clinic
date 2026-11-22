from datetime import datetime,timedelta,time
from zoneinfo import ZoneInfo

from django.db import transaction
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .calendar_api import CalendarUnavailable,GoogleCalendar,configured,timestamp
from .calendar_models import Appointment,AvailabilityOverride,CalendarConnection,ScheduleSettings
from .models import AuditEvent

TZ = ZoneInfo('Asia/Tehran')


class BookingError(Exception):
    pass


def overlaps(start,end,intervals):
    return any(start < busy_end and end > busy_start for busy_start,busy_end in intervals)


def working_windows(day,schedule):
    today = timezone.localdate(timezone.now(),TZ)
    if not schedule.enabled or day < today or day > today+timedelta(days=schedule.horizon_days):
        return []
    override = AvailabilityOverride.objects.filter(day=day).first()
    if override:
        if override.closed:
            return []
        try:
            return [(datetime.combine(day,time.fromisoformat(w['start']),TZ),datetime.combine(day,time.fromisoformat(w['end']),TZ)) for w in override.windows]
        except (ValueError,KeyError,TypeError):
            raise BookingError('بازه‌های این روز معتبر نیست؛ تنظیمات بررسی شود.') from None
    if day.weekday() not in schedule.weekdays or not schedule.opens_at or not schedule.closes_at:
        return []
    return [(datetime.combine(day,schedule.opens_at,TZ),datetime.combine(day,schedule.closes_at,TZ))]


def active_connection():
    connection = CalendarConnection.objects.filter(pk=1,active=True).first()
    if not connection or not configured() or connection.account_email.casefold() != settings.GOOGLE_CALENDAR_ACCOUNT or not connection.google_subject:
        raise BookingError('ابتدا حساب گوگل پزشک باید متصل شود.')
    return connection


def available_slots(day,provider=None,exclude=None,schedule=None):
    connection = active_connection()
    schedule = schedule or ScheduleSettings.objects.get_or_create(pk=1)[0]
    windows = working_windows(day,schedule)
    if not windows:
        return []
    provider = provider or GoogleCalendar(connection)
    beginning,closing = min(w[0] for w in windows),max(w[1] for w in windows)
    busy = provider.free_busy_except(beginning,closing,exclude) if exclude else provider.free_busy(beginning,closing)
    records = Appointment.objects.filter(status__in=Appointment.RESERVING).filter(Q(starts_at__lt=closing,ends_at__gt=beginning)|Q(previous_starts_at__lt=closing,previous_ends_at__gt=beginning))
    if exclude:
        records = records.exclude(pk=exclude.pk)
    busy += list(records.values_list('starts_at','ends_at'))
    busy += list(records.exclude(previous_starts_at=None).values_list('previous_starts_at','previous_ends_at'))
    duration = timedelta(minutes=schedule.slot_minutes)
    if schedule.slot_minutes < 5:
        raise BookingError('مدت ویزیت معتبر نیست.')
    result = []
    for start,end in windows:
        while start+duration <= end:
            if start >= timezone.now() and not overlaps(start,start+duration,busy):
                result.append((start,start+duration))
            start += duration
    return result


def _reserve(patient,day,actor,selected=None,provider=None,request_key=None,authorize=None):
    ScheduleSettings.objects.get_or_create(pk=1)
    with transaction.atomic():
        schedule = ScheduleSettings.objects.select_for_update().get(pk=1)
        if authorize:
            current = authorize()
            if current.patient_id != patient.pk:
                raise BookingError('پروفایل بیمار تغییر کرده؛ صفحه را تازه کنید.')
        if request_key:
            existing = Appointment.objects.filter(request_key=request_key).first()
            if existing:
                if existing.patient_id != patient.pk or existing.created_by_id != actor.pk or timezone.localdate(existing.starts_at,TZ) != day or (selected is not None and existing.starts_at != selected):
                    raise BookingError('این فرم برای نوبت دیگری استفاده شده؛ صفحه را تازه کنید.')
                return existing
        connection = active_connection()
        provider = provider or GoogleCalendar(connection)
        slots = available_slots(day,provider=provider,schedule=schedule)
        choice = next((slot for slot in slots if selected is None or slot[0] == selected),None)
        if choice is None:
            raise BookingError('این ساعت آزاد نیست یا خارج از برنامه مطب است؛ وقت دیگری انتخاب کنید.')
        appointment = Appointment.objects.create(patient=patient,created_by=actor,starts_at=choice[0],ends_at=choice[1],connection_generation=connection.generation,request_key=request_key)
        AuditEvent.objects.create(actor=actor,action='appointment.reserve',target=str(appointment.pk))
    sync_appointment(appointment.pk,actor,provider=provider,force=True)
    appointment.refresh_from_db()
    return appointment


def book_next_available(patient,day,actor,provider=None):
    return _reserve(patient,day,actor,provider=provider)


def book_selected_slot(patient,day,selected,actor,provider=None,request_key=None,authorize=None):
    return _reserve(patient,day,actor,selected=selected,provider=provider,request_key=request_key,authorize=authorize)


def reschedule_appointment(pk,day,selected,actor,provider=None):
    ScheduleSettings.objects.get_or_create(pk=1)
    with transaction.atomic():
        schedule = ScheduleSettings.objects.select_for_update().get(pk=1)
        appointment = Appointment.objects.select_for_update().get(pk=pk)
        if appointment.calendar_review_required:
            raise BookingError('تغییر دستی تقویم نیازمند تعیین تکلیف پزشک است؛ ویرایش خودکار انجام نشد.')
        if appointment.status == 'update_pending' and appointment.starts_at == selected:
            return appointment
        if appointment.status != 'confirmed':
            raise BookingError('ابتدا همگام‌سازی نوبت قبلی را کامل کنید؛ سپس ویرایش کنید.')
        connection = active_connection()
        if appointment.connection_generation != connection.generation:
            raise BookingError('این نوبت متعلق به اتصال قبلی گوگل است؛ پیش از ویرایش بررسی شود.')
        provider = provider or GoogleCalendar(connection)
        slots = available_slots(day,provider=provider,exclude=appointment,schedule=schedule)
        choice = next((slot for slot in slots if slot[0] == selected),None)
        if not choice:
            raise BookingError('ساعت جدید آزاد نیست؛ روز یا ساعت دیگری انتخاب کنید.')
        if appointment.starts_at == choice[0] and appointment.ends_at == choice[1]:
            return appointment
        appointment.previous_starts_at,appointment.previous_ends_at = appointment.starts_at,appointment.ends_at
        appointment.starts_at,appointment.ends_at = choice
        appointment.status,appointment.sync_operation = 'update_pending','update'
        appointment.sync_attempts,appointment.last_error = 0,''
        appointment.next_retry_at = timezone.now()
        appointment.save()
        AuditEvent.objects.create(actor=actor,action='appointment.edit_request',target=str(pk))
    return sync_appointment(pk,actor,provider=provider,force=True)


def sync_appointment(pk,actor=None,provider=None,force=False):
    ScheduleSettings.objects.get_or_create(pk=1)
    with transaction.atomic():
        ScheduleSettings.objects.select_for_update().get(pk=1)
        appointment = Appointment.objects.select_for_update().get(pk=pk)
        if appointment.calendar_review_required:
            # A force retry must not recreate a manually deleted event or
            # overwrite a manual move. The original local hold remains intact.
            return appointment
        if appointment.status not in ['pending','update_pending','cancel_pending','conflict_cancelling','attention']:
            return appointment
        if not force and (appointment.next_retry_at > timezone.now() or appointment.sync_attempts >= 10):
            return appointment
        connection = CalendarConnection.objects.filter(pk=1,active=True).first()
        if not connection or not configured() or connection.account_email.casefold() != settings.GOOGLE_CALENDAR_ACCOUNT or not connection.google_subject:
            appointment.last_error = 'تقویم متصل نیست؛ این عملیات در گوگل تأیید نشده است.'
            appointment.save(update_fields=['last_error'])
            return appointment
        if connection.generation != appointment.connection_generation:
            # Conflict cancellations must stay non-reserving even when an old
            # account needs manual attention; their released time may be reused.
            if appointment.status != 'conflict_cancelling':
                appointment.status = 'attention'
            appointment.sync_attempts = 10
            appointment.last_error = 'این نوبت مربوط به اتصال قبلی گوگل است؛ در حساب قبلی بررسی شود.'
            appointment.save(update_fields=['status','sync_attempts','last_error'])
            return appointment
        if force:
            appointment.sync_attempts = 0
        if appointment.status == 'attention':
            appointment.status = {'create':'pending','update':'update_pending','cancel':'cancel_pending'}[appointment.sync_operation]
        try:
            provider = provider or GoogleCalendar(connection)
            if appointment.status in ['cancel_pending','conflict_cancelling']:
                provider.delete_event(appointment)
                appointment.status = 'cancelled'
            elif appointment.sync_operation == 'update':
                existing = provider.find_event(appointment,match_times=False)
                if not existing:
                    raise CalendarUnavailable('رویداد قبلی پیدا نشد؛ رویداد تازه‌ای ساخته نمی‌شود.')
                try:
                    matches = timestamp(existing['start']['dateTime']) == appointment.starts_at and timestamp(existing['end']['dateTime']) == appointment.ends_at
                except (KeyError,TypeError,ValueError):
                    raise CalendarUnavailable('زمان رویداد قبلی معتبر نیست؛ بررسی دستی لازم است.') from None
                if matches:
                    appointment.status = 'confirmed'
                elif appointment.starts_at <= timezone.now():
                    appointment.status,appointment.last_error = 'attention','زمان جدید گذشته است؛ نوبت قبلی هنوز آزاد نشده است.'
                elif overlaps(appointment.starts_at,appointment.ends_at,provider.free_busy_except(appointment.starts_at,appointment.ends_at,appointment)):
                    raise CalendarUnavailable('زمان جدید در گوگل پر شده؛ نوبت قبلی تا تعیین تکلیف محفوظ است.')
                else:
                    provider.update_event(appointment)
                    appointment.status = 'confirmed'
            else:
                existing = provider.find_event(appointment)
                if existing:
                    appointment.status = 'confirmed'
                    appointment.google_event_id = appointment.pk.hex
                elif appointment.starts_at <= timezone.now():
                    appointment.status = 'attention'
                    appointment.last_error = 'زمان مراجعه گذشته و رویداد در گوگل پیدا نشد؛ بررسی پزشک لازم است.'
                elif overlaps(appointment.starts_at,appointment.ends_at,provider.free_busy(appointment.starts_at,appointment.ends_at)):
                    appointment.status = 'conflict'
                    appointment.last_error = 'زمان انتخاب‌شده در گوگل پر شده است؛ نوبت دیگری رزرو کنید.'
                else:
                    provider.insert_event(appointment)
                    appointment.status = 'confirmed'
                    appointment.google_event_id = appointment.pk.hex
            if appointment.status in ['confirmed','cancelled']:
                appointment.last_error = ''
                appointment.previous_starts_at = appointment.previous_ends_at = None
            AuditEvent.objects.create(actor=actor,action='appointment.'+appointment.status,target=str(appointment.pk))
        except CalendarUnavailable as error:
            appointment.sync_attempts += 1
            appointment.next_retry_at = timezone.now() + timedelta(minutes=min(2 ** appointment.sync_attempts,60))
            appointment.last_error = str(error)
            if appointment.sync_attempts >= 10 and appointment.status in ['pending','update_pending']:
                appointment.status = 'attention'
        appointment.save(update_fields=['status','google_event_id','sync_attempts','next_retry_at','last_error','previous_starts_at','previous_ends_at','sync_operation'])
        return appointment


def request_cancellation(pk,actor,provider=None):
    ScheduleSettings.objects.get_or_create(pk=1)
    with transaction.atomic():
        ScheduleSettings.objects.select_for_update().get(pk=1)
        appointment = Appointment.objects.select_for_update().get(pk=pk)
        if appointment.calendar_review_required:
            raise BookingError('تغییر دستی تقویم نیازمند تعیین تکلیف پزشک است؛ لغو خودکار انجام نشد.')
        if appointment.status == 'cancelled':
            return appointment
        appointment.status = 'conflict_cancelling' if appointment.status in ['conflict','conflict_cancelling'] else 'cancel_pending'
        appointment.sync_operation = 'cancel'
        appointment.save(update_fields=['status','sync_operation'])
        AuditEvent.objects.create(actor=actor,action='appointment.cancel_request',target=str(pk))
    return sync_appointment(pk,actor,provider=provider,force=True)
