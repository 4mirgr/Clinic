import uuid

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models
from django.utils import timezone


class CalendarConnection(models.Model):
    # One clinic, one owner calendar. Refresh tokens are never stored in plaintext.
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    calendar_id = models.CharField(max_length=255,default='primary')
    generation = models.UUIDField(default=uuid.uuid4,editable=False)
    refresh_token_encrypted = models.TextField(blank=True)
    active = models.BooleanField(default=False)
    connected_at = models.DateTimeField(auto_now=True)

    def set_refresh_token(self,token):
        self.refresh_token_encrypted = Fernet(settings.GOOGLE_TOKEN_ENCRYPTION_KEY.encode()).encrypt(token.encode()).decode()

    def get_refresh_token(self):
        from .calendar_api import CalendarUnavailable
        try:
            return Fernet(settings.GOOGLE_TOKEN_ENCRYPTION_KEY.encode()).decrypt(self.refresh_token_encrypted.encode()).decode()
        except (InvalidToken,ValueError,TypeError,UnicodeError):
            raise CalendarUnavailable('اتصال گوگل نیاز به اتصال مجدد دارد.') from None


class ScheduleSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True,default=1,editable=False)
    enabled = models.BooleanField('نوبت‌دهی فعال باشد',default=False)
    weekdays = models.JSONField(default=list)
    opens_at = models.TimeField('شروع کار',null=True,blank=True)
    closes_at = models.TimeField('پایان کار',null=True,blank=True)
    slot_minutes = models.PositiveSmallIntegerField('مدت ویزیت (دقیقه)',default=20)
    horizon_days = models.PositiveSmallIntegerField('حداکثر فاصله رزرو (روز)',default=30)


class AvailabilityOverride(models.Model):
    day = models.DateField(unique=True)
    closed = models.BooleanField(default=False)
    windows = models.JSONField(default=list)

    class Meta:
        ordering = ['day']


class Appointment(models.Model):
    STATUS = [('pending','در انتظار ثبت گوگل'),('confirmed','ثبت‌شده در گوگل'),('cancel_pending','لغو در انتظار تأیید'),('conflict_cancelling','لغو نوبت دارای تداخل، در انتظار تأیید'),('cancelled','لغوشده'),('conflict','تداخل در گوگل؛ زمان جدید لازم است'),('attention','نیازمند بررسی پزشک')]
    RESERVING = ['pending','confirmed','cancel_pending','attention']
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    patient = models.ForeignKey('clinic.Patient',on_delete=models.PROTECT,related_name='appointments')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=20,choices=STATUS,default='pending')
    connection_generation = models.UUIDField()
    google_event_id = models.CharField(max_length=64,blank=True)
    sync_attempts = models.PositiveSmallIntegerField(default=0)
    next_retry_at = models.DateTimeField(default=timezone.now)
    last_error = models.CharField(max_length=250,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    request_key = models.UUIDField(unique=True,null=True,blank=True,editable=False)

    class Meta:
        ordering = ['-starts_at']
        constraints = [
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F('starts_at')),name='appointment_end_after_start'),
            models.UniqueConstraint(fields=['starts_at'],condition=models.Q(status__in=['pending','confirmed','cancel_pending','attention']),name='one_reserved_appointment_start'),
        ]
