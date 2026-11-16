import tempfile
from pathlib import Path
from unittest.mock import patch
from django.apps import apps
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings


class WorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.doctor = User.objects.create_user('doctor', password='Test-long-pass!73')
        cls.doctor.groups.add(Group.objects.create(name='clinic_manager'))
        cls.secretary = User.objects.create_user('assistant', password='Test-long-pass!73')
        cls.secretary.groups.add(Group.objects.create(name='clinic_secretary'))

    def setUp(self):
        self.client.force_login(self.doctor)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.temp.name)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def create_patient(self, **changes):
        data = {'first_name':'علي', 'last_name':'كرمي', 'national_id':'۰۰۱۲۳۴۵۶۷۸', 'phone':'+۹۸۹۱۲۳۴۵۶۷۸۹', 'history':'سابقه حساسیت', 'medications':'', 'allergies':''}
        data.update(changes)
        response = self.client.post('/dash/patients/new/', data)
        self.assertEqual(response.status_code, 302, response.content[:600])
        return response.headers['Location']

    def test_create_and_search_normalizes_names_digits_and_phone(self):
        detail = self.create_patient()
        for q in ['علی', 'کرمی', '۰۰۱۲۳۴۵۶۷۸', '0012345678', '۰۹۱۲۳۴۵۶۷۸۹', '+989123456789']:
            response = self.client.get('/dash/patients/', {'q':q})
            self.assertContains(response, detail)
        self.assertNotContains(self.client.get('/dash/patients/', {'q':'بدون نتیجه'}), detail)
        patient = apps.get_model('clinic', 'Patient').objects.get()
        self.assertEqual(patient.first_name, 'علی')
        self.assertEqual(patient.phone, '09123456789')
        self.assertEqual(patient.national_id, '0012345678')

    def test_shared_website_profile_is_recalled_for_each_clinical_visit(self):
        reader = Client(enforce_csrf_checks=True)
        def post(route, data):
            import json
            csrf=reader.get('/dash/api/portal/session').json()['csrf_token']
            return reader.post('/dash/api/portal/'+route,json.dumps(data),content_type='application/json',HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(post('signup',{'username':'visit-reader','email':'visit@example.test','display_name':'علی کرمی','password':'Synthetic shared visit password 937!'}).status_code,201)
        self.assertEqual(apps.get_model('clinic','Patient').objects.count(),0)
        self.assertEqual(post('profile',{'first_name':'علي','last_name':'كرمي','phone':'۰۹۱۲۳۴۵۶۷۸۹','reported_history':'شرح خود بیمار'}).status_code,200)
        account=apps.get_model('clinic','PortalAccount').objects.get()
        patient=account.patient
        detail=patient.get_absolute_url()
        for query in ['علی کرمی','علي كرمي','۰۹۱۲۳۴۵۶۷۸۹','+989123456789']:
            self.assertContains(self.client.get('/dash/patients/',{'q':query}),detail)
        # The doctor records the identifier; a patient cannot claim an old record with it.
        patient.national_id='0012345678';patient.save(update_fields=['national_id'])
        self.assertContains(self.client.get('/dash/patients/',{'q':'۰۰۱۲۳۴۵۶۷۸'}),detail)
        for note in ['یادداشت ویزیت اول پزشک','یادداشت ویزیت دوم پزشک']:
            self.assertEqual(self.client.post(detail+'visits/new/',{'note':note}).status_code,302)
            self.assertContains(self.client.get(detail),note)
        self.assertEqual(patient.visits.count(),2)
        profile=reader.get('/dash/api/portal/profile').json()['profile']
        self.assertEqual(profile['reported_history'],'شرح خود بیمار')
        self.assertNotIn('یادداشت ویزیت',str(profile))

    def test_duplicate_national_id_and_invalid_identifiers_do_not_create_records(self):
        self.create_patient()
        for changes in [{'national_id':'0012345678'}, {'national_id':'12'}, {'national_id':'', 'phone':'123'}]:
            data = {'first_name':'رضا','last_name':'نمونه','national_id':'','phone':'09111111111', **changes}
            self.assertEqual(self.client.post('/dash/patients/new/', data).status_code, 200)
        self.assertEqual(apps.get_model('clinic','Patient').objects.count(), 1)

    def test_notes_are_appended_and_html_is_escaped(self):
        detail = self.create_patient()
        r = self.client.post(detail + 'visits/new/', {'note':'<script>alert(1)</script> شرح ویزیت'})
        self.assertEqual(r.status_code, 302)
        r = self.client.get(detail)
        self.assertContains(r, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(r, '<script>alert(1)</script>')
        self.client.post(detail + 'visits/new/', {'note':'ویزیت دوم'})
        self.assertEqual(apps.get_model('clinic','Visit').objects.count(), 2)

    def test_private_upload_download_and_direct_secretary_denial(self):
        detail = self.create_patient()
        r = self.client.post(detail + 'documents/new/', {'title':'آزمایش خون','category':'lab','file':SimpleUploadedFile('../../result.pdf', b'%PDF-1.7\nexample\n%%EOF', content_type='application/pdf')})
        self.assertEqual(r.status_code, 302)
        document = apps.get_model('clinic','Document').objects.get()
        self.assertNotIn('result', document.file.name)
        self.assertNotIn('..', document.file.name)
        url = f'/dash/documents/{document.pk}/download/'
        r = self.client.get(url)
        self.assertEqual(b''.join(r.streaming_content), b'%PDF-1.7\nexample\n%%EOF')
        self.assertIn('attachment', r.headers['Content-Disposition'])
        self.assertEqual(r.headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn('no-store', r.headers['Cache-Control'])
        self.client.force_login(self.secretary)
        for p in [detail, detail+'visits/new/', detail+'documents/new/', url]:
            for method in [self.client.get,self.client.post]:
                self.assertEqual(method(p).status_code,403)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code,302)
        self.assertEqual(self.client.get('/media/'+document.file.name).status_code,404)
        self.assertEqual(self.client.get('/dash/media/'+document.file.name).status_code,404)

    def test_upload_rejects_spoofed_unsupported_and_oversize_files(self):
        detail = self.create_patient()
        for filename, body in [('bad.pdf',b'<html>bad</html>'), ('bad.html',b'%PDF-1.7'), ('large.pdf',b'%PDF-'+b'x'*(20*1024*1024))]:
            r=self.client.post(detail+'documents/new/', {'title':'مدرک','category':'lab','file':SimpleUploadedFile(filename,body)})
            self.assertEqual(r.status_code,200)
        self.assertEqual(apps.get_model('clinic','Document').objects.count(),0)

    @override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
        'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
    def test_failed_staff_upload_removes_filesystem_bytes_after_metadata_rollback(self):
        detail=self.create_patient()
        with patch('clinic.views.audit',side_effect=RuntimeError('synthetic audit failure')):
            with self.assertRaises(RuntimeError):
                self.client.post(detail+'documents/new/',{'title':'مدرک ساختگی','category':'lab',
                    'file':SimpleUploadedFile('synthetic.pdf',b'%PDF-1.7\nsynthetic\n%%EOF')})
        self.assertEqual(apps.get_model('clinic','Document').objects.count(),0)
        self.assertFalse(any(p.is_file() for p in Path(self.temp.name).rglob('*')))

    def test_advice_is_searchable_editable_printable_with_private_qr(self):
        r=self.client.post('/dash/advice/new/', {'title':'توصیه رفلاکس','tags':'گوارش','body':'متن آموزشی آزمایشی برای بازبینی پزشک','source':'منبع آزمایشی','is_approved':'on'})
        self.assertEqual(r.status_code,302)
        advice=apps.get_model('clinic','Advice').objects.get()
        self.assertContains(self.client.get('/dash/advice/',{'q':'بازبینی'}), 'توصیه رفلاکس')
        r=self.client.get(f'/dash/advice/{advice.pk}/print/')
        self.assertContains(r, 'متن آموزشی آزمایشی')
        self.assertContains(r, 'drgerami-md.ir')
        self.assertContains(r, '/dash/advice/qr/')
        qr=self.client.get('/dash/advice/qr/')
        self.assertEqual(qr.status_code,200)
        self.assertEqual(qr.headers['Content-Type'],'image/svg+xml')
        self.assertIn(b'<svg',qr.content)
        self.assertEqual(self.client.post(f'/dash/advice/{advice.pk}/edit/', {'title':'عنوان جدید','tags':'','body':'متن جدید','source':'','is_approved':'on'}).status_code,302)
        self.assertContains(self.client.get(f'/dash/advice/{advice.pk}/print/'),'عنوان جدید')
        self.client.force_login(self.secretary)
        for p in [f'/dash/advice/{advice.pk}/edit/',f'/dash/advice/{advice.pk}/print/','/dash/advice/qr/']:
            self.assertEqual(self.client.get(p).status_code,403)

    def test_draft_advice_is_clearly_marked_and_empty_state_has_no_fake_patients(self):
        self.assertContains(self.client.get('/dash/'),'هنوز بیماری ثبت نشده')
        self.client.post('/dash/advice/new/',{'title':'پیش نویس','body':'نیازمند بررسی','tags':'','source':''})
        a=apps.get_model('clinic','Advice').objects.get()
        self.assertContains(self.client.get(f'/dash/advice/{a.pk}/print/'),'تأیید نشده')

    def test_patient_actions_are_audited_without_clinical_content(self):
        detail=self.create_patient()
        self.client.get(detail)
        self.client.post(detail+'visits/new/',{'note':'متن محرمانه ویزیت'})
        events=apps.get_model('clinic','AuditEvent').objects.all()
        self.assertGreaterEqual(events.count(),3)
        self.assertNotIn('متن محرمانه',str(list(events.values())))
        self.assertContains(self.client.get('/dash/activity/'),'doctor')

    def test_manager_can_edit_patient_but_secretary_cannot(self):
        detail=self.create_patient()
        response=self.client.post(detail+'edit/', {'first_name':'علی','last_name':'کرمی','phone':'09123456789','national_id':'0012345678','history':'سابقه به‌روز','medications':'داروی جدید','allergies':'حساسیت جدید'})
        self.assertEqual(response.status_code,302)
        self.assertContains(self.client.get(detail),'داروی جدید')
        self.assertEqual(apps.get_model('clinic','Patient').objects.count(),1)
        self.client.force_login(self.secretary)
        self.assertEqual(self.client.get(detail+'edit/').status_code,403)
        self.assertEqual(self.client.post(detail+'edit/',{}).status_code,403)

    def test_advice_search_accepts_arabic_letters_and_digits_preserving_paragraphs(self):
        self.client.post('/dash/advice/new/',{'title':'توصيه كبد ۲','body':'خط اول\n\nپيگيري ٣ روز بعد','tags':'آموزشي','source':''})
        for query in ['كبد','کبد','پيگيري','پیگیری','٣','۳','3','۲','2','آموزشی']:
            response=self.client.get('/dash/advice/',{'q':query})
            self.assertContains(response,'/print/',msg_prefix=query)
        advice=apps.get_model('clinic','Advice').objects.get()
        self.assertIn('\n\n',advice.body)
