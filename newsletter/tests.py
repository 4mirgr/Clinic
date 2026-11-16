import json
import re
from unittest.mock import patch

from django.apps import apps
from django.core import mail
from django.test import Client, TestCase, override_settings

API = '/dash/api/portal/'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   NEWSLETTER_ENABLED=True, NEWSLETTER_FROM_EMAIL='education@example.test',
                   NEWSLETTER_SITE_ORIGIN='https://website.example.test')
class NewsletterTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        response = self.post('signup', {'username':'reader-one','email':'reader@example.test',
            'display_name':'خواننده آزمایشی','password':'Synthetic newsletter password 937!'})
        self.assertEqual(response.status_code, 201)

    def post(self, route, data, client=None):
        client = client or self.client
        csrf = client.get(API+'session').json()['csrf_token']
        return client.post(API+route, json.dumps(data), content_type='application/json', HTTP_X_CSRFTOKEN=csrf)

    def subscribe(self):
        response = self.post('newsletter', {'subscribe':True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['newsletter']['status'], 'pending')
        self.assertEqual(len(mail.outbox), 1)
        return re.search(r'#confirm=([A-Za-z0-9_-]+)', mail.outbox[0].body).group(1)

    def test_signup_never_enrolls_or_creates_a_medical_record(self):
        response = self.client.get(API+'newsletter')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['newsletter']['status'], 'unsubscribed')
        self.assertEqual(apps.get_model('clinic','Patient').objects.count(), 0)
        self.assertEqual(apps.get_model('newsletter','Subscription').objects.count(), 0)

    def test_csrf_authentication_and_exact_fields_are_required(self):
        self.assertEqual(self.client.post(API+'newsletter', '{}', content_type='application/json').status_code, 403)
        self.assertEqual(self.post('newsletter', {'subscribe':True}, Client(enforce_csrf_checks=True)).status_code, 401)
        self.assertEqual(self.post('newsletter', {'subscribe':'yes'}).status_code, 400)
        self.assertEqual(self.post('newsletter', {'subscribe':True,'email':'other@example.test'}).status_code, 400)

    def test_email_confirmation_is_required_one_use_and_not_a_login(self):
        token = self.subscribe()
        sub = apps.get_model('newsletter','Subscription').objects.get()
        self.assertNotIn(token, sub.confirmation_hash)
        anon = Client(enforce_csrf_checks=True)
        response = self.post('newsletter/confirm', {'token':token}, anon)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['newsletter']['status'], 'active')
        self.assertIsNone(anon.get(API+'session').json()['user'])
        self.assertEqual(self.post('newsletter/confirm', {'token':token}, anon).status_code, 400)
        self.assertEqual(apps.get_model('clinic','Patient').objects.count(), 0)
        self.assertFalse(apps.get_model('clinic','PortalAccount').objects.get().track_activity)

    def test_disable_and_unsubscribe_work_without_an_email_provider(self):
        token = self.subscribe(); self.post('newsletter/confirm', {'token':token})
        from newsletter.services import unsubscribe_token
        sub = apps.get_model('newsletter','Subscription').objects.get()
        with override_settings(NEWSLETTER_ENABLED=False):
            response = self.post('newsletter/unsubscribe', {'token':unsubscribe_token(sub)}, Client(enforce_csrf_checks=True))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.client.get(API+'newsletter').json()['newsletter']['status'], 'unsubscribed')
            self.assertEqual(self.post('newsletter', {'subscribe':False}).status_code, 200)
            self.assertEqual(self.post('newsletter', {'subscribe':True}).status_code, 503)

    def test_expired_tokens_disabled_accounts_and_forged_tokens_are_rejected(self):
        token = self.subscribe()
        Subscription = apps.get_model('newsletter','Subscription')
        from django.utils import timezone
        Subscription.objects.update(confirmation_expires_at=timezone.now())
        self.assertEqual(self.post('newsletter/confirm', {'token':token}).status_code, 400)
        self.assertEqual(self.post('newsletter/unsubscribe', {'token':'forged'}).status_code, 400)
        self.assertNotContains(self.client.get(API+'newsletter'), token)

    def test_mail_failure_does_not_activate_or_claim_success(self):
        with patch('newsletter.services.EmailMultiAlternatives.send', side_effect=OSError('synthetic failure')):
            self.assertEqual(self.post('newsletter', {'subscribe':True}).status_code, 503)
        sub = apps.get_model('newsletter','Subscription').objects.get()
        self.assertEqual(sub.status, 'pending')

    def test_email_contains_only_general_opt_in_and_configured_origin(self):
        self.subscribe()
        message = mail.outbox[0]
        self.assertEqual(message.to, ['reader@example.test'])
        self.assertIn('https://website.example.test/newsletter/#confirm=', message.body)
        self.assertNotIn('reported_history', message.body)
        self.assertNotIn('/dash/patients/', message.body)
        self.assertNotIn('reader-one', message.body)

    def test_resending_revokes_the_old_link_and_disabled_accounts_cannot_confirm(self):
        old = self.subscribe()
        self.assertEqual(self.post('newsletter', {'subscribe':True}).status_code, 200)
        current = re.search(r'#confirm=([A-Za-z0-9_-]+)', mail.outbox[-1].body).group(1)
        self.assertEqual(self.post('newsletter/confirm', {'token':old}).status_code, 400)
        account = apps.get_model('clinic','PortalAccount').objects.get()
        account.user.is_active = False; account.user.save(update_fields=['is_active'])
        self.assertEqual(self.post('newsletter/confirm', {'token':current}, Client(enforce_csrf_checks=True)).status_code, 400)

    def test_owner_statistics_and_production_mail_gate(self):
        self.assertEqual(self.client.get(API+'admin/newsletter').status_code, 403)
        with override_settings(PRODUCTION=True):
            self.assertEqual(self.post('newsletter', {'subscribe':True}).status_code, 503)
