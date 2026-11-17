"""Reviewed, atomic patient handout packets and an explicitly published summary."""
import base64
import hashlib
import json
import sqlite3
import time
import uuid
from io import BytesIO
from urllib.parse import urlencode

import qrcode
import qrcode.image.svg
from django import forms
from django.conf import settings
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, OperationalError, connection, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .access import manager_required, role_for
from .advice_catalog import search_advice
from .advice_text import SPECIALTIES, search_document, sections
from .models import Advice, AdviceDelivery, AdvicePacket, AuditEvent, Patient, PatientSummary
from .portal_api import PortalError, account_for

SALT='clinic.advice-packet.v1'
SUMMARY_FIELDS=[('history','خلاصه شرح حال'),('conditions','بیماری‌های قبلی و حساسیت‌ها'),('health_status','وضعیت کنونی سلامت'),('medications','داروهای مورد استفاده'),('progress','پیشرفت درمان و برنامه پیگیری')]


def decorate(item):
    item.sections=sections(item.body)
    item.search_document=search_document(item)
    return item


def qr_for(patient):
    path=reverse('patient_summary', args=[patient.pk])
    public_base=getattr(settings,'CLINIC_PUBLIC_URL',settings.CLINIC_SITE+'/dash').rstrip('/')
    url=public_base+path.removeprefix('/dash')
    buffer=BytesIO()
    qrcode.make(url,image_factory=qrcode.image.svg.SvgPathImage).save(buffer)
    return base64.b64encode(buffer.getvalue()).decode('ascii')


def library_context(request):
    query=request.GET.get('q','')[:200]
    specialty=request.GET.get('specialty','')[:40]
    visible=set(search_advice(query,specialty).values_list('pk',flat=True))
    return {'section':'advice','q':query,'specialty':specialty,'specialties':SPECIALTIES,
        'guides':[decorate(a) for a in Advice.objects.all()], 'visible_ids':visible,
        'patients':Patient.objects.all(), 'selected_patient':request.GET.get('patient',''),
        'qr_data':qr_for(Patient.objects.first()) if Patient.objects.exists() else ''}


class Selection(forms.Form):
    patient=forms.ModelChoiceField(queryset=Patient.objects.all())
    advice_ids=forms.ModelMultipleChoiceField(queryset=Advice.objects.all())


def payload_for(request):
    form=Selection(request.POST)
    ids=request.POST.getlist('advice_ids')
    if len(ids)>30 or len(ids)!=len(set(ids)) or not form.is_valid():
        return None
    records={str(a.pk):a for a in form.cleaned_data['advice_ids']}
    try:
        ordered=[records[str(uuid.UUID(key))] for key in ids]
    except (KeyError, ValueError):
        return None
    return {'actor':request.user.pk,'patient':str(form.cleaned_data['patient'].pk),
        'items':[[str(a.pk),a.updated_at.isoformat()] for a in ordered],'nonce':str(uuid.uuid4())}


def token_payload(request):
    try:
        payload=signing.loads(request.POST.get('review_token',''),salt=SALT,max_age=1800)
        if payload['actor'] != request.user.pk or not 1<=len(payload['items'])<=30:
            raise ValueError
        uuid.UUID(payload['patient']); uuid.UUID(payload['nonce'])
        if len({key for key,rev in payload['items']}) != len(payload['items']):
            raise ValueError
        for key,revision in payload['items']:
            uuid.UUID(key)
        return payload
    except (signing.BadSignature, ValueError, KeyError, TypeError):
        return None


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def reviewed_items(payload, lock=False):
    records=Advice.objects.all()
    if lock:
        records=records.select_for_update()
    found={str(a.pk):a for a in records.filter(pk__in=[x[0] for x in payload['items']]).order_by('pk')}
    if any(key not in found or found[key].updated_at.isoformat()!=rev for key,rev in payload['items']):
        raise ReviewConflict
    return [decorate(found[key]) for key,rev in payload['items']]


class ReviewConflict(Exception):
    pass


@manager_required
@require_POST
def prepare(request):
    payload=payload_for(request)
    if payload is None:
        return HttpResponse('بیمار و بین یک تا ۳۰ توصیه معتبر انتخاب کنید.',status=400)
    patient=get_object_or_404(Patient,pk=payload['patient'])
    try:
        guides=reviewed_items(payload)
    except ReviewConflict:
        return HttpResponse('کتابخانه تغییر کرده است؛ دوباره انتخاب کنید.',status=409)
    return render(request,'clinic/packet_review.html',{'section':'advice','patient':patient,
        'guides':guides,'review_token':signing.dumps(payload,salt=SALT,compress=True)})


def record_packet(payload,actor):
    for attempt in range(5):
        try:
            with transaction.atomic():
                existing=AdvicePacket.objects.filter(request_key=payload['nonce']).first()
                digest=fingerprint(payload)
                if existing:
                    if existing.selection_fingerprint != digest or existing.created_by_id != actor.pk:
                        raise ReviewConflict
                    return existing
                # Serialize competing packets in a deterministic source order. A
                # repeated POST may have waited while the first approved sources.
                list(Advice.objects.select_for_update().filter(pk__in=[x[0] for x in payload['items']]).order_by('pk').values_list('pk',flat=True))
                existing=AdvicePacket.objects.filter(request_key=payload['nonce']).first()
                if existing:
                    if existing.selection_fingerprint != digest or existing.created_by_id != actor.pk:
                        raise ReviewConflict
                    return existing
                guides=reviewed_items(payload)
                patient=get_object_or_404(Patient.objects.select_for_update(),pk=payload['patient'])
                packet=AdvicePacket.objects.create(patient=patient,patient_name=patient.full_name,
                    created_by=actor,request_key=payload['nonce'],selection_fingerprint=digest)
                for position,advice in enumerate(guides):
                    # Approval applies only after validating EVERY displayed revision.
                    revision=advice.updated_at
                    advice.is_approved=True
                    advice.updated_by=actor
                    advice.save()
                    AdviceDelivery.objects.create(packet=packet,position=position,patient=patient,advice=advice,
                        title=advice.title,title_en=advice.title_en,specialty=advice.specialty,
                        body=advice.body,tags=advice.tags,source=advice.source,source_metadata=advice.source_metadata,
                        advice_updated_at=revision,created_by=actor,request_key=uuid.uuid5(uuid.UUID(payload['nonce']),str(advice.pk)))
                AuditEvent.objects.create(actor=actor,action='advice.packet_record',target=str(packet.pk))
                return packet
        except IntegrityError:
            existing=AdvicePacket.objects.filter(request_key=payload['nonce']).first()
            if existing and existing.selection_fingerprint==fingerprint(payload) and existing.created_by_id==actor.pk:
                return existing
            raise ReviewConflict
        except OperationalError as error:
            code=getattr(error.__cause__,'sqlite_errorcode',0)
            if connection.vendor!='sqlite' or code & 0xff not in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED):
                raise
            if attempt==4:
                raise
            time.sleep(.025*2**attempt)


@manager_required
@require_POST
def confirm(request):
    payload=token_payload(request)
    if payload is None or request.POST.get('reviewed')!='on':
        return HttpResponse('بازبینی کامل و تأیید صریح پزشک لازم است؛ فرم ممکن است منقضی شده باشد.',status=400)
    try:
        packet=record_packet(payload,request.user)
    except ReviewConflict:
        return HttpResponse('متن از زمان بازبینی تغییر کرده است. به کتابخانه برگردید و دوباره بازبینی کنید.',status=409)
    except OperationalError:
        response=HttpResponse('ثبت هم‌زمان دیگری انجام می‌شود؛ همین فرم را دوباره ارسال کنید.',status=503)
        response['Retry-After']='1'
        return response
    return redirect(packet)


def readable_patient(request, patient_id):
    if not request.user.is_authenticated:
        return redirect(reverse('login_choice')+'?'+urlencode({'next':request.path}))
    role=role_for(request.user)
    if role=='secretary':
        raise PermissionDenied
    if role=='manager':
        return get_object_or_404(Patient,pk=patient_id)
    try:
        account=account_for(request,required=True)
    except PortalError as error:
        if error.status==401:
            return redirect(reverse('patient_portal')+'?'+urlencode({'next':request.path}))
        raise PermissionDenied
    if not account.patient_id or str(account.patient_id)!=str(patient_id):
        raise Http404
    return get_object_or_404(Patient,pk=account.patient_id)


def packet_context(packet):
    return {'packet':packet,'patient_name':packet.patient_name,'guides':[decorate(a) for a in packet.deliveries.order_by('position')],
        'qr_data':qr_for(packet.patient),'summary_url':reverse('patient_summary',args=[packet.patient_id])}


@require_GET
def packet_view(request,pk,pdf=False):
    packet=get_object_or_404(AdvicePacket.objects.select_related('patient'),pk=pk)
    patient=readable_patient(request,packet.patient_id)
    if isinstance(patient,HttpResponse):
        return patient
    context=packet_context(packet)
    AuditEvent.objects.create(actor=request.user,action='advice.packet_view',target=str(packet.pk))
    if pdf:
        from .education_pdf import pdf_response
        return pdf_response(context)
    return render(request,'clinic/advice_packet.html',context)


@manager_required
@require_POST
def draft_pdf(request):
    payload=token_payload(request)
    if payload is None:
        return HttpResponse('فرم نامعتبر یا منقضی است.',status=400)
    try:
        guides=reviewed_items(payload)
    except ReviewConflict:
        return HttpResponse('متن تغییر کرده است.',status=409)
    patient=get_object_or_404(Patient,pk=payload['patient'])
    from .education_pdf import pdf_response
    return pdf_response({'patient_name':patient.full_name,'guides':guides,'qr_data':qr_for(patient),'draft':True})


@require_GET
def summary(request,pk):
    patient=readable_patient(request,pk)
    if isinstance(patient,HttpResponse):
        return patient
    record=PatientSummary.objects.filter(patient=patient).first()
    data=record.published_data if record else {}
    AuditEvent.objects.create(actor=request.user,action='summary.view',target=str(pk))
    return render(request,'clinic/patient_summary.html',{'patient':patient,'shared':[(label,data.get(key,'')) for key,label in SUMMARY_FIELDS],
        'published_at':record.published_at if record and data else None,'manager':role_for(request.user)=='manager'})


class SummaryForm(forms.Form):
    publish=forms.BooleanField(required=False,label='این نسخه را برای بیمار منتشر می‌کنم')
    for key,label in SUMMARY_FIELDS:
        locals()[key]=forms.CharField(label=label,required=False,max_length=8000,widget=forms.Textarea(attrs={'rows':4}))
    del key,label


@manager_required
@require_http_methods(['GET','POST'])
def summary_edit(request,pk):
    patient=get_object_or_404(Patient,pk=pk)
    record=PatientSummary.objects.filter(patient=patient).first()
    form=SummaryForm(request.POST if request.method=='POST' else None,initial=record.draft_data if record else {})
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            record,_=PatientSummary.objects.select_for_update().get_or_create(patient=patient,defaults={'updated_by':request.user})
            record.draft_data={key:form.cleaned_data[key] for key,label in SUMMARY_FIELDS}
            record.updated_by=request.user
            if form.cleaned_data['publish']:
                record.published_data=dict(record.draft_data)
                record.published_by=request.user
                record.published_at=timezone.now()
            record.save()
            AuditEvent.objects.create(actor=request.user,action='summary.publish' if form.cleaned_data['publish'] else 'summary.draft',target=str(pk))
        return redirect('patient_summary',pk=pk)
    return render(request,'clinic/summary_form.html',{'patient':patient,'form':form,'section':'patients'})


@manager_required
@require_POST
def summary_withdraw(request,pk):
    with transaction.atomic():
        record=get_object_or_404(PatientSummary.objects.select_for_update(),patient_id=pk)
        record.published_data={}
        record.published_at=None
        record.published_by=None
        record.save()
        AuditEvent.objects.create(actor=request.user,action='summary.withdraw',target=str(pk))
    return redirect('patient_summary',pk=pk)
