"""Google OpenID Connect sign-in; no Calendar scope and no implicit account linking."""
import secrets
import uuid
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow

from .access import role_for
from .models import AuditEvent, GoogleIdentity, PortalAccount
from .views_auth import safe_next

SCOPES=['openid','https://www.googleapis.com/auth/userinfo.email','https://www.googleapis.com/auth/userinfo.profile']


def configured():
    return bool(settings.GOOGLE_AUTH_CLIENT_ID and settings.GOOGLE_AUTH_CLIENT_SECRET)


def make_flow(state=None,verifier=None):
    config={'web':{'client_id':settings.GOOGLE_AUTH_CLIENT_ID,'client_secret':settings.GOOGLE_AUTH_CLIENT_SECRET,
        'auth_uri':'https://accounts.google.com/o/oauth2/v2/auth','token_uri':'https://oauth2.googleapis.com/token',
        'redirect_uris':[settings.GOOGLE_AUTH_REDIRECT_URI]}}
    return Flow.from_client_config(config,scopes=SCOPES,state=state,redirect_uri=settings.GOOGLE_AUTH_REDIRECT_URI,code_verifier=verifier,autogenerate_code_verifier=not bool(verifier))


@require_POST
def start(request):
    if not configured():
        messages.info(request,'ورود گوگل هنوز برای این محیط فعال نشده است.')
        return redirect(reverse('shared_account')+('?manage=1' if request.user.is_authenticated else ''))
    if request.user.is_authenticated and not role_for(request.user):
        from .portal_api import account_for, PortalError
        try:
            account_for(request,True)
        except PortalError:
            raise PermissionDenied
    flow=make_flow()
    nonce=secrets.token_urlsafe(32)
    url,state=flow.authorization_url(prompt='select_account',nonce=nonce,access_type='online')
    request.session['google_signin']={'state':state,'nonce':nonce,'verifier':flow.code_verifier,
        'user_id':request.user.pk if request.user.is_authenticated else None,
        'auth_hash':request.user.get_session_auth_hash() if request.user.is_authenticated else '',
        'created_at':timezone.now().timestamp(),'next':safe_next(request)}
    return redirect(url)


def resolve_identity(claims,user=None):
    """A matching email never grants another account's clinical data or roles."""
    subject=claims['sub']
    email=claims['email'].strip().casefold()
    identity=GoogleIdentity.objects.select_related('user').filter(subject=subject).first()
    if identity:
        if user is not None and identity.user_id!=user.pk:
            raise ValueError('Identity already linked')
        return identity.user
    if user is not None:
        if GoogleIdentity.objects.filter(user=user).exists():
            raise ValueError('An identity is already linked')
        GoogleIdentity.objects.create(user=user,subject=subject,email=email)
        return user
    if PortalAccount.objects.filter(email__iexact=email).exists() or User.objects.filter(email__iexact=email).exists():
        raise ValueError('Sign in with the existing account before linking Google')
    user=User.objects.create_user('patient_'+uuid.uuid4().hex[:16],email=email,first_name=str(claims.get('name',''))[:100])
    user.set_unusable_password()
    user.save(update_fields=['password'])
    PortalAccount.objects.create(user=user,email=email)
    GoogleIdentity.objects.create(user=user,subject=subject,email=email)
    return user


@require_GET
def callback(request):
    saved=request.session.pop('google_signin',None)
    now=timezone.now().timestamp()
    valid=bool(configured() and isinstance(saved,dict) and isinstance(saved.get('created_at'),(int,float))
        and 0<=now-saved['created_at']<=600 and saved.get('state')
        and secrets.compare_digest(saved['state'],request.GET.get('state',''))
        and saved.get('user_id')==(request.user.pk if request.user.is_authenticated else None))
    if valid and saved.get('user_id'):
        valid=secrets.compare_digest(saved.get('auth_hash',''),request.user.get_session_auth_hash())
    if not valid or request.GET.get('error') or not request.GET.get('code'):
        messages.error(request,'درخواست ورود نامعتبر یا منقضی است؛ دوباره تلاش کنید.')
        return redirect(reverse('shared_account')+('?manage=1' if request.user.is_authenticated else ''))
    try:
        flow=make_flow(state=saved['state'],verifier=saved['verifier'])
        flow.fetch_token(code=request.GET['code'],timeout=15)
        token=flow.credentials.id_token
        if not token:
            raise ValueError('Missing identity token')
        claims=id_token.verify_oauth2_token(token,Request(),audience=settings.GOOGLE_AUTH_CLIENT_ID)
        if (claims.get('iss') not in ('accounts.google.com','https://accounts.google.com')
            or claims.get('aud')!=settings.GOOGLE_AUTH_CLIENT_ID or claims.get('email_verified') is not True
            or not isinstance(claims.get('email'),str) or '@' not in claims['email'] or len(claims['email'])>254
            or not isinstance(claims.get('sub'),str) or not 1<=len(claims['sub'])<=255
            or not secrets.compare_digest(claims.get('nonce',''),saved['nonce'])):
            raise ValueError('Invalid identity claims')
        with transaction.atomic():
            owner=None
            if saved.get('user_id'):
                owner=User.objects.select_for_update().get(pk=saved['user_id'],is_active=True)
                linked=PortalAccount.objects.select_for_update().filter(user=owner).first()
                if linked and request.session.get('portal_auth_version')!=linked.auth_version:
                    raise ValueError('Revoked account session')
                if not secrets.compare_digest(owner.get_session_auth_hash(),saved['auth_hash']):
                    raise ValueError('Credentials changed')
            user=resolve_identity(claims,owner)
            user=User.objects.select_for_update().get(pk=user.pk)
            if not user.is_active:
                raise ValueError('Inactive account')
            login(request,user,backend='django.contrib.auth.backends.ModelBackend')
            account=PortalAccount.objects.select_for_update().filter(user=user).first()
            if account:
                request.session['portal_auth_version']=account.auth_version
            request.session.set_expiry(1800 if role_for(user) else 86400)
            AuditEvent.objects.create(actor=user,action='auth.google',target=str(user.pk))
    except Exception:
        # Never log authorization codes, provider tokens, or medical information.
        messages.error(request,'ورود گوگل کامل نشد. اگر با این ایمیل حساب دارید، ابتدا با رمز وارد شوید و سپس گوگل را متصل کنید.')
        return redirect(reverse('shared_account')+('?manage=1' if request.user.is_authenticated else ''))
    destination=saved.get('next','')
    if not destination.startswith('/dash/') or destination.startswith('//'):
        destination=''
    return redirect(destination or ('dashboard' if role_for(user) else 'patient_portal'))
