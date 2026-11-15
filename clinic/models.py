import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.urls import reverse


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
    tags = models.CharField('برچسب‌ها', max_length=300, blank=True)
    body = models.TextField('متن توصیه', max_length=30000)
    source = models.TextField('منابع و توضیح بازبینی', max_length=4000, blank=True)
    is_approved = models.BooleanField('متن را بازبینی و برای ارائه به بیمار تأیید می‌کنم', default=False)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=40)
    target = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


# Register related calendar models without bloating the clinical model module.
from .calendar_models import Appointment, CalendarConnection, ScheduleSettings  # noqa: E402,F401

from .portal_models import PortalAccount, SiteActivity, PortalRecoveryRequest  # noqa: E402,F401
