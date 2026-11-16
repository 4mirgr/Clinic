from django.db import models


class StorageBudget(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    used_bytes = models.PositiveBigIntegerField(default=0)


class DocumentBlob(models.Model):
    # The existing Document FileField retains its opaque patient/UUID path.
    name = models.CharField(max_length=100, primary_key=True)
    content = models.BinaryField()
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
