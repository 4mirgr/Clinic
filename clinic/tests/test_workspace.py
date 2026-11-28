from datetime import datetime, time, timedelta
from uuid import uuid4

from unittest.mock import Mock, patch
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from clinic.jalali import TZ, today_tehran
from clinic.models import Appointment, Patient, PortalAccount, PatientIntakeSubmission, PatientRecordChange, Visit, PrescriptionReference, GoogleIdentity


class WorkspaceTests(TestCase):
    def setUp(self):
        self.doctor=User.objects.create_user('workspace-doctor',password='Workspace-only-73!')
        self.doctor.groups.add(Group.objects.get_or_create(name='clinic_manager')[0])
        self.patient=Patient.objects.create(first_name='بیمار',last_name='نمونه',phone='09123456789',history='یادداشت خصوصی پزشک')
        self.member=User.objects.create_user('workspace-member',password='Workspace-only-73!')
        self.account=PortalAccount.objects.create(user=self.member,patient=self.patient,email='workspace@example.test')
        self.client.force_login(self.doctor)

    def member_login(self):
        self.client.force_login(self.member)
        session=self.client.session;session['portal_auth_version']=0;session.save()

    def test_structured_visits_preserve_old_notes_and_validate_vitals(self):
        url=self.patient.get_absolute_url()+'visits/new/'
        self.assertEqual(self.client.post(url,{'note':'یادداشت قدیمی'}).status_code,302)
        self.assertEqual(Visit.objects.get().mode,'in_person')
        data={'note':'شرح جدید','mode':'online','chief_complaint':'پیگیری','assessment':'ارزیابی پزشک','plan':'برنامه','systolic':'125','diastolic':'80','weight':'75.5','oxygen_saturation':'98','follow_up_on':'۱۴۰۵/۰۹/۰۱'}
        self.assertEqual(self.client.post(url,data).status_code,302)
        visit=Visit.objects.first()
        self.assertEqual(visit.mode,'online');self.assertEqual(visit.systolic,125)
        self.assertIsNotNone(visit.follow_up_on)
        self.client.post(url,{**data,'oxygen_saturation':'125'})
        self.assertEqual(Visit.objects.count(),2)
        self.assertContains(self.client.get('/dash/visits/?mode=online'),'پیگیری')
        self.client.post(url,{'note':'اندازه‌گیری مستقل','diastolic':'80'})
        self.assertContains(self.client.get(self.patient.get_absolute_url()),'— / 80 mmHg')
        self.member_login()
        self.assertEqual(self.client.get('/dash/visits/').status_code,403)
        self.assertEqual(self.client.post(url,data).status_code,403)

    def test_physician_record_edits_keep_before_and_after_only_in_private_record(self):
        data={'first_name':'بیمار','last_name':'نمونه','phone':'09123456789','history':'شرح تازه','medications':'داروی پزشک','allergies':''}
        self.assertEqual(self.client.post(self.patient.get_absolute_url()+'edit/',data).status_code,302)
        change=PatientRecordChange.objects.get()
        self.assertEqual(change.changes['history'],{'before':'یادداشت خصوصی پزشک','after':'شرح تازه'})
        self.client.post(self.patient.get_absolute_url()+'edit/',data)
        self.assertEqual(PatientRecordChange.objects.count(),1)
        with self.assertRaises(ValidationError):change.save()
        self.member_login()
        page=self.client.get('/dash/portal/')
        self.assertNotContains(page,'یادداشت خصوصی پزشک')
        self.assertNotContains(page,'داروی پزشک')

    def test_intake_versions_are_preserved_and_bad_input_is_atomic(self):
        self.member_login()
        url='/dash/api/portal/profile'
        data={'display_name':'بیمار نمونه','reported_family_history':'سابقه خانوادگی نمونه','reported_current_problem':'مشکل نمونه','reported_onset':'دو روز','reported_surgeries':'ندارم','reported_medications':'دارو و مقدار نمونه'}
        self.assertEqual(self.client.post(url,data,content_type='application/json').status_code,200)
        first=PatientIntakeSubmission.objects.get()
        self.assertEqual(first.data['reported_family_history'],'سابقه خانوادگی نمونه')
        self.client.post(url,data,content_type='application/json')
        self.assertEqual(PatientIntakeSubmission.objects.count(),1)
        self.client.post(url,{'reported_family_history':'نسخه جدید'},content_type='application/json')
        self.assertEqual(PatientIntakeSubmission.objects.count(),2)
        first.refresh_from_db();self.assertEqual(first.data['reported_family_history'],'سابقه خانوادگی نمونه')
        self.assertEqual(self.client.post(url,{'reported_onset':'x'*2001,'display_name':'نباید ذخیره شود'},content_type='application/json').status_code,400)
        self.member.refresh_from_db();self.assertNotEqual(self.member.first_name,'نباید ذخیره شود')
        self.patient.refresh_from_db();self.assertEqual(self.patient.history,'یادداشت خصوصی پزشک')
        with self.assertRaises(ValidationError):first.save()
        self.client.force_login(self.doctor)
        self.assertContains(self.client.get(self.patient.get_absolute_url()),'نسخه جدید')

    def test_first_edit_preserves_intake_saved_before_revision_history(self):
        self.account.reported_history='شرح بیمار پیش از ارتقا'
        self.account.reported_medications='داروی قبلی بیمار'
        self.account.save()
        self.member_login()
        response=self.client.post('/dash/api/portal/profile',{'display_name':'بیمار نمونه','reported_history':'شرح جدید'},content_type='application/json')
        self.assertEqual(response.status_code,200)
        snapshots=list(PatientIntakeSubmission.objects.order_by('created_at','pk'))
        self.assertEqual(len(snapshots),2)
        self.assertEqual(snapshots[0].data['reported_history'],'شرح بیمار پیش از ارتقا')
        self.assertEqual(snapshots[0].data['reported_medications'],'داروی قبلی بیمار')
        self.assertEqual(snapshots[1].data['reported_history'],'شرح جدید')

    def test_prescription_reference_is_staff_only_and_does_not_claim_delivery(self):
        self.assertEqual(self.client.get('/dash/prescriptions/?patient=not-a-uuid').status_code,200)
        page=self.client.get('/dash/prescriptions/')
        self.assertContains(page,'https://panel.drnext.ir/')
        self.assertNotContains(page,'<iframe')
        data={'patient':str(self.patient.pk),'provider':'drnext','reference':'EXAMPLE-123','note':'توضیح اختصاصی رهگیری آزمایشی'}
        self.assertEqual(self.client.post('/dash/prescriptions/',data).status_code,302)
        self.assertEqual(PrescriptionReference.objects.get().author,self.doctor)
        self.assertContains(self.client.get('/dash/prescriptions/'),'توضیح اختصاصی رهگیری آزمایشی')
        self.assertContains(self.client.get(self.patient.get_absolute_url()),'توضیح اختصاصی رهگیری آزمایشی')
        self.member_login()
        self.assertEqual(self.client.post('/dash/prescriptions/',data).status_code,403)
        self.assertNotContains(self.client.get('/dash/portal/'),'EXAMPLE-123')
        secretary=User.objects.create_user('workspace-secretary');secretary.groups.add(Group.objects.get_or_create(name='clinic_secretary')[0])
        self.client.force_login(secretary)
        self.assertEqual(self.client.get('/dash/prescriptions/').status_code,403)
        self.assertEqual(self.client.get('/dash/visits/').status_code,403)

    def test_prescriptions_opened_from_record_keep_patient_context(self):
        other = Patient.objects.create(first_name='بیمار', last_name='دوم', phone='09111111111')
        for patient, reference in [(self.patient, 'FIRST-RX'), (other, 'OTHER-RX')]:
            PrescriptionReference.objects.create(patient=patient, provider='drnext', reference=reference, author=self.doctor)
        url = f'/dash/prescriptions/?patient={self.patient.pk}'
        page = self.client.get(url)
        self.assertContains(page, 'FIRST-RX')
        self.assertNotContains(page, 'OTHER-RX')
        self.assertContains(self.client.get('/dash/prescriptions/'), 'OTHER-RX')
        data = {'patient': str(other.pk), 'provider': 'drnext', 'reference': 'NEW-RX'}
        rejected = self.client.post(url, data)
        self.assertIn('patient', rejected.context['form'].errors)
        self.assertFalse(PrescriptionReference.objects.filter(reference='NEW-RX').exists())
        data['patient'] = str(self.patient.pk)
        self.assertRedirects(self.client.post(url, data), self.patient.get_absolute_url())

    def test_today_schedule_shows_first_five_in_chronological_order(self):
        start = datetime.combine(today_tehran(), time(9), tzinfo=TZ)
        slots = [start + timedelta(hours=i) for i in range(6)]
        for slot in slots:
            Appointment.objects.create(patient=self.patient, created_by=self.doctor, starts_at=slot,
                ends_at=slot + timedelta(minutes=15), status='confirmed', connection_generation=uuid4())
        schedule = self.client.get('/dash/').context['today_appointments']
        self.assertEqual([visit.starts_at for visit in schedule], slots[:5])

    def test_shared_account_reuses_username_password_and_patient_session(self):
        self.client.logout()
        self.assertContains(self.client.get('/dash/account/'),'ورود با گوگل')
        response=self.client.post('/dash/api/portal/login',{'identifier':self.member.username,'password':'Workspace-only-73!'},content_type='application/json')
        self.assertEqual(response.status_code,200)
        self.assertRedirects(self.client.get('/dash/account/'),'/dash/portal/',fetch_redirect_response=False)
        self.assertEqual(self.client.get('/dash/portal/').status_code,200)
        self.assertContains(self.client.get('/dash/account/?manage=1'),'href="/dash/portal/"')


@override_settings(GOOGLE_AUTH_CLIENT_ID='isolated-client',GOOGLE_AUTH_CLIENT_SECRET='isolated-secret')
class GoogleSigninTests(TestCase):
    def begin(self):
        flow=Mock();flow.code_verifier='test-verifier';flow.authorization_url.return_value=('https://accounts.google.com/o/oauth2/v2/auth?state=test-state','test-state')
        with patch('clinic.google_signin.make_flow',return_value=flow):
            self.assertEqual(self.client.post('/dash/account/google/').status_code,302)
        return self.client.session['google_signin']

    def finish(self,nonce,**claims):
        flow=Mock();flow.credentials.id_token='test-only-id-token'
        identity={'iss':'https://accounts.google.com','aud':'isolated-client','sub':'subject-one','email':'google@example.test','email_verified':True,'nonce':nonce,'name':'نمونه گوگل',**claims}
        with patch('clinic.google_signin.make_flow',return_value=flow),patch('clinic.google_signin.id_token.verify_oauth2_token',return_value=identity):
            return self.client.get('/dash/account/google/callback/?state=test-state&code=test-code')

    def test_verified_google_signin_creates_only_patient_and_reuses_identity(self):
        state=self.begin();self.assertEqual(self.finish(state['nonce']).status_code,302)
        user=User.objects.get();self.assertFalse(user.has_usable_password());self.assertFalse(user.is_staff)
        self.assertFalse(user.groups.exists());self.assertEqual(PortalAccount.objects.count(),1)
        self.assertEqual(self.client.get('/dash/portal/').status_code,200)
        self.client.logout();state=self.begin();self.finish(state['nonce'])
        self.assertEqual(User.objects.count(),1);self.assertEqual(GoogleIdentity.objects.count(),1)

    def test_wrong_nonce_or_unverified_email_never_logs_in_or_creates_user(self):
        state=self.begin();self.finish('wrong-nonce');self.assertEqual(User.objects.count(),0)
        state=self.begin();self.finish(state['nonce'],email_verified=False);self.assertEqual(User.objects.count(),0)
        self.assertNotIn('_auth_user_id',self.client.session)
        self.assertRedirects(self.client.get('/dash/account/google/callback/?state=test-state&code=test-code'),'/dash/account/',fetch_redirect_response=False)

    def test_matching_email_does_not_implicitly_link_to_existing_patient_or_doctor(self):
        user=User.objects.create_user('existing',email='google@example.test')
        PortalAccount.objects.create(user=user,email='google@example.test')
        state=self.begin();self.finish(state['nonce'])
        self.assertFalse(GoogleIdentity.objects.exists());self.assertNotIn('_auth_user_id',self.client.session)
        self.client.force_login(user)
        session=self.client.session;session['portal_auth_version']=0;session.save()
        state=self.begin();self.finish(state['nonce'])
        self.assertEqual(GoogleIdentity.objects.get().user,user)

    def test_start_requires_csrf_and_callback_rejects_state_or_expired_request(self):
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/dash/account/google/').status_code,403)
        self.begin();self.client.get('/dash/account/google/callback/?state=wrong&code=test-code')
        self.assertNotIn('google_signin',self.client.session)
        state=self.begin();session=self.client.session;state['created_at']=timezone.now().timestamp()-601;session['google_signin']=state;session.save()
        self.finish(state['nonce']);self.assertFalse(User.objects.exists())

    def test_linking_google_rechecks_revoked_patient_session(self):
        user=User.objects.create_user('revoked-user',first_name='نمونه')
        account=PortalAccount.objects.create(user=user,email='revoked@example.test')
        self.client.force_login(user)
        session=self.client.session;session['portal_auth_version']=0;session.save()
        saved=self.begin()
        account.auth_version=1;account.save()
        self.finish(saved['nonce'])
        self.assertFalse(GoogleIdentity.objects.exists())
