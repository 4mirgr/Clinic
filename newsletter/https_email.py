"""Single-recipient opt-in confirmations over HTTPS for hosts blocking SMTP."""
import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class BrevoConfirmationBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        messages = list(email_messages)
        if not messages:
            return 0
        if (len(messages) != 1 or len(messages[0].to) != 1 or messages[0].cc or messages[0].bcc
                or messages[0].attachments):
            raise ValueError('Only a single-recipient confirmation is supported.')
        if not settings.BREVO_API_KEY:
            raise OSError('Confirmation transport is not configured.')
        message = messages[0]
        payload = {'sender': {'email': message.from_email}, 'to': [{'email': message.to[0]}],
                   'subject': message.subject, 'textContent': message.body}
        try:
            response = requests.post('https://api.brevo.com/v3/smtp/email',
                headers={'api-key':settings.BREVO_API_KEY, 'Accept':'application/json'},
                json=payload, timeout=(3, 12), allow_redirects=False)
            message_id = response.json().get('messageId') if response.status_code == 201 else None
            accepted = isinstance(message_id, str) and bool(message_id.strip())
        except Exception:
            raise OSError('Confirmation transport did not confirm acceptance.') from None
        if not accepted:
            raise OSError('Confirmation transport did not confirm acceptance.')
        return 1
