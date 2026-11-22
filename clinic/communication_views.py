"""Protected patient contact choices and physician-only outbox administration."""
import json
import re
import secrets
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from .access import manager_required, role_for
from .communication_models import CHANNELS, ContactPreference, PatientNotification, TelegramLinkChallenge
from .communications import PREFERENCE_FIELDS, digest, eligible, plan_reminders, preferences_data, readiness, setting, telegram_link_available, whatsapp_phone
from .models import AuditEvent, PortalAccount
from .portal_api import PortalError, account_for, answer, data_body, locked_account, rate


@require_POST
def telegram_link(request):
    """Issue a bearer pairing challenge only to the logged-in account owner."""
    try:
        account = account_for(request, True)
        if role_for(request.user) == 'secretary':
            raise PortalError('patient_account_required', 403)
        data_body(request, [])
        if not telegram_link_available():
            raise PortalError('telegram_link_unavailable', 503)
        rate(request, 'telegram-link', 8, str(account.pk))
        with transaction.atomic():
            account = locked_account(request, account)
            now = timezone.now()
            # One active challenge per account; neither raw token nor deep link
            # is stored or put in an audit record.
            TelegramLinkChallenge.objects.filter(account=account, consumed_at__isnull=True).update(consumed_at=now)
            raw = secrets.token_urlsafe(32)
            TelegramLinkChallenge.objects.create(account=account, token_digest=digest(raw), auth_version=account.auth_version, expires_at=now + timedelta(minutes=15))
        return answer({'url': f"https://t.me/{setting('TELEGRAM_BOT_USERNAME')}?start={raw}", 'expires_in': 900})
    except PortalError as error:
        return answer({'error': error.code}, error.status)


@csrf_exempt
@require_POST
def telegram_webhook(request):
    """Telegram-only callback; isolated secret-header authentication replaces CSRF.

    The only accepted message pairs a private chat with a short-lived token
    issued during the owner's authenticated session. No network/reply occurs.
    """
    secret = setting('TELEGRAM_WEBHOOK_SECRET')
    if not telegram_link_available() or len(secret) < 32 or not constant_time_compare(request.headers.get('X-Telegram-Bot-Api-Secret-Token', ''), secret):
        return answer({'error': 'forbidden'}, 403)
    try:
        length = int(request.META.get('CONTENT_LENGTH') or '0')
        if length > 8192 or length < 0 or len(request.body) > 8192:
            raise ValueError
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError
        message = data.get('message')
        if not isinstance(message, dict):
            # Updates unrelated to a private text message are safely ignored.
            return answer({'accepted': True})
        chat, sender = message.get('chat'), message.get('from')
        if not isinstance(chat, dict) or not isinstance(sender, dict):
            raise ValueError
        chat_id, sender_id = chat.get('id'), sender.get('id')
        if (chat.get('type') != 'private' or type(chat_id) is not int or type(sender_id) is not int
                or not 1000 <= chat_id <= 10**20 - 1 or chat_id != sender_id or sender.get('is_bot') is not False):
            raise ValueError
        command = message.get('text')
        if not isinstance(command, str):
            raise ValueError
        match = re.fullmatch(r'/start ([A-Za-z0-9_-]{43})', command)
        if not match:
            return answer({'accepted': True})
    except (ValueError, TypeError, UnicodeDecodeError):
        return answer({'error': 'invalid_update'}, 400)
    now = timezone.now()
    challenge = TelegramLinkChallenge.objects.filter(token_digest=digest(match.group(1)), consumed_at__isnull=True, expires_at__gt=now).first()
    if not challenge:
        return answer({'accepted': True})
    with transaction.atomic():
        # Match the credential/preferences lock order: user, account, challenge.
        user = User.objects.select_for_update(no_key=True).get(pk=challenge.account.user_id)
        account = PortalAccount.objects.select_for_update().get(pk=challenge.account_id)
        current = TelegramLinkChallenge.objects.select_for_update().filter(pk=challenge.pk, consumed_at__isnull=True, expires_at__gt=timezone.now()).first()
        if not current or not user.is_active or role_for(user) == 'secretary' or current.auth_version != account.auth_version:
            return answer({'accepted': True})
        preference, _ = ContactPreference.objects.select_for_update().get_or_create(account=account)
        preference.verified_telegram = str(chat_id)
        preference.save(update_fields=['verified_telegram', 'updated_at'])
        current.consumed_at = timezone.now()
        current.save(update_fields=['consumed_at'])
        # Changing the verified destination never silently opts the patient in.
        for record in PatientNotification.objects.filter(account=account, channel='telegram', status__in=['queued', 'failed']):
            _, reason = eligible(record)
            if reason:
                record.status, record.error_code = 'cancelled', reason
                record.save(update_fields=['status', 'error_code'])
        AuditEvent.objects.create(actor=user, action='communication.telegram_linked', target=str(account.pk))
    return answer({'accepted': True})


@require_http_methods(['GET', 'POST'])
def preferences(request):
    try:
        account = account_for(request, True)
        if role_for(request.user) == 'secretary':
            raise PortalError('patient_account_required', 403)
        if request.method == 'POST':
            data = data_body(request, PREFERENCE_FIELDS)
            if any(type(value) is not bool for value in data.values()):
                raise PortalError('invalid_fields')
            with transaction.atomic():
                account = locked_account(request, account)
                preference, _ = ContactPreference.objects.select_for_update().get_or_create(account=account)
                for field, value in data.items():
                    setattr(preference, field, value)
                preference.save()
                # Opt-out immediately invalidates queued work, including when
                # the dispatcher has not run since the preference change.
                for record in PatientNotification.objects.filter(account=account, status__in=['queued', 'failed']):
                    _, reason = eligible(record)
                    if reason:
                        record.status, record.error_code = 'cancelled', reason
                        record.save(update_fields=['status', 'error_code'])
                AuditEvent.objects.create(actor=request.user, action='communication.preferences', target=str(account.pk))
        return answer(preferences_data(account))
    except PortalError as error:
        return answer({'error': error.code}, error.status)


class VerifyContactForm(forms.Form):
    account = forms.ModelChoiceField(label='حساب بیمار', queryset=PortalAccount.objects.none())
    channel = forms.ChoiceField(label='کانال ارتباطی', choices=CHANNELS)
    destination = forms.CharField(label='نشانی تأییدشده', max_length=254, help_text='ایمیل همان حساب؛ شماره واتس‌اپ به شکل 98912…؛ یا شناسه عددی چت خصوصی تلگرام پس از شروع ربات توسط بیمار.')
    ownership_confirmed = forms.BooleanField(label='مالکیت این راه ارتباطی را مستقیماً با همین بیمار بررسی کرده‌ام.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = PortalAccount.objects.filter(user__is_active=True, patient__isnull=False).exclude(user__groups__name='clinic_secretary').select_related('user', 'patient').distinct()
        self.fields['account'].label_from_instance = lambda item: f'{item.patient.full_name} · {item.user.username}'

    def clean(self):
        data = super().clean()
        account, channel, target = data.get('account'), data.get('channel'), data.get('destination', '').strip()
        if not account or not channel:
            return data
        if channel == 'email' and target.casefold() != account.email.casefold():
            self.add_error('destination', 'ایمیل باید دقیقاً متعلق به همین حساب باشد.')
        if channel == 'whatsapp' and (not whatsapp_phone(account) or target.lstrip('+') != whatsapp_phone(account)):
            self.add_error('destination', 'شماره باید همان شماره همراه ثبت‌شده بیمار باشد؛ با پیش‌شماره ۹۸ و ارقام لاتین.')
        if channel == 'telegram' and not re.fullmatch(r'[1-9][0-9]{3,19}', target):
            self.add_error('destination', 'فقط شناسه عددی چت خصوصیِ بیمار پذیرفته می‌شود؛ گروه و نام کاربری کافی نیست.')
        data['destination'] = target.lstrip('+') if channel == 'whatsapp' else target
        return data


@manager_required
@require_http_methods(['GET', 'POST'])
def console(request):
    form = VerifyContactForm(request.POST if request.method == 'POST' and request.POST.get('action') == 'verify' else None, initial={'account':request.GET.get('account')})
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'verify' and form.is_valid():
            with transaction.atomic():
                account = PortalAccount.objects.select_for_update().get(pk=form.cleaned_data['account'].pk)
                preference, _ = ContactPreference.objects.select_for_update().get_or_create(account=account)
                setattr(preference, 'verified_' + ('whatsapp' if form.cleaned_data['channel'] == 'whatsapp' else form.cleaned_data['channel']), form.cleaned_data['destination'])
                preference.verified_by, preference.verified_at = request.user, timezone.now()
                preference.save()
                AuditEvent.objects.create(actor=request.user, action='communication.contact_verified', target=str(account.pk))
            messages.success(request, 'راه ارتباطی تأیید شد؛ ارسال فقط با انتخاب خود بیمار و تنظیم سرویس انجام می‌شود.')
            return redirect('communications')
        if action == 'plan':
            count = plan_reminders()
            AuditEvent.objects.create(actor=request.user, action='communication.planned', target=str(count))
            messages.success(request, f'{count} یادآوری تازه در صف قرار گرفت؛ از این صفحه پیامی ارسال نمی‌شود.')
            return redirect('communications')
        if action == 'retry':
            # Ambiguous/sent messages are deliberately excluded from retry.
            try:
                pk = int(request.POST.get('notification', ''))
            except ValueError:
                pk = 0
            count = PatientNotification.objects.filter(pk=pk, status='failed', attempts__lt=3).update(status='queued', due_at=timezone.now())
            messages.info(request, 'برای تلاش مجدد صف‌بندی شد.' if count else 'این مورد قابل تلاش مجدد نیست؛ نتیجه نامشخص باید بررسی شود.')
            return redirect('communications')
    channel_status = [{'key': key, 'label': label, 'configured': readiness(key)[0], 'reason': readiness(key)[1]} for key, label in CHANNELS]
    return render(request, 'clinic/communications.html', {'section': 'communications', 'form': form, 'channels': channel_status,
        'page': Paginator(PatientNotification.objects.select_related('patient', 'account'), 30).get_page(request.GET.get('page'))})
