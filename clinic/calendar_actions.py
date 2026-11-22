"""Manager-triggered application of the owner's Google-authoritative policy."""
from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from .access import manager_required
from .calendar_reconciliation import reconcile_calendar
from .portal_api import PortalError, rate


@manager_required
@require_POST
def apply_google_changes(request):
    try:
        rate(request,'calendar-reconcile',6,str(request.user.pk))
    except PortalError:
        messages.warning(request,'بررسی‌های زیادی انجام شده؛ چند دقیقه بعد دوباره تلاش کنید.')
        return redirect('calendar')
    result=reconcile_calendar(probe=True,apply_google=True,limit=3,actor=request.user)
    if result['status']=='checked' or result['applied_moved'] or result['applied_missing']:
        messages.success(request,f"بررسی شد: {result['applied_moved']} تغییر زمان و {result['applied_missing']} حذف از گوگل در پنل ثبت شد.")
    if result['overlap']:
        messages.warning(request,'زمان تغییرکرده با نوبت دیگری تداخل دارد؛ وقت قبلی تا بررسی شما حفظ شد.')
    if result['remaining']:
        messages.info(request,'بررسی این نوبت تمام نشده است؛ موارد باقی‌مانده در اجرای بعد بررسی می‌شوند.')
    if result['status']!='checked' and not result['overlap']:
        messages.warning(request,'دریافت همه تغییرات گوگل کامل نشد؛ وضعیت اتصال و تنظیمات تقویم را بررسی کنید.')
    return redirect('calendar')
