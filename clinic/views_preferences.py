from django.conf import settings
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import UserPreference


@require_POST
def set_theme(request):
    theme = request.POST.get('theme')
    if theme not in ('light','dark'):
        return HttpResponseBadRequest('Invalid theme.')
    if request.user.is_authenticated:
        UserPreference.objects.update_or_create(user=request.user, defaults={'theme':theme})
    target = request.POST.get('next','/dash/')
    if not target.startswith('/dash/') or not url_has_allowed_host_and_scheme(target,{request.get_host()},require_https=request.is_secure()):
        target = '/dash/'
    response = redirect(target)
    response.set_cookie('gerami_theme',theme,max_age=31536000,path='/dash/',httponly=True,samesite='Lax',secure=settings.SESSION_COOKIE_SECURE)
    return response
