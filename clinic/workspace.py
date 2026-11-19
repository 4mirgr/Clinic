"""Physician workspace data and protected clinical worklists."""
from datetime import timedelta, datetime, time

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access import manager_required, role_for
from .forms import PrescriptionReferenceForm
from .intake import INTAKE_FIELDS
from .jalali import format_jalali, today_tehran, TZ
from .models import Appointment, AuditEvent, Patient, PrescriptionReference, Visit

PROVIDER_LINKS=[
 ('drnext','دکترنکست','https://panel.drnext.ir/'),
 ('tamin','تأمین اجتماعی','https://ep.tamin.ir/'),
 ('ihio','بیمه سلامت','https://eservices.ihio.gov.ir/ihioerx/'),
]


def doctor_dashboard():
    today=today_tehran()
    start=timezone.make_aware(datetime.combine(today-timedelta(days=13),time.min),TZ)
    counts={}
    for created in Visit.objects.filter(created_at__gte=start).values_list('created_at',flat=True):
        day=timezone.localtime(created).date()
        counts[day]=counts.get(day,0)+1
    dates=[today-timedelta(days=13-i) for i in range(14)]
    ceiling=max([1,*counts.values()])
    points=' '.join(f'{12+i*27},{94-counts.get(day,0)*70/ceiling:.1f}' for i,day in enumerate(dates))
    from .models import Advice, Document
    return {'section':'dashboard','patient_count':Patient.objects.count(),'document_count':Document.objects.count(),
        'advice_count':Advice.objects.count(),'visits_count':Visit.objects.count(),
        'online_count':Visit.objects.filter(mode='online').count(),
        'followup_count':Visit.objects.filter(follow_up_on__isnull=False,follow_up_on__lte=today,follow_up_done=False).count(),
        'recent_patients':Patient.objects.annotate(last_visit=Max('visits__created_at')).order_by('-last_visit','-created_at')[:5],
        'today_appointments':Appointment.objects.filter(starts_at__date=today).exclude(status__in=['cancelled','conflict'])[:5],
        'recent_visits':Visit.objects.select_related('patient')[:5],
        'chart_points':points,'chart_total':sum(counts.values()),'today_label':format_jalali(today),
        'chart_start':format_jalali(dates[0]),'chart_end':format_jalali(today)}


def intake_context(account):
    if not account:
        return {'intake_sections':[],'intake_progress':0}
    sections=[{'key':key,'label':label,'value':getattr(account,key),'maximum':maximum} for key,label,maximum in INTAKE_FIELDS]
    complete=sum(bool(item['value'].strip()) for item in sections)
    latest=account.intake_submissions.first()
    return {'intake_sections':sections,'intake_progress':round(complete*100/len(sections)), 'intake_completed':complete,'intake_total':len(sections),'intake_saved_at':latest.created_at if latest else None}


@manager_required
@require_GET
def visits(request):
    query=request.GET.get('q','')[:200]
    records=Visit.objects.select_related('patient','author')
    if request.GET.get('followup')=='1':
        records=records.filter(follow_up_on__isnull=False,follow_up_on__lte=today_tehran(),follow_up_done=False)
    if query:
        for token in query.split():
            records=records.filter(Q(patient__first_name__icontains=token)|Q(patient__last_name__icontains=token)|Q(chief_complaint__icontains=token))
    mode=request.GET.get('mode','')
    if mode in ('online','in_person'):
        records=records.filter(mode=mode)
    return render(request,'clinic/visits.html',{'section':'visits','q':query,'mode':mode,'followup':request.GET.get('followup')=='1','page':Paginator(records,20).get_page(request.GET.get('page'))})


@manager_required
@require_http_methods(['GET','POST'])
def prescriptions(request):
    form=PrescriptionReferenceForm(request.POST if request.method=='POST' else None,initial={'patient':request.GET.get('patient'),'provider':'drnext'})
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            record=form.save(commit=False)
            record.author=request.user
            record.save()
            AuditEvent.objects.create(actor=request.user,action='prescription.reference',target=str(record.pk))
        return redirect(record.patient)
    import uuid
    try:
        selected=Patient.objects.filter(pk=uuid.UUID(request.GET.get('patient',''))).first()
    except ValueError:
        selected=None
    return render(request,'clinic/prescriptions.html',{'section':'prescriptions','form':form,'provider_links':PROVIDER_LINKS,'selected_patient':selected,'page':Paginator(PrescriptionReference.objects.select_related('patient'),20).get_page(request.GET.get('page'))})


@require_GET
def shared_account(request):
    from .google_signin import configured
    if request.user.is_authenticated and request.GET.get('manage')!='1':
        if role_for(request.user):
            return redirect('dashboard')
        from .portal_api import account_for
        if account_for(request):
            return redirect('patient_portal')
    return render(request,'clinic/shared_account.html',{'google_enabled':configured(),'google_linked':hasattr(request.user,'google_identity') if request.user.is_authenticated else False,'account_dashboard':'dashboard' if role_for(request.user) else 'patient_portal'})


@manager_required
@require_POST
def followup_done(request,pk):
    with transaction.atomic():
        visit=get_object_or_404(Visit.objects.select_for_update(),pk=pk)
        if visit.follow_up_on and not visit.follow_up_done:
            visit.follow_up_done=True
            visit.save(update_fields=['follow_up_done'])
            AuditEvent.objects.create(actor=request.user,action='visit.followup_done',target=str(pk))
    return redirect(visit.patient)
