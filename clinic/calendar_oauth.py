import secrets
import uuid

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_GET,require_POST
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport.requests import Request

from .access import manager_required
from .calendar_api import SCOPES,TOKEN_URI,configured
from .calendar_models import CalendarConnection,ScheduleSettings
from .models import AuditEvent


def make_flow(state=None,verifier=None):
    config = {'web':{'client_id':settings.GOOGLE_CLIENT_ID,'client_secret':settings.GOOGLE_CLIENT_SECRET,
                     'auth_uri':'https://accounts.google.com/o/oauth2/v2/auth','token_uri':TOKEN_URI,
                     'redirect_uris':[settings.GOOGLE_REDIRECT_URI]}}
    return Flow.from_client_config(config,scopes=SCOPES,state=state,redirect_uri=settings.GOOGLE_REDIRECT_URI,code_verifier=verifier,autogenerate_code_verifier=not bool(verifier))


@manager_required
@require_POST
def connect(request):
    if not configured():
        messages.error(request,'اتصال گوگل تنظیم نشده؛ تنظیمات امن OAuth توسط میزبان تکمیل شود.')
        return redirect('calendar')
    flow = make_flow()
    nonce = secrets.token_urlsafe(32)
    url,state = flow.authorization_url(access_type='offline',prompt='consent',include_granted_scopes='true',login_hint=settings.GOOGLE_CALENDAR_ACCOUNT,nonce=nonce)
    request.session['google_oauth'] = {'state':state,'verifier':flow.code_verifier,'nonce':nonce,'user_id':request.user.pk,'created_at':timezone.now().timestamp()}
    return redirect(url)


@manager_required
@require_GET
def callback(request):
    saved = request.session.pop('google_oauth',None)
    now = timezone.now().timestamp()
    if (not configured() or not saved or saved.get('user_id') != request.user.pk
        or not isinstance(saved.get('created_at'),(int,float)) or not 0 <= now-saved['created_at'] <= 600
        or not secrets.compare_digest(saved.get('state',''),request.GET.get('state',''))):
        messages.error(request,'درخواست اتصال معتبر نیست یا منقضی شده؛ اتصال را دوباره آغاز کنید.')
        return redirect('calendar')
    if request.GET.get('error') or not request.GET.get('code'):
        messages.error(request,'اجازه دسترسی کامل نشد؛ حسابی متصل نشد.')
        return redirect('calendar')
    try:
        flow = make_flow(state=saved['state'],verifier=saved['verifier'])
        flow.fetch_token(code=request.GET['code'],timeout=15)
        credentials = flow.credentials
        granted = credentials.granted_scopes or credentials.scopes or []
        if isinstance(granted,str):
            granted = granted.split()
        if not credentials.refresh_token or not set(SCOPES).issubset(set(granted)):
            raise ValueError('Missing offline consent or scopes')
        if not credentials.id_token:
            raise ValueError('Missing account identity')
        claims = id_token.verify_oauth2_token(credentials.id_token,Request(),audience=settings.GOOGLE_CLIENT_ID)
        email = claims.get('email','').strip().casefold()
        if (claims.get('email_verified') is not True or email != settings.GOOGLE_CALENDAR_ACCOUNT
            or not claims.get('sub') or not secrets.compare_digest(claims.get('nonce',''),saved.get('nonce',''))):
            raise ValueError('Wrong Google account or nonce')
        connection = CalendarConnection(pk=1,owner=request.user,calendar_id='primary',generation=uuid.uuid4(),active=True)
        connection.account_email,connection.google_subject = email,claims['sub']
        connection.set_refresh_token(credentials.refresh_token)
        ScheduleSettings.objects.get_or_create(pk=1)
        with transaction.atomic():
            ScheduleSettings.objects.select_for_update().get(pk=1)
            old = CalendarConnection.objects.filter(pk=1).first()
            if old and old.google_subject == connection.google_subject and old.account_email == email:
                connection.generation = old.generation
            CalendarConnection.objects.update_or_create(pk=1,defaults={
                'owner':request.user,'calendar_id':'primary','generation':connection.generation,
                'active':True,'account_email':email,'google_subject':connection.google_subject,
                'refresh_token_encrypted':connection.refresh_token_encrypted,
            })
    except Exception:
        # Provider exceptions may contain tokens. Do not log or display their repr/body.
        messages.error(request,'اتصال گوگل کامل نشد. تنظیمات OAuth و اجازه دسترسی آفلاین را بررسی کنید.')
        return redirect('calendar')
    AuditEvent.objects.create(actor=request.user,action='calendar.connect')
    messages.success(request,'تقویم گوگل متصل شد. پیش از رزرو، روزها و ساعت‌های کاری را تنظیم کنید.')
    return redirect('calendar')


@manager_required
@require_POST
def disconnect(request):
    ScheduleSettings.objects.get_or_create(pk=1)
    with transaction.atomic():
        ScheduleSettings.objects.select_for_update().get(pk=1)
        CalendarConnection.objects.filter(pk=1).update(active=False,refresh_token_encrypted='')
    request.session.pop('google_oauth',None)
    AuditEvent.objects.create(actor=request.user,action='calendar.disconnect')
    messages.success(request,'اتصال محلی قطع شد؛ نوبت‌های قبلی در گوگل خودکار حذف نمی‌شوند.')
    return redirect('calendar')
