"""Opt-in contact verification and durable, non-clinical notification outbox."""
from django.conf import settings
from django.db import models
from django.utils import timezone


CHANNELS = [('email', 'ایمیل'), ('telegram', 'تلگرام'), ('whatsapp', 'واتس‌اپ')]


class ContactPreference(models.Model):
    account = models.OneToOneField('clinic.PortalAccount', on_delete=models.PROTECT, related_name='contact_preferences')
    email_opt_in = models.BooleanField(default=False)
    telegram_opt_in = models.BooleanField(default=False)
    whatsapp_opt_in = models.BooleanField(default=False)
    appointment_reminders = models.BooleanField(default=True)
    followup_reminders = models.BooleanField(default=True)
    advice_notifications = models.BooleanField(default=True)
    verified_email = models.EmailField(blank=True)
    verified_whatsapp = models.CharField(max_length=24, blank=True)
    verified_telegram = models.CharField(max_length=24, blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    verified_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)


class TelegramLinkChallenge(models.Model):
    account = models.ForeignKey('clinic.PortalAccount', on_delete=models.CASCADE)
    token_digest = models.CharField(max_length=64, unique=True)
    auth_version = models.PositiveIntegerField()
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PatientNotification(models.Model):
    KINDS = [('appointment', 'یادآوری نوبت'), ('followup', 'یادآوری پیگیری'), ('advice', 'توصیه آماده')]
    STATUSES = [('queued', 'در صف'), ('sending', 'در حال ارسال'), ('sent', 'پذیرفته‌شده توسط سرویس'), ('failed', 'خطای قابل تلاش مجدد'), ('unknown', 'نتیجه نامشخص؛ نیازمند بررسی'), ('cancelled', 'لغوشده')]
    account = models.ForeignKey('clinic.PortalAccount', on_delete=models.PROTECT)
    patient = models.ForeignKey('clinic.Patient', on_delete=models.PROTECT)
    channel = models.CharField(max_length=12, choices=CHANNELS)
    kind = models.CharField(max_length=16, choices=KINDS)
    source_id = models.CharField(max_length=64)
    source_version = models.CharField(max_length=64)
    dedup_key = models.CharField(max_length=64, unique=True)
    destination_hash = models.CharField(max_length=64)
    auth_version = models.PositiveIntegerField()
    due_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=12, choices=STATUSES, default='queued')
    attempts = models.PositiveSmallIntegerField(default=0)
    error_code = models.CharField(max_length=40, blank=True)
    provider_reference = models.CharField(max_length=160, blank=True)
    sent_at = models.DateTimeField(null=True)
    claimed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['status', 'due_at'], name='notification_due_idx')]
