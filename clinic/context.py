from django.conf import settings
from .access import role_for


def clinic_context(request):
    return {'clinic_name': settings.CLINIC_NAME, 'clinic_title': 'متخصص داخلی',
            'clinic_site': settings.CLINIC_SITE, 'clinic_role': role_for(request.user)}
