import re
from datetime import date,datetime
from zoneinfo import ZoneInfo

import jdatetime
from django import forms
from django.utils import timezone

TZ = ZoneInfo('Asia/Tehran')
TO_ASCII = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')
TO_PERSIAN = str.maketrans('0123456789','۰۱۲۳۴۵۶۷۸۹')


def today_tehran():
    return timezone.localdate(timezone.now(),TZ)


def format_jalali(value,include_time=False):
    if not value:
        return ''
    clock = ''
    if isinstance(value,datetime):
        value = timezone.localtime(value,TZ)
        clock = value.strftime(' · %H:%M') if include_time else ''
        value = value.date()
    converted = jdatetime.date.fromgregorian(date=value)
    return (f'{converted.year:04d}/{converted.month:02d}/{converted.day:02d}'+clock).translate(TO_PERSIAN)


class JalaliDateInput(forms.TextInput):
    template_name = 'clinic/widgets/jalali_date.html'

    def __init__(self,attrs=None):
        super().__init__({'autocomplete':'off','inputmode':'numeric','placeholder':'۱۴۰۵/۰۸/۲۴',**(attrs or {})})

    def format_value(self,value):
        return format_jalali(value) if isinstance(value,date) else super().format_value(value)

    def get_context(self,name,value,attrs):
        context = super().get_context(name,value,attrs)
        context['widget']['today'] = today_tehran().isoformat()
        return context


class JalaliDateField(forms.DateField):
    widget = JalaliDateInput

    def to_python(self,value):
        if value in self.empty_values:
            return None
        if isinstance(value,date):
            return value
        text = str(value).strip().translate(TO_ASCII)
        if not re.fullmatch(r'1[34][0-9]{2}/[0-9]{1,2}/[0-9]{1,2}',text):
            raise forms.ValidationError('تاریخ هجری شمسی را مانند ۱۴۰۵/۰۸/۲۴ وارد کنید.')
        try:
            year,month,day = map(int,text.split('/'))
            return jdatetime.date(year,month,day).togregorian()
        except (ValueError,OverflowError):
            raise forms.ValidationError('تاریخ هجری شمسی معتبر نیست.') from None
