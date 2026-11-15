from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = 'Create a clinic manager or restricted secretary. Passwords are prompted, never command-line arguments.'

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('--role', required=True, choices=['manager','secretary'])

    def handle(self, *args, **options):
        User = get_user_model()
        username = options['username'].strip()
        if User.objects.filter(username=username).exists():
            raise CommandError('User exists; no account or role was changed. Use changepassword for password resets.')
        user = User(username=username)
        try:
            user.full_clean(exclude=['password'])
            password = getpass('Password (12+ characters): ')
            if password != getpass('Confirm password: '):
                raise CommandError('Passwords do not match.')
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError('; '.join(error.messages))
        with transaction.atomic():
            user.set_password(password)
            user.save()
            group, _ = Group.objects.get_or_create(name='clinic_' + options['role'])
            user.groups.add(group)
        self.stdout.write(self.style.SUCCESS('Account created with the requested role.'))
