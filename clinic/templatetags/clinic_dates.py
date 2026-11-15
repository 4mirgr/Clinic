from django import template
from clinic.jalali import format_jalali

register = template.Library()


@register.filter
def jalali_date(value):
    return format_jalali(value)


@register.filter
def jalali_datetime(value):
    return format_jalali(value,include_time=True)
