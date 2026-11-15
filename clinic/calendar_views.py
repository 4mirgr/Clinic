from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404,redirect,render
from django.views.decorators.http import require_GET,require_POST,require_http_methods
from django.utils import timezone

from .access import calendar_staff_required
from .calendar_api import CalendarUnavailable,configured
from .calendar_forms import AvailabilityForm,BookingForm,ScheduleForm
from .calendar_models import Appointment,AvailabilityOverride,CalendarConnection,ScheduleSettings
from .jalali import JalaliDateField,TO_PERSIAN,today_tehran
from .models import AuditEvent
from .scheduling import BookingError,available_slots,book_selected_slot,request_cancellation,sync_appointment


@calendar_staff_required
@require_GET
def calendar_home(request):
    schedule,_ = ScheduleSettings.objects.get_or_create(pk=1)
    connection = CalendarConnection.objects.filter(pk=1,active=True).first()
    all_appointments = request.GET.get('view') == 'all'
    records = Appointment.objects.select_related('patient')
    if all_appointments:
        records = records.order_by('-starts_at')
    else:
        records = records.filter(Q(status__in=['pending','cancel_pending','conflict_cancelling','conflict','attention'])|Q(status='confirmed',ends_at__gte=timezone.now())).order_by('starts_at')
    page = Paginator(records,25).get_page(request.GET.get('page'))
    return render(request,'clinic/calendar.html',{'section':'calendar','schedule':schedule,'connection':connection,'google_configured':configured(),'form':BookingForm(actor=request.user),'appointments':page.object_list,'page':page,'calendar_all':all_appointments})


@calendar_staff_required
@require_http_methods(['GET','POST'])
def schedule_settings(request):
    ScheduleSettings.objects.get_or_create(pk=1)
    with transaction.atomic():
        schedule = ScheduleSettings.objects.select_for_update().get(pk=1)
        form = ScheduleForm(request.POST if request.method == 'POST' else None,instance=schedule)
        if request.method == 'POST' and form.is_valid():
            form.save()
            AuditEvent.objects.create(actor=request.user,action='calendar.hours_update')
            messages.success(request,'ساعت‌های کاری ذخیره شد. منطقه زمانی: تهران.')
            return redirect('calendar')
    return render(request,'clinic/form.html',{'section':'calendar','form':form,'title':'تنظیم نوبت‌دهی','description':'روزها و ساعت‌های کاری را مشخص کنید. تا فعال‌سازی شما، رزرو خودکار انجام نمی‌شود. ساعت‌ها به وقت تهران هستند.','back_url':'calendar'})


@calendar_staff_required
@require_POST
def book(request):
    form = BookingForm(request.POST,actor=request.user)
    if form.is_valid():
        try:
            appointment = book_selected_slot(form.cleaned_data['patient'],form.cleaned_data['day'],form.cleaned_data['slot_start'],request.user,request_key=form.cleaned_data['request_token'])
        except (BookingError,CalendarUnavailable) as error:
            form.add_error(None,str(error))
        else:
            if appointment.status == 'confirmed':
                messages.success(request,'نوبت در ساعت انتخاب‌شده در گوگل ثبت شد.')
            else:
                messages.warning(request,'زمان در پنل نگه داشته شد، اما ثبت گوگل هنوز تأیید نشده؛ وضعیت همگام‌سازی را بررسی کنید.')
            return redirect('calendar')
    return render(request,'clinic/form.html',{'section':'calendar','form':form,'title':'انتخاب وقت مراجعه','description':'روز شمسی و یکی از ساعت‌های آزاد را انتخاب کنید.','back_url':'calendar','slot_picker':True})


@calendar_staff_required
@require_POST
def retry(request,pk):
    get_object_or_404(Appointment,pk=pk)
    appointment = sync_appointment(pk,request.user,force=True)
    messages.info(request,'وضعیت نوبت: '+appointment.get_status_display())
    return redirect('calendar')


@calendar_staff_required
@require_POST
def cancel(request,pk):
    get_object_or_404(Appointment,pk=pk)
    appointment = request_cancellation(pk,request.user)
    messages.info(request,'وضعیت نوبت: '+appointment.get_status_display())
    return redirect('calendar')


@calendar_staff_required
@require_GET
def slots(request):
    from django.core.exceptions import ValidationError
    try:
        day = JalaliDateField().clean(request.GET.get('day',''))
        choices = available_slots(day)
    except ValidationError:
        return JsonResponse({'slots':[],'error':'تاریخ شمسی معتبر انتخاب کنید.'},status=400)
    except (BookingError,CalendarUnavailable) as error:
        return JsonResponse({'slots':[],'error':str(error)},status=503)
    return JsonResponse({'slots':[{'start':start.isoformat(),'end':end.isoformat(),'label':timezone.localtime(start).strftime('%H:%M').translate(TO_PERSIAN)} for start,end in choices]})


@calendar_staff_required
@require_http_methods(['GET','POST'])
def availability_settings(request):
    initial = {}
    if request.method == 'GET' and request.GET.get('day'):
        from django.core.exceptions import ValidationError
        try:
            day = JalaliDateField().clean(request.GET['day'])
            override = AvailabilityOverride.objects.filter(day=day).first()
            initial = {'day':day}
            if override:
                initial['closed'] = override.closed
                for index,window in enumerate(override.windows[:2]):
                    initial.update({('opens_at' if index == 0 else 'opens_second'):window['start'],('closes_at' if index == 0 else 'closes_second'):window['end']})
        except ValidationError:
            pass
    form = AvailabilityForm(request.POST if request.method == 'POST' else None,initial=initial)
    if request.method == 'POST' and form.is_valid():
        ScheduleSettings.objects.get_or_create(pk=1)
        with transaction.atomic():
            ScheduleSettings.objects.select_for_update().get(pk=1)
            override,_ = AvailabilityOverride.objects.update_or_create(day=form.cleaned_data['day'],defaults={'closed':form.cleaned_data['closed'],'windows':form.cleaned_data['windows']})
            AuditEvent.objects.create(actor=request.user,action='calendar.availability',target=str(override.pk))
        messages.success(request,'برنامه این روز ذخیره شد؛ نوبت‌های قبلی خودکار جابه‌جا نمی‌شوند.')
        return redirect('calendar_availability')
    page = Paginator(AvailabilityOverride.objects.all(),25).get_page(request.GET.get('page'))
    return render(request,'clinic/availability.html',{'section':'calendar','form':form,'page':page})
