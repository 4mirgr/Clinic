import tempfile
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from clinic.models import Document, Patient, PortalAccount


class PortalAuditRegressions(TestCase):
    def setUp(self):
        self.storage=tempfile.TemporaryDirectory();self.addCleanup(self.storage.cleanup)
        self.override=override_settings(MEDIA_ROOT=self.storage.name);self.override.enable();self.addCleanup(self.override.disable)
        self.member=User.objects.create_user('audit-member')
        self.patient=Patient.objects.create(first_name='بیمار',last_name='آزمایشی',phone='09123456789')
        self.account=PortalAccount.objects.create(user=self.member,email='audit@example.test',patient=self.patient,reported_history='متن بالینی خوداظهاری خصوصی')
        self.document=Document.objects.create(patient=self.patient,title='مدرک خصوصی',category='lab',file=SimpleUploadedFile('sample.pdf',b'%PDF-1.7\nsample\n%%EOF'),uploaded_by=self.member)
        self.url=f'/dash/api/portal/documents/{self.document.pk}/download'

    def login(self):
        self.client.force_login(self.member)
        session=self.client.session;session['portal_auth_version']=0;session.save()

    def test_secretary_linked_to_patient_is_denied_all_clinical_portal_data(self):
        self.member.groups.add(Group.objects.get_or_create(name='clinic_secretary')[0]);self.login()
        for path in ['/dash/api/portal/profile','/dash/api/portal/documents',self.url]:
            self.assertEqual(self.client.get(path).status_code,403,path)
        self.assertEqual(self.client.post('/dash/api/portal/profile',{'display_name':'نباید تغییر کند'},content_type='application/json').status_code,403)
        self.assertEqual(self.client.post('/dash/api/portal/documents',{}).status_code,403)
        self.assertNotContains(self.client.get('/dash/portal/'),'متن بالینی خوداظهاری خصوصی')

    def test_missing_private_file_returns_not_found(self):
        self.login();self.document.file.delete(save=False)
        self.assertEqual(self.client.get(self.url).status_code,404)

    def test_staff_with_portal_account_still_gets_short_session(self):
        self.member.groups.add(Group.objects.get_or_create(name='clinic_secretary')[0])
        self.member.set_password('Audit-pass-only-938!');self.member.save()
        response=self.client.post('/dash/api/portal/login',{'identifier':self.member.username,'password':'Audit-pass-only-938!'},content_type='application/json')
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.session.get_expiry_age(),1800)

    def test_staff_email_login_is_supported_only_for_unambiguous_identity(self):
        doctor=User.objects.create_user('audit-doctor',email='audit-doctor@example.test',password='Audit-pass-only-938!')
        doctor.groups.add(Group.objects.get_or_create(name='clinic_manager')[0])
        data={'identifier':'audit-doctor@example.test','password':'Audit-pass-only-938!'}
        self.assertEqual(self.client.post('/dash/api/portal/login',data,content_type='application/json').status_code,200)
        self.client.logout()
        self.assertEqual(self.client.post('/dash/api/portal/signup',{'username':'new-conflicting-patient','email':doctor.email.upper(),'display_name':'نمونه','password':'Signup-only-984!'},content_type='application/json').status_code,409)
        other=User.objects.create_user('ambiguous-account',email=doctor.email,password='Audit-pass-only-938!')
        PortalAccount.objects.create(user=other,email=doctor.email)
        self.assertEqual(self.client.post('/dash/api/portal/login',data,content_type='application/json').status_code,401)

    def test_recent_visited_patient_stays_visible_with_many_unvisited_profiles(self):
        from clinic.models import Visit
        from clinic.workspace import doctor_dashboard
        Visit.objects.create(patient=self.patient,author=self.member,note='ویزیت نمونه')
        for i in range(6):
            Patient.objects.create(first_name='تازه',last_name=str(i),phone='09123456789')
        self.assertIn(self.patient,list(doctor_dashboard()['recent_patients']))
