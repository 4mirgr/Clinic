"""Private editorial snapshots; ordinary saves append rather than rewrite."""
import copy
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from .advice_text import CHOICES


CONTENT_FIELDS = ('title', 'title_en', 'specialty', 'tags', 'body', 'source', 'source_metadata')
REVISION_FIELDS = CONTENT_FIELDS + ('catalog_key', 'is_approved')


class AdviceRevision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    advice = models.ForeignKey('clinic.Advice', on_delete=models.PROTECT, related_name='revisions')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    advice_updated_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_baseline = models.BooleanField(default=False)
    title = models.CharField(max_length=200)
    title_en = models.CharField(max_length=200, blank=True)
    specialty = models.CharField(max_length=40, choices=CHOICES, blank=True)
    catalog_key = models.SlugField(null=True, blank=True)
    tags = models.CharField(max_length=1000, blank=True)
    body = models.TextField(max_length=30000)
    source = models.TextField(max_length=4000, blank=True)
    source_metadata = models.JSONField(default=dict, blank=True)
    is_approved = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['advice', '-created_at'], name='advice_revision_history_idx')]

    @classmethod
    def capture(cls, advice, *, using, is_baseline=False):
        return cls.objects.using(using).create(advice_id=advice.pk, actor_id=advice.updated_by_id,
            advice_updated_at=advice.updated_at, is_baseline=is_baseline,
            **{field:copy.deepcopy(getattr(advice, field)) for field in REVISION_FIELDS})

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('تاریخچه توصیه قابل بازنویسی نیست؛ متن فعلی را ویرایش کنید.')
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('advice_revision_detail', args=[self.advice_id, self.pk])
