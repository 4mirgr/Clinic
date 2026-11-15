from django.contrib.auth.models import Group,User
from django.test import Client,TestCase


class ThemeTests(TestCase):
    def test_anonymous_theme_cookie_is_saved_and_login_page_uses_it(self):
        response=self.client.post('/dash/preferences/theme/',{'theme':'dark','next':'/dash/login/'})
        self.assertRedirects(response,'/dash/login/',fetch_redirect_response=False)
        self.assertEqual(response.cookies['gerami_theme'].value,'dark')
        self.assertTrue(response.cookies['gerami_theme']['httponly'])
        self.assertContains(self.client.get('/dash/login/'),'data-theme="dark"')

    def test_authenticated_theme_follows_account_on_another_device(self):
        user=User.objects.create_user('assistant',password='Strong-test-only-73!')
        user.groups.add(Group.objects.create(name='clinic_secretary'))
        self.client.force_login(user)
        self.assertEqual(self.client.post('/dash/preferences/theme/',{'theme':'dark'}).status_code,302)
        other=Client();other.force_login(user)
        self.assertContains(other.get('/dash/'),'data-theme="dark"')
        self.assertEqual(other.get('/dash/patients/').status_code,403)
        other.post('/dash/preferences/theme/',{'theme':'light'})
        self.assertContains(self.client.get('/dash/'),'data-theme="light"')

    def test_invalid_theme_csrf_and_external_redirect_are_rejected(self):
        response=self.client.post('/dash/preferences/theme/',{'theme':'<script>'})
        self.assertEqual(response.status_code,400)
        self.assertNotIn('gerami_theme',response.cookies)
        self.assertEqual(Client(enforce_csrf_checks=True).post('/dash/preferences/theme/',{'theme':'dark'}).status_code,403)
        self.assertEqual(self.client.get('/dash/preferences/theme/').status_code,405)
        response=self.client.post('/dash/preferences/theme/',{'theme':'dark','next':'//evil.example/'})
        self.assertRedirects(response,'/dash/',fetch_redirect_response=False)

    def test_outside_dash_error_page_does_not_set_or_replace_clinic_csrf_cookie(self):
        response=Client().get('/favicon.ico')
        self.assertEqual(response.status_code,404)
        self.assertNotIn('gerami_csrf',response.cookies)
