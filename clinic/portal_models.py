"""Canonical accounts and patient-reported data shared with the public website."""
import uuid
from django.conf import settings
from django.db import models


class PortalAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='portal_account')
    email = models.EmailField(unique=True)
    patient = models.OneToOneField('clinic.Patient', null=True, blank=True, on_delete=models.PROTECT, related_name='portal_account')
    phone = models.CharField(max_length=24, blank=True)
    site_role = models.CharField(max_length=6, choices=[('member','Member'),('admin','Website administrator')], default='member')
    reported_history = models.TextField(max_length=10000, blank=True)
    reported_medications = models.TextField(max_length=5000, blank=True)
    reported_allergies = models.TextField(max_length=5000, blank=True)
    reported_current_problem = models.TextField(max_length=6000, blank=True)
    reported_onset = models.TextField(max_length=2000, blank=True)
    reported_surgeries = models.TextField(max_length=5000, blank=True)
    reported_family_history = models.TextField(max_length=5000, blank=True)
    reported_supplements = models.TextField(max_length=3000, blank=True)
    reported_social_history = models.TextField(max_length=5000, blank=True)
    track_activity = models.BooleanField(default=False)
    share_activity = models.BooleanField(default=False)
    consent_updated_at = models.DateTimeField(null=True, blank=True)
    auth_version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SiteActivity(models.Model):
    account = models.ForeignKey(PortalAccount, on_delete=models.CASCADE, related_name='site_activity')
    kind = models.CharField(max_length=12, choices=[('search','Search'),('article_open','Opened article')])
    value = models.CharField(max_length=160)
    category = models.CharField(max_length=100, blank=True)
    day = models.DateField()
    count = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['account','kind','value','day'], name='portal_activity_daily_unique')]
        indexes = [models.Index(fields=['account','-updated_at'])]


class PortalRecoveryRequest(models.Model):
    account = models.ForeignKey(PortalAccount, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


class PatientIntakeSubmission(models.Model):
    account = models.ForeignKey(PortalAccount, on_delete=models.PROTECT, related_name='intake_submissions')
    patient = models.ForeignKey('clinic.Patient', on_delete=models.PROTECT, related_name='intake_submissions')
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at','-pk']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            from django.core.exceptions import ValidationError
            raise ValidationError('اطلاعات قبلی حفظ می‌شود؛ نسخه جدید ثبت کنید.')
        return super().save(*args, **kwargs)


class GoogleIdentity(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='google_identity')
    subject = models.CharField(max_length=255, unique=True)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
