from django import forms
from django.core import signing
from django.utils import timezone
import uuid

from .calendar_models import ScheduleSettings,AvailabilityOverride
from .jalali import JalaliDateField,today_tehran
from .models import Patient

WEEKDAYS = [('5','شنبه'),('6','یکشنبه'),('0','دوشنبه'),('1','سه‌شنبه'),('2','چهارشنبه'),('3','پنجشنبه'),('4','جمعه')]


class ScheduleForm(forms.ModelForm):
    weekdays = forms.MultipleChoiceField(label='روزهای کاری',choices=WEEKDAYS,required=False,widget=forms.CheckboxSelectMultiple)
    slot_minutes = forms.IntegerField(label='مدت هر ویزیت (دقیقه)',min_value=5,max_value=180)
    horizon_days = forms.IntegerField(label='حداکثر فاصله رزرو (روز)',min_value=1,max_value=90)

    class Meta:
        model = ScheduleSettings
        fields = ['enabled','weekdays','opens_at','closes_at','slot_minutes','horizon_days']
        widgets = {'opens_at':forms.TimeInput(format='%H:%M',attrs={'type':'time'}),'closes_at':forms.TimeInput(format='%H:%M',attrs={'type':'time'})}

    def clean_weekdays(self):
        return [int(value) for value in self.cleaned_data['weekdays']]

    def clean(self):
        data = super().clean()
        opening,closing = data.get('opens_at'),data.get('closes_at')
        if data.get('enabled') and (not data.get('weekdays') or not opening or not closing):
            raise forms.ValidationError('برای فعال‌سازی، روزها و شروع و پایان کار را مشخص کنید.')
        if opening and closing:
            if opening >= closing:
                raise forms.ValidationError('پایان کار باید بعد از شروع کار در همان روز باشد.')
            if data.get('enabled') and (closing.hour*60+closing.minute)-(opening.hour*60+opening.minute) < data.get('slot_minutes',0):
                raise forms.ValidationError('بازه کاری باید دست‌کم به اندازه یک ویزیت باشد.')
        return data


class BookingForm(forms.Form):
    patient = forms.ModelChoiceField(queryset=Patient.objects.none(),label='بیمار')
    day = JalaliDateField(label='تاریخ مراجعه (هجری شمسی)',initial=today_tehran)
    slot_start = forms.DateTimeField(widget=forms.HiddenInput)
    request_token = forms.CharField(widget=forms.HiddenInput)

    def __init__(self,*args,**kwargs):
        self.actor = kwargs.pop('actor',None)
        super().__init__(*args,**kwargs)
        self.fields['patient'].queryset = Patient.objects.order_by('last_name','first_name')
        self.fields['patient'].label_from_instance = lambda patient: patient.full_name
        if not self.is_bound and self.actor:
            self.fields['request_token'].initial = signing.dumps({'key':uuid.uuid4().hex,'user':self.actor.pk},salt='clinic.booking')

    def clean_request_token(self):
        try:
            data = signing.loads(self.cleaned_data['request_token'],salt='clinic.booking',max_age=1800)
            if not self.actor or data['user'] != self.actor.pk:
                raise ValueError()
            return uuid.UUID(data['key'])
        except (signing.BadSignature,ValueError,KeyError,TypeError):
            raise forms.ValidationError('فرم رزرو منقضی یا نامعتبر است؛ صفحه را تازه کنید.') from None


class AvailabilityForm(forms.Form):
    day = JalaliDateField(label='روز موردنظر (هجری شمسی)',initial=today_tehran)
    closed = forms.BooleanField(label='این روز تعطیل باشد',required=False)
    opens_at = forms.TimeField(label='شروع بازه اول',required=False,widget=forms.TimeInput(attrs={'type':'time'}))
    closes_at = forms.TimeField(label='پایان بازه اول',required=False,widget=forms.TimeInput(attrs={'type':'time'}))
    opens_second = forms.TimeField(label='شروع بازه دوم (اختیاری)',required=False,widget=forms.TimeInput(attrs={'type':'time'}))
    closes_second = forms.TimeField(label='پایان بازه دوم (اختیاری)',required=False,widget=forms.TimeInput(attrs={'type':'time'}))

    def clean(self):
        data = super().clean()
        if data.get('closed'):
            data['windows'] = []
            return data
        windows = []
        for opening,closing in [('opens_at','closes_at'),('opens_second','closes_second')]:
            start,end = data.get(opening),data.get(closing)
            if not start and not end and windows:
                continue
            if not start or not end or end <= start:
                raise forms.ValidationError('هر بازه باید شروع و پایان معتبر در همان روز داشته باشد.')
            windows.append({'start':start.strftime('%H:%M'),'end':end.strftime('%H:%M')})
        windows.sort(key=lambda item:item['start'])
        if len(windows) == 2 and windows[0]['end'] > windows[1]['start']:
            raise forms.ValidationError('بازه‌های کاری نباید با هم تداخل داشته باشند.')
        data['windows'] = windows
        return data
