import re
from pathlib import Path

from django import forms
from .models import Advice, Document, Patient, Visit, PrescriptionReference
from .jalali import JalaliDateField


TRANSLATION = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك', '01234567890123456789یک')


def normalize(value):
    return ' '.join(value.translate(TRANSLATION).split())


class PatientForm(forms.ModelForm):
    # Accept international/formatting input before storing canonical 11 digits.
    phone = forms.CharField(label='شماره همراه', max_length=30)
    class Meta:
        model = Patient
        fields = ['first_name','last_name','national_id','phone','history','medications','allergies']
        widgets = {'history':forms.Textarea(attrs={'rows':4}), 'medications':forms.Textarea(attrs={'rows':3}), 'allergies':forms.Textarea(attrs={'rows':3})}

    def clean_first_name(self):
        return normalize(self.cleaned_data['first_name'])

    def clean_last_name(self):
        return normalize(self.cleaned_data['last_name'])

    def clean_national_id(self):
        value = normalize(self.cleaned_data.get('national_id') or '').replace(' ', '')
        if value and not re.fullmatch(r'[0-9]{10}', value):
            raise forms.ValidationError('کد ملی باید دقیقاً ۱۰ رقم باشد؛ در صورت نداشتن، خالی بگذارید.')
        return value or None

    def clean_phone(self):
        value = normalize(self.cleaned_data['phone']).replace(' ', '').replace('-', '')
        if value.startswith('+98'):
            value = '0' + value[3:]
        elif value.startswith('0098'):
            value = '0' + value[4:]
        if not re.fullmatch(r'09[0-9]{9}', value):
            raise forms.ValidationError('شماره همراه معتبر مانند ۰۹۱۲۳۴۵۶۷۸۹ وارد کنید.')
        return value


class VisitForm(forms.ModelForm):
    mode = forms.ChoiceField(label='نوع ویزیت', choices=Visit._meta.get_field('mode').choices, required=False, initial='in_person')
    follow_up_on = JalaliDateField(label='تاریخ پیگیری (هجری شمسی)', required=False)
    class Meta:
        model = Visit
        fields = ['mode','chief_complaint','note','assessment','plan','systolic','diastolic','pulse','weight','temperature','oxygen_saturation','follow_up_on']
        widgets = {key:forms.Textarea(attrs={'rows':3}) for key in ['note','assessment','plan']}

    def clean_mode(self):
        return self.cleaned_data.get('mode') or 'in_person'

    def clean(self):
        data=super().clean()
        ranges={'systolic':(30,300),'diastolic':(10,200),'pulse':(10,300),'weight':(1,500),'temperature':(25,45),'oxygen_saturation':(1,100)}
        for key,(low,high) in ranges.items():
            value=data.get(key)
            if value is not None and not low<=value<=high:
                self.add_error(key,f'مقدار باید بین {low} و {high} باشد؛ اگر اندازه‌گیری نشده خالی بگذارید.')
        return data


class PrescriptionReferenceForm(forms.ModelForm):
    class Meta:
        model=PrescriptionReference
        fields=['patient','provider','reference','note']
        widgets={'note':forms.Textarea(attrs={'rows':3})}


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['title','category','file']
        widgets = {'file':forms.ClearableFileInput(attrs={'accept':'.pdf,.jpg,.jpeg,.png'})}

    def clean_file(self):
        file = self.cleaned_data['file']
        if file.size > 20 * 1024 * 1024:
            raise forms.ValidationError('حداکثر حجم فایل ۲۰ مگابایت است.')
        suffix = Path(file.name).suffix.lower()
        signatures = {'.pdf': b'%PDF-', '.png': b'\x89PNG\r\n\x1a\n', '.jpg': b'\xff\xd8\xff', '.jpeg': b'\xff\xd8\xff'}
        header = file.read(16)
        file.seek(0)
        if suffix not in signatures or not header.startswith(signatures[suffix]):
            raise forms.ValidationError('فقط فایل PDF، JPG و PNG با محتوای معتبر پذیرفته می‌شود.')
        return file


class AdviceForm(forms.ModelForm):
    def clean(self):
        data = super().clean()
        for key in ['title', 'tags', 'body']:
            if key in data:
                # Keep newlines/paragraphs while aligning saved content with search input.
                data[key] = data[key].translate(TRANSLATION)
        return data

    class Meta:
        model = Advice
        fields = ['title','title_en','specialty','tags','body','source','is_approved']
        widgets = {'body':forms.Textarea(attrs={'rows':14}), 'source':forms.Textarea(attrs={'rows':3})}
