"""Private patient advice snapshots; no external delivery or notification."""
import base64
import sqlite3
import time
import uuid
from io import BytesIO

import qrcode
import qrcode.image.svg
from django import forms
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .access import manager_required, role_for
from .forms import normalize
from .models import Advice, AdviceDelivery, AuditEvent, Patient
from .portal_api import PortalError, account_for


class DeliveryConfirmation(forms.Form):
    revision = forms.DateTimeField(widget=forms.HiddenInput)
    request_key = forms.UUIDField(widget=forms.HiddenInput)


def history_page(request, patient_id):
    records = AdviceDelivery.objects.filter(patient_id=patient_id).select_related('created_by')
    if role_for(request.user) == 'secretary':
        records = records.none()
    return Paginator(records, 20).get_page(request.GET.get('advice_page'))


@manager_required
@require_GET
def select_advice(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    query = normalize(request.GET.get('q', '')[:200])
    records = Advice.objects.filter(is_approved=True)
    if query:
        records = records.filter(Q(title__icontains=query) | Q(body__icontains=query) | Q(tags__icontains=query))
    return render(request, 'clinic/advice_select.html', {
        'section': 'patients', 'patient': patient, 'q': query,
        'page': Paginator(records, 20).get_page(request.GET.get('page')),
    })


def confirmation_page(request, patient, advice, form, status=200, conflict=False):
    return render(request, 'clinic/advice_confirm.html', {
        'section': 'patients', 'patient': patient, 'advice': advice,
        'form': form, 'conflict': conflict,
    }, status=status)


def matching_delivery(delivery, patient, advice, user):
    return delivery.patient_id == patient.pk and delivery.advice_id == advice.pk and delivery.created_by_id == user.pk


class AdviceConflict(Exception):
    pass


class AdviceBusy(Exception):
    pass


def record_snapshot(patient, advice_pk, user, revision, key):
    for attempt in range(5):
        try:
            with transaction.atomic():
                # PostgreSQL serializes against edits; SQLite retries the entire
                # deferred transaction if a competing reader wins the write.
                advice = get_object_or_404(Advice.objects.select_for_update(), pk=advice_pk)
                existing = AdviceDelivery.objects.filter(request_key=key).first()
                if existing:
                    if matching_delivery(existing, patient, advice, user):
                        return existing
                    raise AdviceConflict
                if not advice.is_approved or revision != advice.updated_at:
                    raise AdviceConflict
                delivery = AdviceDelivery.objects.create(
                    patient=patient, advice=advice, title=advice.title, body=advice.body,
                    tags=advice.tags, source=advice.source, advice_updated_at=advice.updated_at,
                    created_by=user, request_key=key,
                )
                AuditEvent.objects.create(actor=user, action='advice.record', target=str(delivery.pk))
                return delivery
        except IntegrityError:
            existing = AdviceDelivery.objects.filter(request_key=key).first()
            if existing is None:
                raise
            if existing.patient_id == patient.pk and existing.advice_id == advice_pk and existing.created_by_id == user.pk:
                return existing
            raise AdviceConflict
        except OperationalError as error:
            code = getattr(error.__cause__, 'sqlite_errorcode', 0)
            if connection.vendor != 'sqlite' or code & 0xff not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise
            if attempt == 4:
                raise AdviceBusy from error
            time.sleep(0.025 * 2 ** attempt)


@manager_required
@require_http_methods(['GET', 'POST'])
def confirm_advice(request, pk, advice_pk):
    patient = get_object_or_404(Patient, pk=pk)
    advice = get_object_or_404(Advice, pk=advice_pk)
    if request.method == 'GET':
        if not advice.is_approved:
            raise Http404
        form = DeliveryConfirmation(initial={'revision': advice.updated_at.isoformat(), 'request_key': uuid.uuid4()})
        return confirmation_page(request, patient, advice, form)

    form = DeliveryConfirmation(request.POST)
    if not form.is_valid():
        return confirmation_page(request, patient, advice, form, status=400)
    try:
        delivery = record_snapshot(patient, advice_pk, request.user, form.cleaned_data['revision'], form.cleaned_data['request_key'])
    except AdviceConflict:
        return confirmation_page(request, patient, advice, form, status=409, conflict=True)
    except AdviceBusy:
        form.add_error(None, 'ثبت هم‌زمان دیگری در حال انجام است. کمی بعد همین فرم را دوباره ارسال کنید.')
        response = confirmation_page(request, patient, advice, form, status=503)
        response['Retry-After'] = '1'
        return response
    return redirect(delivery)


@require_GET
def delivery_print(request, pk):
    if not request.user.is_authenticated:
        return redirect('login_choice')
    manager = role_for(request.user) == 'manager'
    records = AdviceDelivery.objects.select_related('patient', 'created_by')
    if not manager:
        if role_for(request.user) == 'secretary':
            raise PermissionDenied
        try:
            account = account_for(request, required=True)
        except PortalError as error:
            if error.status == 401:
                return redirect('patient_portal')
            raise PermissionDenied
        if not account.patient_id:
            raise Http404
        records = records.filter(patient_id=account.patient_id)
    delivery = get_object_or_404(records, pk=pk)
    AuditEvent.objects.create(actor=request.user, action='advice.record_view', target=str(delivery.pk))
    image = qrcode.make(settings.CLINIC_SITE, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = BytesIO()
    image.save(buffer)
    return render(request, 'clinic/advice_delivery_print.html', {
        'delivery': delivery, 'manager': manager,
        'qr_data': base64.b64encode(buffer.getvalue()).decode('ascii'),
    })
