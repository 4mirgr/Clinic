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
            response['Cache-Control'] = 'private, no-store, max-age=0'
            response['Pragma'] = 'no-cache'
            # Chromium sends Origin:null on form POSTs under no-referrer.
            # same-origin keeps external navigation private and permits Django's CSRF validation.
            response['Referrer-Policy'] = 'same-origin'
            response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
            response['Content-Security-Policy'] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
                "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            )
        return response
