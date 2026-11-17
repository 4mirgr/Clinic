from io import BytesIO
from pathlib import Path

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access import manager_required, role_for
from .forms import AdviceForm, DocumentForm, PatientForm, VisitForm, normalize
from .models import Advice, AuditEvent, Document, Patient


def audit(request, action, target=''):
    AuditEvent.objects.create(actor=request.user, action=action, target=str(target))


@require_GET
def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('login_choice')
    role = role_for(request.user)
    if role is None:
        from .portal_api import account_for
        if account_for(request):
            return redirect('patient_portal')
        raise PermissionDenied
    if role == 'secretary':
        return render(request, 'clinic/secretary.html', {'section':'dashboard'})
    return render(request, 'clinic/dashboard.html', {
        'section':'dashboard','patient_count':Patient.objects.count(),
        'document_count':Document.objects.count(), 'advice_count':Advice.objects.count(),
        'recent_patients':Patient.objects.all()[:5],
        'recent_events':AuditEvent.objects.select_related('actor')[:5],
    })


@manager_required
@require_GET
def patients(request):
    q = normalize(request.GET.get('q','')[:200])
    records = Patient.objects.all()
    if q:
        phone = q.replace(' ','').replace('-','')
        if phone.startswith('+98'):
            phone = '0' + phone[3:]
        elif phone.startswith('0098'):
            phone = '0' + phone[4:]
        # Each word can match either name component: full-name searches work too.
        names = Q()
        for token in q.split():
            names &= Q(first_name__icontains=token) | Q(last_name__icontains=token)
        records = records.filter(names | Q(national_id__icontains=q) | Q(phone__icontains=phone))
    return render(request,'clinic/patients.html', {'section':'patients','q':q,'page':Paginator(records,20).get_page(request.GET.get('page'))})


@manager_required
@require_http_methods(['GET','POST'])
def patient_new(request):
    form = PatientForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            patient = form.save()
            audit(request,'patient.create',patient.pk)
        return redirect(patient)
    return render(request,'clinic/form.html',{'section':'patients','form':form,'title':'پرونده جدید','description':'مشخصات بیمار را ثبت کنید. کد ملی در صورت نداشتن می‌تواند خالی بماند.','back_url':'patients'})


def consented_activity(patient):
    from datetime import timedelta
    from django.utils import timezone
    from .models import PortalAccount
    account = PortalAccount.objects.filter(patient=patient, track_activity=True, share_activity=True).first()
    if not account:
        return []
    from django.db.models import Sum
    return account.site_activity.filter(day__gte=timezone.localdate()-timedelta(days=90)).values('kind','value','category').annotate(count=Sum('count')).order_by('-count')[:30]


@manager_required
@require_GET
def patient_detail(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    audit(request,'patient.view',pk)
    from .advice_views import history_page
    return render(request,'clinic/patient_detail.html',{'section':'patients','patient':patient,'visit_form':VisitForm(),'document_form':DocumentForm(),'portal_profile':getattr(patient,'portal_account',None),'portal_activity':consented_activity(patient),'advice_deliveries':history_page(request, patient.pk),'advice_packets':patient.advice_packets.all()[:20]})


@manager_required
@require_http_methods(['GET','POST'])
def patient_edit(request, pk):
    patient = get_object_or_404(Patient,pk=pk)
    form = PatientForm(request.POST if request.method == 'POST' else None, instance=patient)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            patient = form.save()
            audit(request,'patient.update',patient.pk)
        return redirect(patient)
    return render(request,'clinic/form.html',{'section':'patients','form':form,'title':'ویرایش مشخصات و سوابق','description':'یادداشت‌های ویزیت قبلی مستقل از این فرم باقی می‌مانند.','back_url':'patients'})


@manager_required
@require_POST
def visit_new(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    form = VisitForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            visit = form.save(commit=False)
            visit.patient, visit.author = patient, request.user
            visit.save()
            audit(request,'visit.create',visit.pk)
        return redirect(patient)
    return render(request,'clinic/form.html',{'section':'patients','form':form,'title':'ثبت شرح ویزیت','back_url':'patients'})


@manager_required
@require_POST
def document_new(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    form = DocumentForm(request.POST,request.FILES)
    if form.is_valid():
        document = form.save(commit=False)
        document.patient, document.uploaded_by = patient, request.user
        document.save()
        audit(request,'document.upload',document.pk)
        return redirect(patient)
    return render(request,'clinic/form.html',{'section':'patients','form':form,'title':'افزودن مدرک','description':'PDF، JPG یا PNG؛ حداکثر ۲۰ مگابایت. مشاهده‌گر DICOM هنوز اضافه نشده است.','multipart':True,'back_url':'patients'})


@manager_required
@require_GET
def document_download(request, pk):
    document = get_object_or_404(Document,pk=pk)
    try:
        stream = document.file.open('rb')
    except FileNotFoundError:
        raise Http404('فایل موجود نیست؛ پشتیبان ذخیره‌سازی بررسی شود.')
    audit(request,'document.download',pk)
    # Do not trust user filenames/content types; never render an uploaded file inline.
    return FileResponse(stream, as_attachment=True, filename=f'document-{document.pk}{Path(document.file.name).suffix}',content_type='application/octet-stream')


@manager_required
@require_GET
def advice_list(request):
    from .education_views import library_context
    return render(request, 'clinic/advice_list.html', library_context(request))


@manager_required
@require_http_methods(['GET','POST'])
def advice_edit(request, pk=None):
    advice = get_object_or_404(Advice,pk=pk) if pk else None
    form = AdviceForm(request.POST if request.method == 'POST' else None,instance=advice)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            advice = form.save(commit=False)
            advice.updated_by = request.user
            approve = form.cleaned_data['is_approved']
            advice.save()
            if approve and not advice.is_approved:
                advice.is_approved = True
                advice.save()
            audit(request,'advice.save',advice.pk)
        return redirect('advice_print', pk=advice.pk)
    return render(request,'clinic/form.html',{'section':'advice','form':form,'title':'ویرایش توصیه' if pk else 'توصیه جدید','description':'تیترها و بندها را در سطرهای جدا بنویسید. پیش از ارائه به بیمار، متن را بازبینی و تأیید کنید.','back_url':'advice'})


@manager_required
@require_GET
def advice_print(request, pk):
    advice = get_object_or_404(Advice,pk=pk)
    audit(request,'advice.print_view',pk)
    from .education_views import decorate
    return render(request,'clinic/advice_print.html',{'advice':decorate(advice)})


@manager_required
@require_GET
def advice_qr(request):
    image = qrcode.make(settings.CLINIC_SITE, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = BytesIO()
    image.save(buffer)
    return HttpResponse(buffer.getvalue(),content_type='image/svg+xml')


@manager_required
@require_GET
def activity(request):
    page = Paginator(AuditEvent.objects.select_related('actor'),40).get_page(request.GET.get('page'))
    return render(request,'clinic/activity.html',{'section':'activity','page':page})
