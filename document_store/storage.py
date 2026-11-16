"""Optional bounded private bytes in the same dedicated Clinic PostgreSQL DB."""
import hashlib

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.core.files.utils import validate_file_name
from django.db import transaction
from django.utils.deconstruct import deconstructible

from .exceptions import DocumentStorageFull
from .models import DocumentBlob, StorageBudget


@deconstructible
class DatabaseDocumentStorage(Storage):
    def _open(self, name, mode='rb'):
        if mode not in ('r', 'rb'):
            raise ValueError('Private document streams are read-only.')
        try:
            blob = DocumentBlob.objects.get(pk=name)
        except DocumentBlob.DoesNotExist:
            raise FileNotFoundError('Private document is unavailable.') from None
        data = bytes(blob.content)
        if len(data) != blob.size or hashlib.sha256(data).hexdigest() != blob.sha256:
            raise OSError('Private document integrity check failed.')
        return ContentFile(data, name=name)

    def _save(self, name, content):
        validate_file_name(name, allow_relative_path=True)
        data = bytearray()
        for chunk in content.chunks():
            data.extend(chunk)
            if len(data) > 20 * 1024 * 1024:
                raise SuspiciousFileOperation('Private document exceeds the upload limit.')
        size = len(data)
        with transaction.atomic():
            StorageBudget.objects.get_or_create(pk=1)
            budget = StorageBudget.objects.select_for_update().get(pk=1)
            if budget.used_bytes + size > settings.CLINIC_DOCUMENT_BUDGET_BYTES:
                raise DocumentStorageFull('Private document budget exhausted.')
            # Serialize collision checks with budget allocation, never overwrite bytes.
            name = self.get_available_name(name, max_length=100)
            DocumentBlob.objects.create(name=name, content=bytes(data), size=size,
                                        sha256=hashlib.sha256(data).hexdigest())
            budget.used_bytes += size
            budget.save(update_fields=['used_bytes'])
        return name

    def exists(self, name):
        return DocumentBlob.objects.filter(pk=name).exists()

    def size(self, name):
        try:
            return DocumentBlob.objects.values_list('size', flat=True).get(pk=name)
        except DocumentBlob.DoesNotExist:
            raise FileNotFoundError('Private document is unavailable.') from None

    def delete(self, name):
        with transaction.atomic():
            budget = StorageBudget.objects.select_for_update().filter(pk=1).first()
            blob = DocumentBlob.objects.only('name','size').filter(pk=name).first()
            if not blob:
                return
            if not budget:
                raise OSError('Private document accounting is unavailable.')
            size = blob.size
            blob.delete()
            budget.used_bytes = max(0, budget.used_bytes - size)
            budget.save(update_fields=['used_bytes'])

    def get_created_time(self, name):
        return DocumentBlob.objects.values_list('created_at', flat=True).get(pk=name)

    # Storage's path() and url() intentionally remain unavailable. Only the
    # existing authenticated, attachment-only document views can return bytes.
