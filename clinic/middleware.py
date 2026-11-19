from django.conf import settings
from django.http import HttpResponseForbidden
from django.utils.crypto import constant_time_compare


class PrivateResponsesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        proxy_key = getattr(settings, 'CLINIC_PROXY_KEY', '')
        if request.path.startswith('/dash') and proxy_key and not constant_time_compare(request.headers.get('X-Clinic-Proxy-Key', ''), proxy_key):
            response = HttpResponseForbidden('Origin access denied.')
        else:
            response = self.get_response(request)
        if request.path.startswith('/dash'):
            # Chromium enforces form-action across POST redirects. Only these OAuth
            # initiation documents may navigate a submitted form to Google's consent origin.
            form_action = "'self' https://accounts.google.com" if request.path in ('/dash/calendar/','/dash/calendar/connect/','/dash/account/google/') else "'self'"
            response['Cache-Control'] = 'private, no-store, max-age=0'
            response['Pragma'] = 'no-cache'
            # Chromium sends Origin:null on form POSTs under no-referrer.
            # same-origin keeps external navigation private and permits Django's CSRF validation.
            response['Referrer-Policy'] = 'same-origin'
            response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
            response['Content-Security-Policy'] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
                f"object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action {form_action}"
            )
        return response
