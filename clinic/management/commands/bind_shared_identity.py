"""Deliberate, provider-verified migration of an explicitly selected local user."""
import os
import stat
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from clinic.models import AuditEvent, PortalAccount, SharedIdentity
from clinic.shared_identity import ISSUER, SharedIdentityError, verified_account


def local_role(user):
    if not user.is_active or user.is_staff or user.is_superuser:
        raise CommandError('Inactive, staff and superuser accounts cannot be bound by this adapter.')
    groups = set(user.groups.filter(name__in=['clinic_manager', 'clinic_secretary']).values_list('name', flat=True))
    if len(groups) > 1:
        raise CommandError('Conflicting local clinical roles require separate operator review.')
    return 'admin' if 'clinic_manager' in groups else 'secretary' if 'clinic_secretary' in groups else 'user'


def check_local(user, issuer, subject):
    role = local_role(user)
    if SharedIdentity.objects.filter(issuer=issuer, subject=subject).exists() or SharedIdentity.objects.filter(user=user).exists():
        raise CommandError('The chosen subject or local user already has an identity binding; nothing changed.')
    portal = PortalAccount.objects.filter(user=user).first()
    if portal and portal.site_role != ('admin' if role == 'admin' else 'member'):
        raise CommandError('The existing website role conflicts with the clinical role; review roles separately.')
    return role, portal


def read_token_file(filename):
    """Avoid argv/history, symlinks, large reads and permissive token files."""
    try:
        fd = os.open(filename, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
                raise ValueError
            raw = stream.read(3802)
        token = raw.decode('ascii').strip()
        if not token or len(raw) > 3801 or len(token) > 3800:
            raise ValueError
        return token
    except (OSError, UnicodeError, ValueError):
        raise CommandError('The session token must be in an owner-only regular file with mode 0600; token contents were not logged.') from None


class Command(BaseCommand):
    help = 'Explicitly bind an existing local username to a verified shared issuer/UUID. Default: dry run with no network or writes.'

    def add_arguments(self, parser):
        parser.add_argument('username', help='Exact existing local username, selected by the operator; never inferred from email.')
        parser.add_argument('--issuer', required=True, help='Exact configured shared Auth issuer.')
        parser.add_argument('--subject', required=True, help='Exact canonical shared-account UUID, reviewed by the operator.')
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--commit', action='store_true')
        mode.add_argument('--dry-run', action='store_true')
        parser.add_argument('--confirm-username', help='For commit, repeat the exact selected username.')
        parser.add_argument('--session-token-file', help='For commit, path to a 0600 file containing the selected shared account access token. Never pass a token as an argument.')

    def handle(self, *args, **options):
        issuer, username = options['issuer'], options['username']
        if issuer != ISSUER:
            raise CommandError('Only the configured canonical issuer is accepted; no arbitrary endpoint is contacted.')
        try:
            subject = uuid.UUID(options['subject'])
        except (ValueError, TypeError, AttributeError):
            raise CommandError('A valid canonical subject UUID is required.') from None
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError('The exact selected local username does not exist; no account was created.') from None
        expected_role, _ = check_local(user, issuer, subject)
        if not options['commit']:
            self.stdout.write(f'DRY RUN: local account is eligible; required canonical role={expected_role}. No provider call, binding, password, role, session or patient change was made.')
            return
        if not getattr(settings, 'SHARED_AUTH_ENABLED', False):
            raise CommandError('Commit requires activated private shared mode; standalone passwords must remain usable until that migration.')
        if options.get('confirm_username') != username or not options.get('session_token_file'):
            raise CommandError('Commit requires the exact --confirm-username and --session-token-file; nothing changed.')
        token = read_token_file(options['session_token_file'])
        try:
            account, _ = verified_account(token)
        except SharedIdentityError:
            raise CommandError('The selected canonical session could not be verified; nothing changed and no token was logged.') from None
        finally:
            token = ''
        try:
            actual_subject = uuid.UUID(account['id'])
            email = account['email'].strip().lower()
            validate_email(email)
        except (KeyError, ValueError, TypeError, AttributeError, ValidationError):
            raise CommandError('The canonical account response is invalid; nothing changed.') from None
        if actual_subject != subject or account.get('role') != expected_role:
            raise CommandError('The verified canonical subject or role does not match the explicit migration target; nothing changed.')
        try:
            with transaction.atomic():
                # Keep credential/portal mutation lock order: user, then portal.
                user = User.objects.select_for_update().get(pk=user.pk, username=username)
                current_role, existing = check_local(user, issuer, subject)
                if current_role != account.get('role'):
                    raise CommandError('The local role changed during verification; nothing changed.')
                portal = PortalAccount.objects.select_for_update().filter(user=user).first()
                if (user.email and user.email.strip().casefold() != email.casefold()) or (portal and portal.email.casefold() != email.casefold()):
                    raise CommandError('Existing local contact data conflicts with the verified account; review the chosen mapping separately.')
                if PortalAccount.objects.exclude(user=user).filter(email__iexact=email).exists():
                    raise CommandError('The verified email belongs to another local portal; no identity or patient was matched by email.')
                if portal is None:
                    portal = PortalAccount.objects.create(user=user, email=email, site_role='admin' if current_role == 'admin' else 'member')
                portal.auth_version += 1
                portal.save(update_fields=['auth_version', 'updated_at'])
                cutoff = timezone.now()
                identity = SharedIdentity.objects.create(user=user, issuer=issuer, subject=subject, auth_version=portal.auth_version, revoked_before=cutoff)
                user.set_unusable_password()
                user.save(update_fields=['password'])
                AuditEvent.objects.create(action='shared.identity_bound', target=str(identity.pk))
        except (IntegrityError, User.DoesNotExist):
            raise CommandError('A concurrent account/binding change prevented migration; no partial binding was retained.') from None
        self.stdout.write(self.style.SUCCESS('Identity bound. Existing roles and patient link preserved; local password and old sessions invalidated. A fresh shared sign-in is required.'))
