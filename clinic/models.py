import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from .advice_text import CHOICES, search_document


class LoginThrottle(models.Model):
    key = models.CharField(max_length=64, unique=True)
    failures = models.PositiveIntegerField(default=0)
    expires = models.DateTimeField()


class UserPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    theme = models.CharField(max_length=5, choices=[('light','روز'),('dark','شب')])


class Patient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField('نام', max_length=100)
    last_name = models.CharField('نام خانوادگی', max_length=100)
    national_id = models.CharField('کد ملی', max_length=10, unique=True, null=True, blank=True)
    phone = models.CharField('شماره همراه', max_length=11)
    history = models.TextField('شرح‌حال و سوابق', blank=True, max_length=20000)
    medications = models.TextField('داروهای مصرفی', blank=True, max_length=10000)
    allergies = models.TextField('حساسیت‌ها', blank=True, max_length=10000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    def get_absolute_url(self):
        return reverse('patient_detail', args=[self.pk])


class Visit(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='visits')
    note = models.TextField('شرح ویزیت و برنامه پیگیری', max_length=20000)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


def document_path(instance, filename):
    return f'{instance.patient_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}'


class Document(models.Model):
    CATEGORIES = [('lab','آزمایش'),('echo','اکوکاردیوگرافی'),('ct','گزارش سی‌تی‌اسکن'),('xray','گرافی'),('other','سایر مدارک')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='documents')
    title = models.CharField('عنوان مدرک', max_length=200)
    category = models.CharField('نوع مدرک', max_length=10, choices=CATEGORIES)
    file = models.FileField('فایل', upload_to=document_path)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Advice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField('عنوان توصیه', max_length=200)
    catalog_key = models.SlugField(null=True, blank=True, unique=True)
    specialty = models.CharField('شاخه تخصصی', max_length=40, choices=CHOICES, blank=True)
    title_en = models.CharField('عنوان انگلیسی', max_length=200, blank=True)
    search_text = models.TextField(blank=True, editable=False)
    source_metadata = models.JSONField(default=dict, blank=True)
    tags = models.CharField('برچسب‌ها', max_length=1000, blank=True)
    body = models.TextField('متن توصیه', max_length=30000)
    source = models.TextField('منابع و توضیح بازبینی', max_length=4000, blank=True)
    is_approved = models.BooleanField('متن را بازبینی و برای ارائه به بیمار تأیید می‌کنم', default=False)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            fields = ('title','title_en','specialty','tags','body','source','source_metadata')
            old = type(self).objects.filter(pk=self.pk).values(*fields).first()
            if old and any(old[key] != getattr(self,key) for key in fields):
                self.is_approved = False
        self.search_text = search_document(self)
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'search_text','is_approved','updated_at'}
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ['title']


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=40)
    target = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class AdviceDelivery(models.Model):
    """A recorded copy, independent of subsequent edits to the library."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='advice_deliveries')
    advice = models.ForeignKey(Advice, on_delete=models.PROTECT, related_name='deliveries')
    title = models.CharField(max_length=200)
    body = models.TextField(max_length=30000)
    tags = models.CharField(max_length=1000, blank=True)
    packet = models.ForeignKey("AdvicePacket", on_delete=models.PROTECT, null=True, blank=True, related_name="deliveries")
    position = models.PositiveSmallIntegerField(default=0)
    title_en = models.CharField(max_length=200, blank=True)
    specialty = models.CharField(max_length=40, blank=True)
    source_metadata = models.JSONField(default=dict, blank=True)
    source = models.TextField(max_length=4000, blank=True)
    advice_updated_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    request_key = models.UUIDField(unique=True, editable=False)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [models.UniqueConstraint(fields=['packet','position'], condition=models.Q(packet__isnull=False), name='unique_packet_position')]

    def get_absolute_url(self):
        return reverse('advice_delivery_print', args=[self.pk])

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('نسخه ثبت‌شده قابل بازنویسی نیست؛ توصیه تازه‌ای ثبت کنید.')
        return super().save(*args, **kwargs)


# Register related calendar models without bloating the clinical model module.
from .calendar_models import Appointment, AvailabilityOverride, CalendarConnection, ScheduleSettings  # noqa: E402,F401
from .portal_models import PortalAccount, SiteActivity, PortalRecoveryRequest  # noqa: E402,F401


class AdvicePacket(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='advice_packets')
    patient_name = models.CharField(max_length=201)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    request_key = models.UUIDField(unique=True, editable=False)
    selection_fingerprint = models.CharField(max_length=64)

    class Meta:
        ordering = ['-created_at']

    def get_absolute_url(self):
        return reverse('advice_packet', args=[self.pk])

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('نسخه ثبت‌شده قابل بازنویسی نیست.')
        return super().save(*args, **kwargs)


class PatientSummary(models.Model):
    patient = models.OneToOneField(Patient, on_delete=models.PROTECT, primary_key=True, related_name='shared_summary')
    draft_data = models.JSONField(default=dict)
    published_data = models.JSONField(default=dict)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name='+')
    published_at = models.DateTimeField(null=True)
