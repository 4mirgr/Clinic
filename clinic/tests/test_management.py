from io import StringIO
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class AccountCommandTests(TestCase):
    def create(self, role, username, password):
        with patch('clinic.management.commands.create_clinic_user.getpass', return_value=password):
            call_command('create_clinic_user', username, role=role, stdout=StringIO())

    def test_creates_distinct_accounts_with_hashed_password_and_exact_role(self):
        for role,name in [('manager','dr.gerami'),('secretary','assistant')]:
            self.create(role,name,'Strong-test-only-74!')
            user=authenticate(username=name,password='Strong-test-only-74!')
            self.assertIsNotNone(user)
            self.assertFalse(user.is_superuser)
            self.assertEqual(list(user.groups.values_list('name',flat=True)),['clinic_'+role])
            self.assertNotEqual(user.password,'Strong-test-only-74!')

    def test_rejects_weak_password_and_does_not_overwrite_existing_user(self):
        with self.assertRaises(CommandError):
            self.create('manager','weak','123')
        self.assertFalse(User.objects.filter(username='weak').exists())
        self.create('secretary','assistant','Strong-test-only-74!')
        with self.assertRaises(CommandError):
            self.create('manager','assistant','Different-test-74!')
        self.assertIsNotNone(authenticate(username='assistant',password='Strong-test-only-74!'))
        self.assertFalse(User.objects.get(username='assistant').groups.filter(name='clinic_manager').exists())
