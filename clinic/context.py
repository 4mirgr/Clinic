from django.conf import settings
from .access import role_for
from .models import UserPreference


def clinic_context(request):
    theme = request.COOKIES.get('gerami_theme', '')
    if request.user.is_authenticated:
        preference = UserPreference.objects.filter(user=request.user).values_list('theme', flat=True).first()
        theme = preference or theme
    if theme not in ('light','dark'):
        theme = ''
    return {'clinic_name': settings.CLINIC_NAME, 'clinic_title': 'متخصص داخلی',
            'clinic_site': settings.CLINIC_SITE, 'clinic_role': role_for(request.user),
            'interface_theme': theme, 'preview_export': settings.CLINIC_PREVIEW_EXPORT,
            'shared_patient_staff': getattr(settings,'SHARED_AUTH_ENABLED',False) and role_for(request.user)=='secretary',
            'shared_auth_enabled': getattr(settings,'SHARED_AUTH_ENABLED',False),
            'inside_clinic':request.path == '/dash' or request.path.startswith('/dash/')}
