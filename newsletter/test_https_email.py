from unittest.mock import Mock, patch
from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings


@override_settings(BREVO_API_KEY='synthetic-test-key')
class HTTPSConfirmationTests(SimpleTestCase):
    def test_uses_https_fixed_provider_without_smtp_and_checks_acceptance(self):
        from newsletter.https_email import BrevoConfirmationBackend
        response=Mock(status_code=201);response.json.return_value={'messageId':'synthetic-accepted-id'}
        with patch('newsletter.https_email.requests.post',return_value=response) as post:
            result=BrevoConfirmationBackend().send_messages([EmailMessage('تأیید','متن آزمایشی','sender@example.test',['reader@example.test'])])
        self.assertEqual(result,1)
        self.assertEqual(post.call_args.args[0],'https://api.brevo.com/v3/smtp/email')
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        self.assertEqual(post.call_args.kwargs['json']['to'],[{'email':'reader@example.test'}])

    def test_provider_quota_or_ambiguous_acceptance_never_claims_success(self):
        from newsletter.https_email import BrevoConfirmationBackend
        for status,payload in [(429,{}),(500,{}),(201,{}),(201,{'messageId':True}),
                               (201,{'messageId':{'error':'invalid'}}),(201,{'messageId':'   '})]:
            response=Mock(status_code=status);response.json.return_value=payload
            with patch('newsletter.https_email.requests.post',return_value=response):
                with self.assertRaises(OSError):
                    BrevoConfirmationBackend().send_messages([EmailMessage('Test','Synthetic','sender@example.test',['reader@example.test'])])

    def test_transport_does_not_become_an_implicit_bulk_mailer(self):
        from newsletter.https_email import BrevoConfirmationBackend
        with patch('newsletter.https_email.requests.post') as post:
            with self.assertRaises(ValueError):
                BrevoConfirmationBackend().send_messages([EmailMessage('Test','Synthetic','sender@example.test',['one@example.test','two@example.test'])])
            self.assertFalse(post.called)

    def test_attachments_cannot_be_exported_by_the_confirmation_transport(self):
        from newsletter.https_email import BrevoConfirmationBackend
        message=EmailMessage('Test','Synthetic','sender@example.test',['reader@example.test'])
        message.attach('private.pdf',b'synthetic-private-document','application/pdf')
        with patch('newsletter.https_email.requests.post') as post:
            with self.assertRaises(ValueError):BrevoConfirmationBackend().send_messages([message])
            self.assertFalse(post.called)
