from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404,redirect,render
from django.views.decorators.http import require_GET,require_POST,require_http_methods
from django.utils import timezone

from .access import manager_required
from .calendar_api import CalendarUnavailable,configured
from .calendar_forms import BookingForm,ScheduleForm
from .calendar_models import Appointment,CalendarConnection,ScheduleSettings
from .models import AuditEvent
from .scheduling import BookingError,book_next_available,request_cancellation,sync_appointment


@manager_required
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
    return render(request,'clinic/calendar.html',{'section':'calendar','schedule':schedule,'connection':connection,'google_configured':configured(),'form':BookingForm(),'appointments':page.object_list,'page':page,'calendar_all':all_appointments})


@manager_required
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


@manager_required
@require_POST
def book(request):
    form = BookingForm(request.POST)
    if form.is_valid():
        try:
            appointment = book_next_available(form.cleaned_data['patient'],form.cleaned_data['day'],request.user)
        except (BookingError,CalendarUnavailable) as error:
            form.add_error(None,str(error))
        else:
            if appointment.status == 'confirmed':
                messages.success(request,'اولین زمان آزاد انتخاب و نوبت در گوگل ثبت شد.')
            else:
                messages.warning(request,'زمان در پنل نگه داشته شد، اما ثبت گوگل هنوز تأیید نشده؛ وضعیت همگام‌سازی را بررسی کنید.')
            return redirect('calendar')
    return render(request,'clinic/form.html',{'section':'calendar','form':form,'title':'رزرو اولین زمان آزاد','description':'روز مراجعه را انتخاب کنید؛ زمان بر اساس ساعات مطب و برنامه گوگل پیدا می‌شود.','back_url':'calendar'})


@manager_required
@require_POST
def retry(request,pk):
    get_object_or_404(Appointment,pk=pk)
    appointment = sync_appointment(pk,request.user,force=True)
    messages.info(request,'وضعیت نوبت: '+appointment.get_status_display())
    return redirect('calendar')


@manager_required
@require_POST
def cancel(request,pk):
    get_object_or_404(Appointment,pk=pk)
    appointment = request_cancellation(pk,request.user)
    messages.info(request,'وضعیت نوبت: '+appointment.get_status_display())
    return redirect('calendar')
