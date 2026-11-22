import io
import os
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from clinic.models import AuditEvent, Patient, PortalAccount, SharedIdentity
from clinic.shared_identity import ISSUER, SharedIdentityError, resolve_user


class IdentityBindingTests(TestCase):
    def test_non_regular_token_path_is_rejected_without_waiting_for_writer(self):
        from clinic.management.commands.bind_shared_identity import read_token_file
        if not hasattr(os,'mkfifo'):
            self.skipTest('Named pipes are unavailable on this platform')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'token-pipe'
            os.mkfifo(path,0o600)
            with self.assertRaises(CommandError):read_token_file(str(path))

    def setUp(self):
        self.user=User.objects.create_user('explicit-local-user',email='explicit@example.test',password='Local-synthetic-only-73!')
        self.subject=uuid.uuid4()
        self.canonical={'id':str(self.subject),'email':self.user.email,'role':'user','name':'Synthetic shared name'}
        self.output=io.StringIO()

    def run_command(self,**options):
        call_command('bind_shared_identity',self.user.username,issuer=ISSUER,subject=str(self.subject),stdout=self.output,**options)

    def token_file(self,folder):
        path=Path(folder)/'access-token'
        path.write_text('synthetic.private.access-token')
        path.chmod(0o600)
        return str(path)

    def commit(self,folder,**overrides):
        options={'commit':True,'confirm_username':self.user.username,'session_token_file':self.token_file(folder),**overrides}
        self.run_command(**options)

    @patch('clinic.management.commands.bind_shared_identity.verified_account')
    def test_default_dry_run_never_contacts_provider_or_changes_any_account(self,verify):
        password=self.user.password
        self.run_command()
        verify.assert_not_called();self.user.refresh_from_db()
        self.assertEqual(self.user.password,password)
        self.assertFalse(SharedIdentity.objects.exists());self.assertFalse(PortalAccount.objects.exists())
        self.assertIn('DRY RUN',self.output.getvalue())

    @override_settings(SHARED_AUTH_ENABLED=False)
    @patch('clinic.management.commands.bind_shared_identity.verified_account')
    def test_standalone_mode_refuses_commit_without_disabling_local_password(self,verify):
        with tempfile.TemporaryDirectory() as folder,self.assertRaises(CommandError):self.commit(folder)
        verify.assert_not_called();self.user.refresh_from_db();self.assertTrue(self.user.has_usable_password())
        self.assertFalse(SharedIdentity.objects.exists())

    @override_settings(SHARED_AUTH_ENABLED=True)
    @patch('clinic.management.commands.bind_shared_identity.verified_account')
    def test_commit_binds_exact_user_and_preserves_patient_roles_with_fresh_signin(self,verify):
        group=Group.objects.create(name='clinic_manager');self.user.groups.add(group)
        self.canonical['role']='admin'
        patient=Patient.objects.create(first_name='Synthetic',last_name='Private patient',phone='09123456789')
        portal=PortalAccount.objects.create(user=self.user,email=self.user.email,patient=patient,site_role='admin',auth_version=5)
        old=timezone.now()-timedelta(minutes=1)
        verify.return_value=(self.canonical,old)
        with tempfile.TemporaryDirectory() as folder:self.commit(folder)
        identity=SharedIdentity.objects.get();self.assertEqual(identity.user,self.user)
        self.assertEqual(identity.subject,self.subject);self.assertEqual(identity.issuer,ISSUER)
        self.user.refresh_from_db();portal.refresh_from_db()
        self.assertFalse(self.user.has_usable_password());self.assertEqual(portal.patient,patient)
        self.assertEqual(portal.auth_version,6);self.assertEqual(identity.auth_version,6)
        self.assertTrue(self.user.groups.filter(pk=group.pk).exists());self.assertEqual(portal.site_role,'admin')
        self.assertEqual(AuditEvent.objects.get(action='shared.identity_bound').target,str(identity.pk))
        with self.assertRaises(SharedIdentityError):resolve_user(self.canonical,old)
        self.assertEqual(resolve_user(self.canonical,timezone.now()+timedelta(seconds=1))[0],self.user)
        self.assertNotIn('synthetic.private.access-token',self.output.getvalue())
        self.assertNotIn(patient.full_name,self.output.getvalue())

    @override_settings(SHARED_AUTH_ENABLED=True)
    @patch('clinic.management.commands.bind_shared_identity.verified_account')
    def test_chosen_local_doctor_without_portal_can_be_deliberately_bound(self,verify):
        self.user.groups.add(Group.objects.create(name='clinic_manager'))
        self.canonical['role']='admin';verify.return_value=(self.canonical,timezone.now())
        with tempfile.TemporaryDirectory() as folder:self.commit(folder)
        portal=PortalAccount.objects.get(user=self.user)
        self.assertEqual(portal.email,self.user.email);self.assertIsNone(portal.patient_id)
        self.assertEqual(portal.site_role,'admin');self.assertEqual(User.objects.count(),1)

    @override_settings(SHARED_AUTH_ENABLED=True)
    @patch('clinic.management.commands.bind_shared_identity.verified_account')
    def test_subject_or_role_mismatch_fails_before_all_writes(self,verify):
        for canonical in [{**self.canonical,'id':str(uuid.uuid4())},{**self.canonical,'role':'admin'}]:
            verify.return_value=(canonical,timezone.now())
            with tempfile.TemporaryDirectory() as folder,self.assertRaises(CommandError):self.commit(folder)
        self.assertFalse(SharedIdentity.objects.exists());self.assertFalse(PortalAccount.objects.exists())
        self.user.refresh_from_db();self.assertTrue(self.user.has_usable_password())

    def test_unknown_issuer_malformed_subject_and_unknown_username_never_create(self):
        for options in [{'issuer':'https://unrelated.example/auth/v1','subject':str(self.subject)}, {'issuer':ISSUER,'subject':'not-a-uuid'}]:
            with self.assertRaises(CommandError):call_command('bind_shared_identity',self.user.username,stdout=self.output,**options)
        with self.assertRaises(CommandError):call_command('bind_shared_identity','unknown-user',issuer=ISSUER,subject=str(self.subject),stdout=self.output)
        self.assertFalse(SharedIdentity.objects.exists());self.assertEqual(User.objects.count(),1)

    def test_existing_subject_or_user_binding_is_never_overwritten(self):
        other=User.objects.create_user('already-bound')
        identity=SharedIdentity.objects.create(user=other,issuer=ISSUER,subject=self.subject)
        with self.assertRaises(CommandError):self.run_command()
        identity.delete()
        SharedIdentity.objects.create(user=self.user,issuer=ISSUER,subject=uuid.uuid4())
        with self.assertRaises(CommandError):self.run_command()
        self.assertEqual(SharedIdentity.objects.count(),1)

    def test_privileged_inactive_or_ambiguous_local_roles_are_rejected(self):
        for field in ['is_staff','is_superuser','is_active']:
            original=getattr(self.user,field)
            setattr(self.user,field,not original);self.user.save()
            with self.assertRaises(CommandError):self.run_command()
            setattr(self.user,field,original);self.user.save()
        self.user.groups.add(Group.objects.create(name='clinic_manager'),Group.objects.create(name='clinic_secretary'))
        with self.assertRaises(CommandError):self.run_command()
        self.assertFalse(SharedIdentity.objects.exists())

    @override_settings(SHARED_AUTH_ENABLED=True)
    @patch('clinic.management.commands.bind_shared_identity.verified_account')
    def test_commit_needs_repeated_exact_username_and_safe_token_file(self,verify):
        for options in [{'confirm_username':'other'},{'confirm_username':self.user.username}]:
            with self.assertRaises(CommandError):self.run_command(commit=True,**options)
        with tempfile.TemporaryDirectory() as folder:
            filename=self.token_file(folder)
            Path(filename).chmod(0o644)
            with self.assertRaises(CommandError):self.run_command(commit=True,confirm_username=self.user.username,session_token_file=filename)
            Path(filename).chmod(0o600)
            link=Path(folder)/'token-symlink';link.symlink_to(filename)
            with self.assertRaises(CommandError):self.run_command(commit=True,confirm_username=self.user.username,session_token_file=str(link))
        verify.assert_not_called();self.assertFalse(SharedIdentity.objects.exists())

    @override_settings(SHARED_AUTH_ENABLED=True)
    @patch('clinic.management.commands.bind_shared_identity.verified_account')
    def test_provider_failure_and_contact_conflict_have_no_partial_migration(self,verify):
        verify.side_effect=SharedIdentityError('shared_identity_unavailable',503)
        with tempfile.TemporaryDirectory() as folder,self.assertRaises(CommandError):self.commit(folder)
        verify.side_effect=None;verify.return_value=({**self.canonical,'email':'different@example.test'},timezone.now())
        with tempfile.TemporaryDirectory() as folder,self.assertRaises(CommandError):self.commit(folder)
        self.assertFalse(SharedIdentity.objects.exists());self.assertFalse(PortalAccount.objects.exists())
        self.user.refresh_from_db();self.assertTrue(self.user.has_usable_password())

    @override_settings(SHARED_AUTH_ENABLED=True)
    @patch('clinic.management.commands.bind_shared_identity.verified_account')
    def test_another_patients_portal_is_never_selected_by_matching_email(self,verify):
        other=User.objects.create_user('other-patient')
        portal=PortalAccount.objects.create(user=other,email=self.user.email)
        verify.return_value=(self.canonical,timezone.now())
        with tempfile.TemporaryDirectory() as folder,self.assertRaises(CommandError):self.commit(folder)
        portal.refresh_from_db();self.assertEqual(portal.user,other)
        self.assertFalse(SharedIdentity.objects.exists());self.assertFalse(PortalAccount.objects.filter(user=self.user).exists())

    def test_existing_site_role_conflict_is_not_silently_rewritten(self):
        portal=PortalAccount.objects.create(user=self.user,email=self.user.email,site_role='admin')
        with self.assertRaises(CommandError):self.run_command()
        portal.refresh_from_db();self.assertEqual(portal.site_role,'admin')
