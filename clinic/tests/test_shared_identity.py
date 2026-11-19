import uuid
from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.utils import timezone

from clinic.models import Patient, PortalAccount, SharedIdentity
from clinic.shared_identity import ISSUER, SharedIdentityError, resolve_user, verified_account


@override_settings(SHARED_AUTH_ENABLED=True)
class SharedIdentityTests(TestCase):
    def setUp(self):
        self.account={'id':str(uuid.uuid4()),'role':'user','email':'shared@example.test','name':'Shared User','username':'member'}
        self.started=timezone.now()-timedelta(minutes=1)

    def test_first_identity_has_no_password_or_guessed_patient(self):
        patient=Patient.objects.create(first_name='Unlinked',last_name='Patient',national_id='0084575948',phone='09123456789')
        user,portal=resolve_user(self.account,self.started)
        self.assertFalse(user.has_usable_password());self.assertIsNone(portal.patient_id)
        self.assertFalse(user.is_staff);self.assertFalse(user.groups.exists())
        self.assertEqual(SharedIdentity.objects.get(user=user).issuer,ISSUER)

    def test_authoritative_roles_change_on_next_request(self):
        self.account['role']='admin';user,_=resolve_user(self.account,self.started)
        self.assertTrue(user.groups.filter(name='clinic_manager').exists())
        self.account['role']='secretary';resolve_user(self.account,self.started)
        self.assertFalse(user.groups.filter(name='clinic_manager').exists());self.assertTrue(user.groups.filter(name='clinic_secretary').exists())
        self.account['role']='user';resolve_user(self.account,self.started);self.assertFalse(user.groups.exists())

    def test_existing_email_needs_explicit_link(self):
        User.objects.create_user('existing',email=self.account['email'],password='synthetic-existing-pass')
        with self.assertRaises(SharedIdentityError) as caught:resolve_user(self.account,self.started)
        self.assertEqual(caught.exception.status,409);self.assertEqual(SharedIdentity.objects.count(),0)

    def test_local_revocation_survives_local_cookie_deletion(self):
        user,portal=resolve_user(self.account,self.started)
        portal.auth_version+=1;portal.save(update_fields=['auth_version'])
        for _ in range(2):
            with self.assertRaises(SharedIdentityError):resolve_user(self.account,self.started)
        identity=SharedIdentity.objects.get(user=user);self.assertIsNotNone(identity.revoked_before)
        self.assertEqual(resolve_user(self.account,timezone.now()+timedelta(seconds=1))[0],user)

    @patch('clinic.shared_identity.requests.get')
    def test_only_owned_access_cookie_is_forwarded(self,get):
        response=Mock(status_code=200,content=b'{}');response.json.return_value={'authenticated':True,'account':{**self.account,'sessionStartedAt':self.started.isoformat()}};get.return_value=response
        account,_=verified_account('signed.synthetic.token');self.assertEqual(account['id'],self.account['id'])
        args,kwargs=get.call_args;self.assertEqual(args[0],'https://drgerami-md.ir/api/account/session')
        self.assertEqual(kwargs['headers']['Cookie'],'__Host-gerami-access=signed.synthetic.token');self.assertFalse(kwargs['allow_redirects'])
        response.status_code=401
        with self.assertRaises(SharedIdentityError):verified_account('signed.synthetic.token')

    @patch('clinic.shared_identity.verified_account')
    def test_secretary_patient_panel_and_manager_only_google(self,verify):
        verify.return_value=({**self.account,'role':'secretary'},self.started)
        self.client.cookies['__Host-gerami-access']='signed.synthetic.token'
        self.assertEqual(self.client.get('/dash/patients/').status_code,200)
        self.assertEqual(self.client.post('/dash/calendar/connect/').status_code,403)
        verify.return_value=(self.account,self.started)
        self.assertEqual(self.client.get('/dash/patients/').status_code,403)

    def test_native_password_entry_does_not_create_parallel_credentials(self):
        self.assertEqual(self.client.post('/dash/api/portal/signup',data='{}',content_type='application/json').status_code,409)
        self.assertEqual(User.objects.count(),0)
        self.assertIn('/pages/account.html',self.client.get('/dash/account/')['Location'])

    @patch('clinic.shared_identity.verified_account')
    def test_failed_verification_never_uses_old_local_manager(self,verify):
        user=User.objects.create_user('old',password='old-synthetic-pass');user.groups.add(Group.objects.create(name='clinic_manager'))
        self.client.force_login(user);self.client.cookies['__Host-gerami-access']='invalid.token'
        verify.side_effect=SharedIdentityError('shared_identity_unavailable',503)
        self.assertEqual(self.client.get('/dash/patients/').status_code,503)
