import hashlib
from datetime import timedelta

from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import role_for
from .models import LoginThrottle


class RoleLoginForm(AuthenticationForm):
    def __init__(self, *args, role, **kwargs):
        self.role = role
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'نام کاربری'
        self.fields['password'].label = 'رمز عبور'
        self.fields['username'].widget.attrs.update(autocomplete='username', dir='ltr')
        self.fields['password'].widget.attrs.update(autocomplete='current-password', dir='ltr')

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if role_for(user) != self.role:
            raise ValidationError('نام کاربری، رمز عبور یا نوع دسترسی صحیح نیست.')


def login_choice(request):
    if role_for(request.user):
        return redirect('dashboard')
    return render(request, 'clinic/login_choice.html')


def portal_login(request, role):
    if request.method not in ('GET', 'POST'):
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['GET', 'POST'])
    if role_for(request.user):
        return redirect('dashboard')
    form = RoleLoginForm(request, data=request.POST if request.method == 'POST' else None, role=role)
    status = 200
    if request.method == 'POST':
        # Account-level lock persists across workers/restarts. Never store attempted credentials.
        # Use the exact NFKC/strip normalization used by Django authentication.
        # Otherwise fullwidth spellings of the same username bypass the lock.
        username = form.fields['username'].to_python(request.POST.get('username', ''))
        key = hashlib.sha256(username.casefold().encode()).hexdigest()
        now = timezone.now()
        with transaction.atomic():
            throttle, _ = LoginThrottle.objects.get_or_create(key=key, defaults={'expires': now + timedelta(minutes=15)})
            throttle = LoginThrottle.objects.select_for_update().get(pk=throttle.pk)
            if throttle.expires <= now:
                throttle.failures = 0
                throttle.expires = now + timedelta(minutes=15)
            if throttle.failures >= 5:
                status = 429
                form.add_error(None, 'تلاش‌های ناموفق زیاد است. پس از ۱۵ دقیقه دوباره امتحان کنید.')
            elif form.is_valid():
                throttle.delete()
                login(request, form.get_user())
                request.session.set_expiry(1800)
                return redirect('dashboard')
            else:
                throttle.failures += 1
                throttle.save(update_fields=['failures', 'expires'])
    response = render(request, 'clinic/login.html', {'form': form, 'portal_role': role}, status=status)
    if status == 429:
        response['Retry-After'] = '900'
    return response


@require_POST
def sign_out(request):
    logout(request)
    return redirect('login_choice')
