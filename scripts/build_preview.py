"""Render an isolated synthetic Django dataset as a public, read-only preview."""
import argparse
import html
import json
import os
import sys
import tempfile
import uuid
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ReadOnlyHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts = []
        self.skip_script = False
        self.theme_form = False

    def handle_decl(self, declaration):
        self.parts.append(f'<!{declaration}>')

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'script':
            self.skip_script = True
            return
        if self.skip_script:
            return
        if tag == 'input' and attributes.get('type', '').lower() == 'hidden':
            return
        attributes = {key: value for key, value in attrs if not key.startswith('on') and key != 'data-portal-api'}
        if tag == 'form':
            self.theme_form = 'theme-form' in (attributes.get('class') or '').split()
            attributes.pop('method', None)
            attributes['action'] = '#'
            attributes['data-preview-form'] = ''
        if tag in ('input', 'textarea', 'select') and attributes.get('name') not in ('q','specialty','advice_ids'):
            attributes['disabled'] = ''
        if tag == 'button' and attributes.get('type', 'submit') == 'submit' and not self.theme_form and 'data-demo-combine' not in attributes:
            attributes['disabled'] = ''
        if tag == 'option' and attributes.get('value') == '11111111-1111-4111-8111-111111111111':
            attributes['selected'] = ''
        if attributes.get('href') == '/account/':
            attributes['href'] = '/clinic/login/'
        rendered = ''.join(f' {key}' if value is None else f' {key}="{html.escape(value, quote=True)}"' for key, value in attributes.items())
        self.parts.append(f'<{tag}{rendered}>')
        if tag == 'body':
            self.parts.append('<aside class="preview-banner" role="status"><strong>پیش‌نمایش آزمایشی</strong><span>داده‌های نمایشی · ذخیره پرونده و بارگذاری فعال نیست.</span><nav><a href="/clinic/">پیشخوان پزشک</a><a href="/clinic/portal/">نمای بیمار</a><a href="/">وب‌سایت</a></nav></aside>')

    def handle_endtag(self, tag):
        if tag == 'script':
            self.skip_script = False
            return
        if self.skip_script:
            return
        if tag == 'head':
            self.parts.append('<link rel="icon" href="/clinic/static/clinic/favicon.svg"><link rel="stylesheet" href="/clinic/preview.css"><script src="/clinic/static/clinic/print-pager.js" defer></script><script src="/clinic/preview.js" defer></script>')
        if tag == 'form':
            self.theme_form = False
        self.parts.append(f'</{tag}>')

    def handle_data(self, data):
        if not self.skip_script:
            self.parts.append(data)

    def handle_entityref(self, name):
        if not self.skip_script:
            self.parts.append(f'&{name};')

    def handle_charref(self, name):
        if not self.skip_script:
            self.parts.append(f'&#{name};')


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    # Always replace inherited runtime values before importing Django. No
    # connection to the checkout database, real accounts or external services.
    with tempfile.TemporaryDirectory(prefix='clinic-public-preview-') as data_dir:
        os.environ.update(CLINIC_ENV='development', DATABASE_URL='', CLINIC_DATA_DIR=data_dir,
                          CLINIC_PUBLIC_URL='https://drgerami-md.ir/clinic', CLINIC_PROXY_KEY='', GOOGLE_CLIENT_ID='', GOOGLE_CLIENT_SECRET='',
                          GOOGLE_TOKEN_ENCRYPTION_KEY='', DJANGO_SETTINGS_MODULE='config.settings',
                          DJANGO_ALLOWED_HOSTS='testserver,localhost,127.0.0.1',
                          DJANGO_SECRET_KEY='isolated-preview-build-only-not-a-production-secret-8543189265074138')
        import django
        django.setup()
        from django.contrib.auth.models import Group, User
        from django.core.management import call_command
        from django.test import Client
        from clinic.models import Advice, AdviceDelivery, Patient, PortalAccount, Visit, PatientSummary
        from clinic.advice_catalog import load_defaults
        call_command('migrate', interactive=False, verbosity=0)
        doctor = User.objects.create_user('preview-doctor', first_name='پزشک آزمایشی')
        doctor.groups.add(Group.objects.get_or_create(name='clinic_manager')[0])
        patient = Patient.objects.create(id=uuid.UUID('11111111-1111-4111-8111-111111111111'), first_name='بیمار', last_name='آزمایشی', phone='00000000000', history='این پرونده فقط نمونه نمایشی است و مربوط به شخص واقعی نیست.')
        Visit.objects.create(patient=patient, author=doctor, note='یادداشت نمایشی برای بررسی طراحی خط زمانی؛ محتوای پزشکی واقعی نیست.')
        advice = Advice.objects.create(id=uuid.UUID('22222222-2222-4222-8222-222222222222'), title='راهنمای نمونه نمایشی', tags='نمونه رابط کاربری', body='این متن صرفاً برای نمایش طراحی توصیه‌هاست و توصیه پزشکی معتبر نیست.\n\nنسخه ثبت‌شده در پرونده، مستقل از تغییرات بعدی کتابخانه نگهداری می‌شود.', source='محتوای کاملاً نمایشی؛ برای استفاده درمانی نیست.', is_approved=True, updated_by=doctor)
        record = AdviceDelivery.objects.create(id=uuid.UUID('33333333-3333-4333-8333-333333333333'), patient=patient, advice=advice, title=advice.title, body=advice.body, tags=advice.tags, source=advice.source, advice_updated_at=advice.updated_at, created_by=doctor, request_key=uuid.UUID('44444444-4444-4444-8444-444444444444'))
        member = User.objects.create_user('preview-patient', first_name='بیمار آزمایشی')
        PortalAccount.objects.create(user=member, patient=patient, email='preview@example.test')
        load_defaults(doctor)
        PatientSummary.objects.create(patient=patient, updated_by=doctor, published_by=doctor, published_at=advice.updated_at, draft_data={}, published_data={'history':'خلاصهٔ کاملاً ساختگی برای نمایش طراحی؛ مربوط به هیچ شخصی نیست.','conditions':'بیماری نمونه؛ اطلاعات واقعی نیست.','medications':'داروی نمونه؛ دستور مصرف نیست.','health_status':'وضعیت سلامت ساختگی','progress':'روند پیگیری نمایشی'})
        client = Client()
        client.force_login(doctor)
        pages = {
            '/dash/': 'dashboard.html', '/dash/patients/': 'patients.html', '/dash/patients/new/': 'patient-form.html',
            patient.get_absolute_url(): 'patient-detail.html', patient.get_absolute_url()+'edit/': 'patient-edit.html',
            '/dash/advice/': 'advice.html', '/dash/advice/new/': 'advice-form.html',
            f'/dash/advice/{advice.pk}/edit/': 'advice-edit.html', f'/dash/advice/{advice.pk}/print/': 'advice-print.html',
            patient.get_absolute_url()+'advice/': 'advice-select.html', patient.get_absolute_url()+f'advice/{advice.pk}/': 'advice-confirm.html',
            record.get_absolute_url(): 'advice-record.html', '/dash/calendar/': 'calendar.html',
            '/dash/calendar/settings/': 'calendar-settings.html', '/dash/calendar/availability/': 'availability.html',
            '/dash/activity/': 'activity.html',
            patient.get_absolute_url()+'summary/': 'patient-summary.html',
        }
        for guide in Advice.objects.exclude(catalog_key=None):
            pages[f'/dash/advice/{guide.pk}/print/']='guide-'+guide.catalog_key+'.html'
            pages[f'/dash/advice/{guide.pk}/edit/']='guide-'+guide.catalog_key+'-edit.html'
        manifest = {}

        def capture(route, filename):
            response = client.get(route)
            if response.status_code != 200:
                raise RuntimeError(f'Cannot export {route}: HTTP {response.status_code}')
            parser = ReadOnlyHTML()
            parser.feed(response.content.decode().replace('/dash/', '/clinic/'))
            rendered = ''.join(parser.parts)
            if route == '/dash/advice/':
                rendered=rendered.replace('<section class="card education-library"', '<p><a href="/clinic/advice/sample.pdf">دریافت نمونه PDF پنج‌صفحه‌ای با وزیرمتن و QR آزمایشی</a></p><section class="card education-library"')
                rendered=rendered.replace('<button class="button primary" type="submit" disabled="">بازبینی و آماده‌سازی چاپ</button>','<button class="button primary" type="button" data-demo-combine>ساخت پیش‌نمایش چاپ</button>')
            (output / filename).write_text('\n'.join(line.rstrip() for line in rendered.splitlines())+'\n')
            manifest[route.replace('/dash/', '/clinic/')] = {'path':'deploy/preview/public/'+filename, 'type':'text/html; charset=utf-8'}

        for route, filename in pages.items():
            capture(route, filename)
        qr = client.get('/dash/advice/qr/')
        if qr.status_code != 200:
            raise RuntimeError('Cannot export public-site QR')
        (output / 'site-qr.svg').write_bytes(qr.content)
        manifest['/clinic/advice/qr/'] = {'path':'deploy/preview/public/site-qr.svg', 'type':'image/svg+xml'}
        client.force_login(member)
        session = client.session
        session['portal_auth_version'] = 0
        session.save()
        capture('/dash/portal/', 'portal.html')
        capture('/dash/booking/', 'booking.html')
        client.logout()
        for route, filename in [('/dash/login/','login.html'),('/dash/login/manager/','manager-login.html'),('/dash/login/secretary/','secretary-login.html')]:
            capture(route, filename)
        assets = {
            'print-pager.js':'text/javascript; charset=utf-8', 'education.css':'text/css; charset=utf-8', 'education.js':'text/javascript; charset=utf-8', 'brand/logo.webp':'image/webp',
            'fonts/vazirmatn-print-regular.ttf':'font/ttf', 'fonts/vazirmatn-print-semibold.ttf':'font/ttf',
            'app.css':'text/css; charset=utf-8', 'portal.css':'text/css; charset=utf-8', 'favicon.svg':'image/svg+xml',
            'art/clinical-orbit.png':'image/png', 'fonts/vazirmatn-arabic-400-normal.woff2':'font/woff2',
            'fonts/vazirmatn-arabic-600-normal.woff2':'font/woff2', 'fonts/OFL.txt':'text/plain; charset=utf-8',
        }
        for path, content_type in assets.items():
            manifest['/clinic/static/clinic/'+path] = {'path':'static/clinic/'+path, 'type':content_type}
        manifest['/clinic/advice/sample.pdf']={'path':'docs/previews/education-demo.pdf','type':'application/pdf'}
        for path, content_type in [('preview.css','text/css; charset=utf-8'),('preview.js','text/javascript; charset=utf-8')]:
            manifest['/clinic/'+path] = {'path':'deploy/preview/'+path, 'type':content_type}
        (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
        print(f'Exported {len(pages)+5} synthetic pages and {len(manifest)} public routes to {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    build(parser.parse_args().output)
