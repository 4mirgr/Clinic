from django.contrib.auth.models import Group, User
from django.test import Client, TestCase


class AccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user('doctor', password='Test-long-pass!73')
        cls.manager.groups.add(Group.objects.create(name='clinic_manager'))
        cls.secretary = User.objects.create_user('secretary', password='Test-long-pass!73')
        cls.secretary.groups.add(Group.objects.create(name='clinic_secretary'))
        cls.stranger = User.objects.create_user('unassigned', password='Test-long-pass!73')

    def sign_in(self, role='manager', username='doctor', password='Test-long-pass!73'):
        return self.client.post(f'/dash/login/{role}/', {'username': username, 'password': password})

    def test_anonymous_dash_requires_login_and_root_is_unhandled(self):
        self.assertRedirects(self.client.get('/dash/'), '/dash/login/', fetch_redirect_response=False)
        self.assertEqual(self.client.get('/').status_code, 404)

    def test_both_portals_render_and_manager_can_login(self):
        for path in ['/dash/login/', '/dash/login/manager/', '/dash/login/secretary/']:
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertRedirects(self.sign_in(), '/dash/', fetch_redirect_response=False)
        self.assertContains(self.client.get('/dash/'), 'پیشخوان')

    def test_secretary_cannot_use_manager_portal(self):
        response = self.sign_in(username='secretary')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_manager_cannot_login_through_secretary_portal(self):
        self.assertEqual(self.sign_in(role='secretary').status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_secretary_can_login_but_cannot_read_or_post_clinical_routes(self):
        self.assertRedirects(self.sign_in(role='secretary', username='secretary'), '/dash/', fetch_redirect_response=False)
        self.assertContains(self.client.get('/dash/'), 'دسترسی محدود')
        for path in ['/dash/patients/', '/dash/patients/new/', '/dash/advice/', '/dash/advice/new/', '/dash/activity/']:
            for method in [self.client.get, self.client.post]:
                self.assertEqual(method(path).status_code, 403, path)

    def test_unassigned_user_is_denied(self):
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get('/dash/').status_code, 403)

    def test_removing_role_revokes_existing_session(self):
        self.client.force_login(self.manager)
        self.manager.groups.clear()
        self.assertEqual(self.client.get('/dash/patients/').status_code, 403)

    def test_inactive_user_cannot_login(self):
        self.manager.is_active = False
        self.manager.save()
        self.sign_in()
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_and_logout_require_csrf_and_logout_is_post_only(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/dash/login/manager/', {'username':'doctor', 'password':'Test-long-pass!73'}).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get('/dash/logout/').status_code, 405)
        client.force_login(self.manager)
        self.assertEqual(client.post('/dash/logout/').status_code, 403)
        self.assertRedirects(self.client.post('/dash/logout/'), '/dash/login/', fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_five_failures_temporarily_lock_account_even_with_correct_password(self):
        for _ in range(5):
            self.sign_in(password='wrong')
        self.assertEqual(self.sign_in().status_code, 429)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_external_next_is_ignored(self):
        response = self.client.post('/dash/login/manager/?next=https://evil.example', {'username':'doctor', 'password':'Test-long-pass!73'})
        self.assertRedirects(response, '/dash/', fetch_redirect_response=False)

    def test_authenticated_pages_are_private(self):
        self.client.force_login(self.manager)
        response = self.client.get('/dash/')
        self.assertIn('no-store', response.headers.get('Cache-Control', ''))
        self.assertEqual(response.headers.get('X-Frame-Options'), 'DENY')
        self.assertIn("default-src 'self'", response.headers.get('Content-Security-Policy', ''))

    def test_cloudflare_origin_key_is_required_when_configured(self):
        from django.test import override_settings
        with override_settings(CLINIC_PROXY_KEY='a-private-origin-key-for-test-only-123456'):
            self.assertEqual(self.client.get('/dash/login/').status_code,403)
            self.assertEqual(self.client.get('/dash/login/',HTTP_X_CLINIC_PROXY_KEY='wrong').status_code,403)
            self.assertEqual(self.client.get('/dash/login/',HTTP_X_CLINIC_PROXY_KEY='a-private-origin-key-for-test-only-123456').status_code,200)

    def test_unicode_equivalent_usernames_share_the_same_login_lock(self):
        # Django accepts fullwidth/NFKC-equivalent usernames; all must share one bucket.
        for username in ['doctor','ｄｏｃｔｏｒ','doctor','ｄｏｃｔｏｒ','doctor']:
            self.sign_in(username=username,password='wrong')
        for username in ['doctor','ｄｏｃｔｏｒ']:
            self.assertEqual(self.sign_in(username=username).status_code,429)
            self.assertNotIn('_auth_user_id',self.client.session)
