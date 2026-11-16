import uuid
from django.db import models


class Subscription(models.Model):
    """Educational email consent; never a patient record or clinical role."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.OneToOneField('clinic.PortalAccount', on_delete=models.CASCADE, related_name='newsletter')
    status = models.CharField(max_length=12, default='unsubscribed', choices=[
        ('unsubscribed', 'Unsubscribed'), ('pending', 'Confirmation pending'), ('active', 'Active')])
    consent_version = models.CharField(max_length=40, blank=True)
    requested_at = models.DateTimeField(null=True, blank=True)
    confirmation_email = models.EmailField(blank=True)
    confirmation_hash = models.CharField(max_length=64, null=True, blank=True, unique=True)
    confirmation_expires_at = models.DateTimeField(null=True, blank=True)
    confirmed_email = models.EmailField(blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
