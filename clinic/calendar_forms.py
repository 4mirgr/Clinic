from django import forms
from django.utils import timezone

from .calendar_models import ScheduleSettings
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
    day = forms.DateField(label='تاریخ مراجعه (میلادی)',widget=forms.DateInput(attrs={'type':'date'}))

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['patient'].queryset = Patient.objects.order_by('last_name','first_name')
        self.fields['patient'].label_from_instance = lambda patient: patient.full_name
        self.fields['day'].widget.attrs['min'] = timezone.localdate().isoformat()
