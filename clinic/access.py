from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.conf import settings


def role_for(user):
    if not user.is_authenticated or not user.is_active:
        return None
    if user.is_superuser or user.groups.filter(name='clinic_manager').exists():
        return 'manager'
    if user.groups.filter(name='clinic_secretary').exists():
        return 'secretary'
    return None


def manager_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login_choice')
        if role_for(request.user) != 'manager':
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


def calendar_staff_required(view):
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        if not request.user.is_authenticated:
            return redirect('login_choice')
        if role_for(request.user) not in ('manager','secretary'):
            raise PermissionDenied
        return view(request,*args,**kwargs)
    return wrapped


def patient_staff_required(view):
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        role = role_for(request.user)
        if not request.user.is_authenticated:
            return redirect('login_choice')
        if role != 'manager' and not (getattr(settings,'SHARED_AUTH_ENABLED',False) and role == 'secretary'):
            raise PermissionDenied
        return view(request,*args,**kwargs)
    return wrapped


def booking_access_required(view):
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        request.booking_account = None
        if role_for(request.user) in ('manager','secretary'):
            return view(request,*args,**kwargs)
        from .portal_api import PortalError,account_for
        try:
            request.booking_account = account_for(request,required=True)
        except PortalError as error:
            if error.status == 401:
                if request.headers.get('Accept') == 'application/json':
                    from django.http import JsonResponse
                    return JsonResponse({'slots':[],'error':'ابتدا وارد حساب بیمار شوید.'},status=401)
                return redirect('patient_portal')
            raise PermissionDenied
        return view(request,*args,**kwargs)
    return wrapped
