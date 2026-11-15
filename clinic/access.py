from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


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
