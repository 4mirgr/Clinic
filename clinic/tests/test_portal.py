import hashlib
import hmac
import json
import tempfile
import time

from django.apps import apps
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

API = '/dash/api/portal/'
PASSWORD = 'Test-only strong password 874!'


class PortalTests(TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.storage.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.client = Client(enforce_csrf_checks=True)

    def csrf(self, client=None):
        client = client or self.client
        response = client.get(API + 'session')
        self.assertEqual(response.status_code, 200)
        return response.json()['csrf_token']

    def post(self, path, data, client=None, **extra):
        client = client or self.client
        return client.post(API + path, json.dumps(data), content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf(client), **extra)

    def signup(self, name='patient-one', client=None):
        response = self.post('signup', {'username': name, 'email': name + '@example.test', 'display_name': 'کاربر آزمایشی', 'password': PASSWORD}, client)
        self.assertEqual(response.status_code, 201, response.content[:500])
        return response.json()['user']

    def complete(self):
        response = self.post('profile', {'display_name': 'کاربر آزمایشی', 'first_name': 'کاربر', 'last_name': 'آزمایشی', 'phone': '۰۹۱۲۳۴۵۶۷۸۹', 'reported_history': 'گفتهٔ خود بیمار'})
        self.assertEqual(response.status_code, 200, response.content[:400])
        return apps.get_model('clinic', 'PortalAccount').objects.get(user__username='patient-one')

    def test_registration_requires_csrf_and_does_not_grant_staff_authority(self):
        self.assertEqual(self.client.post(API + 'signup', '{}', content_type='application/json').status_code, 403)
        user = self.signup()
        self.assertEqual(user['role'], 'member')
        self.assertEqual(user['email_verified'], 0)
        self.assertNotIn('password', json.dumps(user))
        self.assertTrue(User.objects.get(username='patient-one').check_password(PASSWORD))
        session = self.client.get(API + 'session').json()
        self.assertEqual(session['user']['id'], user['id'])
        self.assertFalse(session['capabilities']['manageUsers'])
        self.assertEqual(self.client.get('/dash/portal/').status_code, 200)
        self.assertEqual(self.client.get('/dash/patients/').status_code, 403)
        self.assertEqual(self.post('signup', {'username':'bad-user', 'email':'bad@example.test', 'display_name':'Bad', 'password':PASSWORD, 'role':'owner'}).status_code, 400)

    def test_same_django_session_works_across_api_and_native_patient_portal(self):
        self.signup()
        self.post('logout', {})
        self.assertIsNone(self.client.get(API + 'session').json()['user'])
        self.assertEqual(self.client.get('/dash/portal/').status_code, 302)
        self.assertEqual(self.post('login', {'identifier':'patient-one', 'password':PASSWORD}).status_code, 200)
        self.assertEqual(self.client.get('/dash/portal/').status_code, 200)
        self.assertEqual(self.post('login', {'identifier':'patient-one', 'password':'wrong'}).status_code, 401)

    def test_profile_uses_the_exact_clinical_patient_without_implicit_matching(self):
        Patient = apps.get_model('clinic', 'Patient')
        existing = Patient.objects.create(first_name='دیگر', last_name='بیمار', phone='09123456789', history='یادداشت پزشک')
        self.signup()
        account = self.complete()
        self.assertNotEqual(account.patient_id, existing.pk)
        self.assertEqual(account.patient.phone, '09123456789')
        account.patient.history = 'یادداشت معتبر پزشک'
        account.patient.save()
        self.post('profile', {'display_name':'نام تازه', 'first_name':'نام', 'last_name':'تازه', 'phone':'09123456788', 'reported_history':'توضیح تازه بیمار'})
        account.refresh_from_db(); account.patient.refresh_from_db()
        self.assertEqual(account.patient.phone, '09123456788')
        self.assertEqual(account.patient.history, 'یادداشت معتبر پزشک')
        self.assertEqual(self.client.get(API + 'profile').json()['profile']['reported_history'], 'توضیح تازه بیمار')
        account.patient.phone = '09123456787'; account.patient.save()
        self.assertEqual(self.client.get(API + 'profile').json()['profile']['phone'], '09123456787')

    def test_patient_upload_is_private_and_unrelated_users_and_secretary_are_denied(self):
        self.signup(); account = self.complete()
        upload = self.client.post(API + 'documents', {'title':'مدرک آزمایشی', 'category':'lab', 'file':SimpleUploadedFile('../../result.pdf', b'%PDF-1.7\nexample\n%%EOF', content_type='application/pdf')}, HTTP_X_CSRFTOKEN=self.csrf())
        self.assertEqual(upload.status_code, 201, upload.content[:400])
        document = apps.get_model('clinic', 'Document').objects.get()
        self.assertEqual(document.patient_id, account.patient_id)
        self.assertNotIn('result', document.file.name)
        url = upload.json()['document']['download_url']
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('no-store', response['Cache-Control'])
        other = Client(enforce_csrf_checks=True); self.signup('other-patient', other)
        self.assertEqual(other.get(url).status_code, 404)
        secretary = User.objects.create_user('secretary', password=PASSWORD)
        secretary.groups.add(Group.objects.create(name='clinic_secretary')); self.client.force_login(secretary)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(f'/dash/documents/{document.pk}/download/').status_code, 403)
        self.assertEqual(Client().get('/dash/media/' + document.file.name).status_code, 404)

    def test_patient_upload_validates_content_and_enforces_its_smaller_limit(self):
        self.signup(); self.complete()
        for name, value in [('fake.pdf', b'<html>bad</html>'), ('fake.png', b'\x89PNG\r\n\x1a\nnot-an-image'), ('large.pdf', b'%PDF-' + b'x' * (5 * 1024 * 1024))]:
            response = self.client.post(API + 'documents', {'title':'آزمون', 'category':'lab', 'file':SimpleUploadedFile(name, value)}, HTTP_X_CSRFTOKEN=self.csrf())
            self.assertEqual(response.status_code, 400)
        self.assertEqual(apps.get_model('clinic', 'Document').objects.count(), 0)

    def test_activity_requires_opt_in_can_be_erased_and_never_contains_identifiers(self):
        self.signup()
        event = {'kind':'search', 'value':' فشار   خون ', 'category':'سلامت عمومی'}
        self.assertEqual(self.post('activity', event).status_code, 200)
        Activity = apps.get_model('clinic', 'SiteActivity')
        self.assertEqual(Activity.objects.count(), 0)
        self.assertEqual(self.post('privacy', {'track_activity':True, 'share_activity':False}).status_code, 200)
        self.post('activity', event); self.post('activity', event)
        self.assertEqual(Activity.objects.count(), 1)
        self.assertEqual(Activity.objects.get().count, 2)
        for value in ['09123456789', 'person@example.test', 'https://example.test/secret']:
            self.post('activity', {**event, 'value':value})
        self.assertEqual(Activity.objects.count(), 1)
        self.assertEqual(self.client.get(API + 'activity').json()['events'][0]['value'], 'فشار خون')
        response = self.post('privacy', {'track_activity':False, 'share_activity':True})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['privacy']['share_activity'])
        self.assertEqual(Activity.objects.count(), 0)
        self.post('activity', event); self.assertEqual(Activity.objects.count(), 0)

    def test_password_change_revokes_another_browser_session(self):
        self.signup(); other = Client(enforce_csrf_checks=True)
        self.assertEqual(self.post('login', {'identifier':'patient-one', 'password':PASSWORD}, other).status_code, 200)
        self.assertEqual(self.post('password', {'current_password':PASSWORD, 'password':'Another strong secret 937!'}).status_code, 200)
        self.assertIsNone(other.get(API + 'session').json()['user'])
        self.assertIsNotNone(self.client.get(API + 'session').json()['user'])

    def test_public_directory_and_owner_header_forgery_are_denied(self):
        self.signup()
        self.assertEqual(self.client.get(API + 'admin/users', HTTP_X_WEBSITE_OWNER='github:208800626').status_code, 403)
        self.assertEqual(self.post('admin/users/unknown', {'role':'owner'}, HTTP_X_WEBSITE_OWNER='github:208800626').status_code, 403)

    @override_settings(CLINIC_PROXY_KEY='test-bridge-key-' * 4)
    def test_signed_owner_directory_cannot_elevate_clinical_permissions(self):
        proxy = {'HTTP_X_CLINIC_PROXY_KEY':'test-bridge-key-' * 4}
        # Website-owner management uses authenticated server assertions, not browser CSRF exemptions.
        account_user = User.objects.create_user('signed-patient', password=PASSWORD)
        account = apps.get_model('clinic', 'PortalAccount').objects.create(user=account_user, email='signed@example.test')
        def signed(path, data=None):
            raw = b'' if data is None else json.dumps(data).encode()
            method = 'GET' if data is None else 'POST'; stamp = str(int(time.time()))
            message = '\n'.join([stamp, method, API+path, hashlib.sha256(raw).hexdigest(), 'github:208800626'])
            signature = hmac.new(proxy['HTTP_X_CLINIC_PROXY_KEY'].encode(), message.encode(), hashlib.sha256).hexdigest()
            # Normal browser session CSRF is still mandatory for mutations, including proxied owner actions.
            token = self.client.get(API+'session', **proxy).json()['csrf_token']
            headers = {**proxy, 'HTTP_X_WEBSITE_OWNER':'github:208800626', 'HTTP_X_WEBSITE_TIMESTAMP':stamp, 'HTTP_X_WEBSITE_SIGNATURE':signature, 'HTTP_X_CSRFTOKEN':token}
            return self.client.get(API+path, **headers) if data is None else self.client.post(API+path, raw, content_type='application/json', **headers)
        patient = apps.get_model('clinic', 'Patient').objects.create(first_name='Test', last_name='Patient', phone='09111111111')
        account.patient = patient; account.save()
        response = signed('admin/users')
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertEqual(response.json()['total'], 1)
        response = signed('admin/users/clinic:'+str(account.pk), {'role':'admin', 'status':'active', 'phone':'09123456789'})
        self.assertEqual(response.status_code, 200, response.content[:500])
        account.refresh_from_db(); self.assertEqual(account.site_role, 'admin')
        patient.refresh_from_db(); self.assertEqual(patient.phone, '09123456789')
        account_user.refresh_from_db(); self.assertFalse(account_user.is_staff); self.assertEqual(account_user.groups.count(), 0)

    def test_ranked_topics_and_clinician_sharing_require_separate_consent(self):
        self.signup(); account = self.complete()
        self.post('privacy', {'track_activity':True, 'share_activity':False})
        for value in ['قلب', 'فشار خون', 'فشار خون']:
            self.post('activity', {'kind':'search', 'value':value, 'category':'سلامت قلب'})
        self.assertEqual(self.client.get(API+'activity').json()['topics'][0]['total'], 3)
        doctor = User.objects.create_user('topic-doctor', password=PASSWORD)
        doctor.groups.add(Group.objects.create(name='clinic_manager'))
        clinician = Client(); clinician.force_login(doctor)
        url = f'/dash/patients/{account.patient_id}/'
        self.assertNotContains(clinician.get(url), 'سلامت قلب')
        self.post('privacy', {'track_activity':True, 'share_activity':True})
        self.assertContains(clinician.get(url), 'سلامت قلب')
        self.post('privacy', {'track_activity':True, 'share_activity':False})
        self.assertNotContains(clinician.get(url), 'سلامت قلب')

    def test_password_whitespace_is_not_silently_changed(self):
        password = '  Test-only password 783!  '
        response = self.post('signup', {'username':'space-user','email':'space@example.test','display_name':'Test','password':password})
        self.assertEqual(response.status_code, 201)
        self.post('logout', {})
        self.assertEqual(self.post('login', {'identifier':'space-user','password':password}).status_code, 200)

    def test_unicode_report_limits_support_real_persian_text(self):
        self.signup()
        value = 'م' * 10000
        response = self.post('profile', {'display_name':'Test', 'reported_history':value, 'reported_medications':'م'*5000, 'reported_allergies':'م'*5000})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['profile']['reported_history'], value)

    def test_native_forms_never_put_medical_fields_in_a_get_query(self):
        from html.parser import HTMLParser
        self.signup()
        class Forms(HTMLParser):
            methods = []
            def handle_starttag(self, tag, attrs):
                if tag == 'form':
                    self.methods.append(dict(attrs).get('method', 'get').lower())
        parser = Forms(); parser.feed(self.client.get('/dash/portal/').content.decode())
        self.assertTrue(parser.methods)
        self.assertEqual(set(parser.methods), {'post'})

    def test_retention_job_erases_inactive_accounts_old_history(self):
        from datetime import timedelta
        from io import StringIO
        from django.core.management import call_command
        from django.utils import timezone
        self.signup()
        account = apps.get_model('clinic', 'PortalAccount').objects.get(user__username='patient-one')
        Activity = apps.get_model('clinic', 'SiteActivity')
        Activity.objects.create(account=account, kind='search', value='old', day=timezone.localdate()-timedelta(days=91))
        Activity.objects.create(account=account, kind='search', value='recent', day=timezone.localdate())
        call_command('purge_portal_activity', stdout=StringIO())
        self.assertEqual(list(Activity.objects.values_list('value', flat=True)), ['recent'])
