"""Explicit browser acceptance test: python manage.py test clinic.browser_checks.

Uses isolated test users/data; never credentials for the real clinic.
Requires requirements-dev.txt and Chromium (CHROMIUM_PATH or /usr/bin/chromium).
"""
import os
import shutil
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.test import LiveServerTestCase,override_settings
from playwright.sync_api import sync_playwright


@override_settings(GOOGLE_CLIENT_ID='',GOOGLE_CLIENT_SECRET='',GOOGLE_TOKEN_ENCRYPTION_KEY='')
class BrowserAcceptance(LiveServerTestCase):
    def test_desktop_mobile_and_brochure_workflow(self):
        for name,role in [('browser-doctor','manager'),('browser-secretary','secretary')]:
            user=User.objects.create_user(name,password='Browser-test-only-73!')
            user.groups.add(Group.objects.get_or_create(name='clinic_'+role)[0])
        output=settings.BASE_DIR/'test-results'
        output.mkdir(exist_ok=True)
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=(os.getenv('CHROMIUM_PATH') or shutil.which('chromium') or p.chromium.executable_path),headless=True,args=['--no-sandbox'])
            context=browser.new_context(viewport={'width':1440,'height':1050},locale='fa-IR')
            page=context.new_page()
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(self.live_server_url+'/dash/')
            self.assertTrue(page.url.endswith('/dash/login/'))
            page.screenshot(path=str(output/'login-desktop.png'),full_page=True)
            page.get_by_role('link',name='پزشک / مدیر').click()
            page.get_by_label('نام کاربری').fill('browser-doctor')
            page.get_by_label('رمز عبور').fill('Browser-test-only-73!')
            page.get_by_role('button',name='ورود به پنل').click()
            self.assertTrue(page.url.endswith('/dash/'), page.locator('body').inner_text())
            page.evaluate('document.fonts.ready')
            self.assertEqual(page.locator('h1').inner_text(),'پیشخوان مطب')
            self.assertIn('Vazirmatn',page.evaluate('getComputedStyle(document.body).fontFamily'))
            page.screenshot(path=str(output/'dashboard-desktop.png'),full_page=True)
            self.assertEqual(page.locator('html').get_attribute('data-theme'),'light')
            page.get_by_role('button',name='تغییر حالت نمایش').click()
            self.assertEqual(page.locator('html').get_attribute('data-theme'),'dark')
            page.reload()
            self.assertEqual(page.locator('html').get_attribute('data-theme'),'dark')
            self.assertEqual(page.evaluate('getComputedStyle(document.body).backgroundColor'),'rgb(16, 26, 47)')
            page.screenshot(path=str(output/'dashboard-dark-desktop.png'),full_page=True)
            page.get_by_role('button',name='تغییر حالت نمایش').click()

            page.get_by_role('link',name='پرونده جدید').click()
            page.get_by_label('نام',exact=False).first.fill('بیمار')
            page.get_by_label('نام خانوادگی').fill('آزمایشی')
            page.get_by_label('شماره همراه').fill('09123456789')
            page.get_by_label('شرح‌حال و سوابق').fill('این داده صرفاً برای آزمون خودکار است.')
            page.get_by_role('button',name='ذخیره اطلاعات').click()
            page.wait_for_url('**/dash/patients/*/')
            page.locator('textarea[name=note]').fill('یادداشت آزمایشی ویزیت')
            page.get_by_role('button',name='ثبت در خط زمانی').click()
            self.assertIn('یادداشت آزمایشی',page.locator('main').inner_text())
            page.set_viewport_size({'width':390,'height':844})
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.screenshot(path=str(output/'patient-mobile.png'),full_page=True)
            page.get_by_role('button',name='باز کردن منو').click()
            page.get_by_role('link',name='توصیه‌های بیماری‌ها',exact=False).click()
            page.get_by_role('button',name='تغییر حالت نمایش').click()
            self.assertEqual(page.locator('html').get_attribute('data-theme'),'dark')
            page.get_by_role('link',name='توصیه جدید').click()
            page.get_by_label('عنوان توصیه').fill('نمونه آموزشی آزمایشی')
            page.get_by_label('متن توصیه').fill('این متن فقط برای آزمون چاپ است.\n\nاین بخش نمونه دوم است.')
            page.get_by_label('متن را بازبینی').check()
            page.get_by_role('button',name='ذخیره اطلاعات').click()
            page.wait_for_url('**/print/')
            page.set_viewport_size({'width':1200,'height':1100})
            page.evaluate('document.fonts.ready')
            page.locator('.qr-block img').wait_for()
            self.assertTrue(page.locator('.qr-block img').evaluate('(img) => img.complete && img.naturalWidth > 0'))
            self.assertEqual(page.locator('html').get_attribute('data-theme'),'dark')
            page.emulate_media(media='print')
            self.assertEqual(page.evaluate('getComputedStyle(document.body).backgroundColor'),'rgb(255, 255, 255)')
            page.pdf(path=str(output/'brochure-example.pdf'),format='A4',print_background=True)
            page.emulate_media(media='screen')
            page.screenshot(path=str(output/'brochure-desktop.png'),full_page=True)
            page.goto(self.live_server_url+'/dash/')
            page.get_by_role('button',name='تغییر حالت نمایش').click()
            page.set_viewport_size({'width':390,'height':844})
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.screenshot(path=str(output/'dashboard-mobile.png'),full_page=True)
            page.get_by_role('button',name='تغییر حالت نمایش').click()
            self.assertEqual(page.locator('html').get_attribute('data-theme'),'dark')
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.screenshot(path=str(output/'dashboard-dark-mobile.png'),full_page=True)

            page.goto(self.live_server_url+'/dash/calendar/')
            self.assertIn('اتصال گوگل تنظیم نشده',page.locator('main').inner_text())
            self.assertIn('رزرو هنوز فعال نیست',page.locator('main').inner_text())
            from clinic.jalali import today_tehran,format_jalali
            self.assertEqual(page.get_by_label('تاریخ مراجعه (هجری شمسی)').input_value(),format_jalali(today_tehran()))
            page.get_by_role('button',name='باز کردن تقویم شمسی').click()
            self.assertTrue(page.locator('.jalali-popup').is_visible())
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.screenshot(path=str(output/'jalali-picker-mobile.png'),full_page=True)
            page.keyboard.press('Escape')
            self.assertFalse(page.locator('.jalali-popup').is_visible())
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.set_viewport_size({'width':1440,'height':1050})
            page.screenshot(path=str(output/'calendar-dark-desktop.png'),full_page=True)
            page.get_by_role('link',name='برنامه هفتگی',exact=True).click()
            self.assertFalse(page.get_by_label('نوبت‌دهی فعال باشد').is_checked())
            page.get_by_label('دوشنبه',exact=True).check()
            page.get_by_label('شروع کار').fill('09:00')
            page.get_by_label('پایان کار').fill('12:00')
            page.get_by_role('button',name='ذخیره اطلاعات').click()
            self.assertIn('رزرو هنوز فعال نیست',page.locator('main').inner_text())
            page.goto(self.live_server_url+'/dash/')
            page.set_viewport_size({'width':390,'height':844})
            page.get_by_role('button',name='باز کردن منو').click()
            self.assertTrue(page.get_by_role('button',name='خروج از حساب').is_visible(), 'Logout must be available from the mobile menu')
            page.get_by_role('button',name='خروج از حساب').click()
            page.wait_for_url('**/dash/login/')
            page.goto(self.live_server_url+'/dash/login/secretary/')
            page.get_by_label('نام کاربری').fill('browser-secretary')
            page.get_by_label('رمز عبور').fill('Browser-test-only-73!')
            page.get_by_role('button',name='ورود به پنل').click()
            page.wait_for_url('**/dash/')
            self.assertIn('دسترسی محدود',page.locator('main').inner_text())
            response=page.goto(self.live_server_url+'/dash/patients/')
            self.assertEqual(response.status,403)
            self.assertEqual(errors,[])
            browser.close()


class OAuthNavigationAcceptance(LiveServerTestCase):
    def test_configured_google_authorization_navigation_is_not_blocked_by_csp(self):
        from clinic.tests.test_calendar import TEST_GOOGLE
        with override_settings(**TEST_GOOGLE):
            user=User.objects.create_user('oauth-browser-doctor',password='Browser-test-only-73!')
            user.groups.add(Group.objects.get_or_create(name='clinic_manager')[0])
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=(os.getenv('CHROMIUM_PATH') or shutil.which('chromium') or p.chromium.executable_path),headless=True,args=['--no-sandbox','--proxy-server=http://127.0.0.1:9','--proxy-bypass-list=localhost;127.0.0.1'])
                page=browser.new_page()
                # This browser uses a closed loopback proxy for external hosts.
                # We verify the attempted authorization navigation, without contacting Google.
                page.goto(self.live_server_url+'/dash/login/manager/')
                page.get_by_label('نام کاربری').fill('oauth-browser-doctor')
                page.get_by_label('رمز عبور').fill('Browser-test-only-73!')
                page.get_by_role('button',name='ورود به پنل').click()
                self.assertTrue(page.url.endswith('/dash/'),page.locator('body').inner_text())
                page.goto(self.live_server_url+'/dash/calendar/')
                self.assertIn('اتصال حساب گوگل',page.locator('body').inner_text())
                with page.expect_request('https://accounts.google.com/**',timeout=5000) as navigation:
                    page.get_by_role('button',name='اتصال حساب گوگل').click()
                from urllib.parse import urlparse,parse_qs
                target=urlparse(navigation.value.url)
                self.assertEqual(target.hostname,'accounts.google.com')
                self.assertIn('code_challenge',parse_qs(target.query))
                self.assertEqual(navigation.value.method,'GET')
                browser.close()


class JalaliBookingAcceptance(LiveServerTestCase):
    def test_staff_selects_jalali_slot_and_edits_same_google_event(self):
        from datetime import time,timedelta
        from unittest.mock import patch
        from clinic.tests.test_calendar import TEST_GOOGLE
        from clinic.tests.test_rescheduling import EditableCalendar
        from clinic.calendar_models import CalendarConnection,ScheduleSettings,Appointment
        from clinic.models import Patient
        from clinic.jalali import today_tehran,format_jalali
        with override_settings(**TEST_GOOGLE):
            user=User.objects.create_user('slot-doctor',password='Browser-test-only-73!');user.groups.add(Group.objects.get_or_create(name='clinic_manager')[0])
            Patient.objects.create(first_name='تست',last_name='نوبت شمسی',phone='09123456789')
            connection=CalendarConnection(pk=1,owner=user,active=True,account_email='dr.gerami.md@gmail.com',google_subject='test-subject');connection.set_refresh_token('test-only-refresh');connection.save()
            ScheduleSettings.objects.create(pk=1,enabled=True,weekdays=list(range(7)),opens_at=time(9),closes_at=time(11),slot_minutes=20,horizon_days=30)
            provider=EditableCalendar()
            with patch('clinic.scheduling.GoogleCalendar',return_value=provider),sync_playwright() as p:
                browser=p.chromium.launch(executable_path=(os.getenv('CHROMIUM_PATH') or shutil.which('chromium') or p.chromium.executable_path),headless=True,args=['--no-sandbox'])
                page=browser.new_page(viewport={'width':1280,'height':1000})
                page.goto(self.live_server_url+'/dash/login/manager/')
                page.get_by_label('نام کاربری').fill('slot-doctor');page.get_by_label('رمز عبور').fill('Browser-test-only-73!');page.get_by_role('button',name='ورود به پنل').click()
                page.goto(self.live_server_url+'/dash/calendar/')
                page.locator('select[name=patient]').select_option(index=1)
                page.get_by_label('تاریخ مراجعه (هجری شمسی)').fill(format_jalali(today_tehran()+timedelta(days=1)))
                page.get_by_role('button',name='نمایش ساعت‌های آزاد').click()
                page.locator('.slot-choice').first.wait_for();page.locator('.slot-choice').first.click()
                page.get_by_role('button',name='ثبت وقت انتخاب‌شده').click()
                page.wait_for_url('**/dash/calendar/')
                self.assertIn('ثبت‌شده در گوگل',page.locator('main').inner_text())
                initial_edit_url=page.get_by_role('link',name='ویرایش وقت').get_attribute('href')
                import uuid
                event_id=uuid.UUID(initial_edit_url.split('/')[-3]).hex
                page.get_by_role('link',name='ویرایش وقت').click()
                page.get_by_role('button',name='نمایش ساعت‌های آزاد').click()
                page.locator('.slot-choice').nth(1).wait_for();page.locator('.slot-choice').nth(1).click()
                page.get_by_role('button',name='ذخیره و همگام‌سازی ویرایش').click()
                page.wait_for_url('**/dash/calendar/')
                self.assertIn('ثبت‌شده در گوگل',page.locator('main').inner_text())
                self.assertIn('۰۹:۲۰',page.locator('main').inner_text())
                self.assertEqual(page.get_by_role('link',name='ویرایش وقت').get_attribute('href'),initial_edit_url)
                self.assertEqual(list(provider.events),[event_id]);self.assertEqual(provider.updates,1)
                (settings.BASE_DIR/'test-results').mkdir(exist_ok=True)
                page.screenshot(path=str(settings.BASE_DIR/'test-results/calendar-jalali-edit.png'),full_page=True)
                browser.close()


class PatientSlotAcceptance(LiveServerTestCase):
    def test_shared_patient_account_selects_own_jalali_slot(self):
        from datetime import time,timedelta
        from unittest.mock import patch
        from clinic.tests.test_calendar import TEST_GOOGLE
        from clinic.tests.test_rescheduling import EditableCalendar
        from clinic.calendar_models import CalendarConnection,ScheduleSettings
        from clinic.jalali import today_tehran,format_jalali
        with override_settings(**TEST_GOOGLE):
            doctor=User.objects.create_user('patient-slot-owner')
            connection=CalendarConnection(pk=1,owner=doctor,active=True,account_email='dr.gerami.md@gmail.com',google_subject='test-subject');connection.set_refresh_token('fake-only');connection.save()
            ScheduleSettings.objects.create(pk=1,enabled=True,weekdays=list(range(7)),opens_at=time(9),closes_at=time(11),slot_minutes=20,horizon_days=30)
            provider=EditableCalendar()
            with patch('clinic.scheduling.GoogleCalendar',return_value=provider),sync_playwright() as p:
                browser=p.chromium.launch(executable_path=(os.getenv('CHROMIUM_PATH') or shutil.which('chromium') or p.chromium.executable_path),headless=True,args=['--no-sandbox'])
                context=browser.new_context(viewport={'width':390,'height':844},locale='fa-IR')
                base=self.live_server_url
                def post(route,data):
                    token=context.request.get(base+'/dash/api/portal/session').json()['csrf_token']
                    return context.request.post(base+'/dash/api/portal/'+route,data=data,headers={'X-CSRFToken':token,'Content-Type':'application/json'})
                self.assertEqual(post('signup',{'username':'patient-browser','email':'patient-browser@example.test','display_name':'بیمار آزمایشی','password':'Browser-test-only-73!'}).status,201)
                self.assertEqual(post('profile',{'display_name':'بیمار آزمایشی','first_name':'بیمار','last_name':'آزمایشی','phone':'09123456789'}).status,200)
                page=context.new_page();page.goto(base+'/dash/portal/')
                page.get_by_role('link',name='انتخاب وقت و نوبت‌های من').click()
                page.wait_for_load_state('load')
                page.wait_for_url('**/dash/booking/')
                self.assertEqual(page.get_by_label('تاریخ مراجعه (هجری شمسی)').input_value(),format_jalali(today_tehran()))
                page.get_by_role('button',name='باز کردن تقویم شمسی').click();self.assertTrue(page.locator('.jalali-popup').is_visible());page.keyboard.press('Escape')
                page.get_by_label('تاریخ مراجعه (هجری شمسی)').fill(format_jalali(today_tehran()+timedelta(days=1)))
                page.get_by_role('button',name='نمایش ساعت‌های آزاد').click()
                page.locator('.slot-choice').first.wait_for();page.locator('.slot-choice').first.click();page.get_by_role('button',name='ثبت وقت انتخاب‌شده').click()
                page.wait_for_url('**/dash/booking/')
                self.assertIn('ثبت‌شده در گوگل',page.locator('main').inner_text());self.assertEqual(len(provider.events),1)
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
                (settings.BASE_DIR/'test-results').mkdir(exist_ok=True);page.screenshot(path=str(settings.BASE_DIR/'test-results/patient-jalali-booking.png'),full_page=True)
                self.assertEqual(page.goto(base+'/dash/calendar/settings/').status,403)
                browser.close()


class PatientAdviceAcceptance(LiveServerTestCase):
    def test_doctor_records_snapshot_and_patient_prints_unchanged_copy(self):
        from .models import Advice, AdviceDelivery, Patient, PortalAccount
        doctor = User.objects.create_user('advice-browser-doctor', password='Browser-test-only-73!')
        doctor.groups.add(Group.objects.get_or_create(name='clinic_manager')[0])
        member = User.objects.create_user('advice-browser-patient', password='Browser-test-only-73!')
        patient = Patient.objects.create(first_name='بیمار', last_name='آزمایشی', phone='09123456789')
        PortalAccount.objects.create(user=member, patient=patient, email='advice-browser@example.test')
        advice = Advice.objects.create(title='راهنمای نمونه آزمایشی', body='این متن فقط برای آزمون نسخه ثبت‌شده است.\n\nبند دوم آزمایشی.', source='منبع آزمایشی', is_approved=True, updated_by=doctor)
        output = settings.BASE_DIR / 'test-results'
        output.mkdir(exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=(os.getenv('CHROMIUM_PATH') or shutil.which('chromium') or p.chromium.executable_path), headless=True, args=['--no-sandbox'])
            context = browser.new_context(viewport={'width':1440, 'height':1000}, locale='fa-IR')
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(self.live_server_url + '/dash/login/manager/')
            page.get_by_label('نام کاربری').fill(doctor.username)
            page.get_by_label('رمز عبور').fill('Browser-test-only-73!')
            page.get_by_role('button', name='ورود به پنل').click()
            page.wait_for_url('**/dash/')
            page.goto(self.live_server_url + patient.get_absolute_url())
            page.get_by_role('link', name='انتخاب تک‌توصیهٔ تأییدشده').click()
            page.get_by_label('جست‌وجوی توصیه تأییدشده').fill('نمونه')
            page.get_by_role('button', name='جست‌وجو', exact=True).click()
            page.get_by_role('link', name='انتخاب و بازبینی').click()
            page.wait_for_load_state('load')
            self.assertIn('بند دوم آزمایشی', page.locator('main').inner_text())
            page.evaluate('document.fonts.ready')
            page.screenshot(path=str(output / 'advice-confirm-desktop.png'), full_page=True)
            page.get_by_role('button', name='ثبت توصیه در پرونده').click()
            page.wait_for_url('**/dash/advice-records/*/')
            record_url = page.url
            self.assertTrue(page.locator('.qr-block img').evaluate('(img) => img.complete && img.naturalWidth > 0'))
            page.get_by_role('link', name='پرونده بیمار').click()
            page.wait_for_load_state('load')
            page.set_viewport_size({'width':390, 'height':844})
            page.locator('#advice-history').scroll_into_view_if_needed()
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 390)
            page.screenshot(path=str(output / 'advice-history-mobile.png'), full_page=True)
            page.goto(self.live_server_url + f'/dash/advice/{advice.pk}/edit/')
            page.get_by_label('متن توصیه').fill('نسخه جدید کتابخانه؛ نباید جایگزین نسخه بیمار شود.')
            page.get_by_role('button', name='ذخیره اطلاعات').click()
            page.wait_for_url('**/dash/advice/*/print/')
            patient_context = browser.new_context(viewport={'width':390, 'height':844}, locale='fa-IR')
            api = self.live_server_url + '/dash/api/portal/'
            token = patient_context.request.get(api + 'session').json()['csrf_token']
            response = patient_context.request.post(api + 'login', data={'identifier':member.username, 'password':'Browser-test-only-73!'}, headers={'X-CSRFToken':token, 'Content-Type':'application/json'})
            self.assertEqual(response.status, 200)
            own_page = patient_context.new_page()
            own_page.on('pageerror', lambda error: errors.append(str(error)))
            own_page.goto(self.live_server_url + '/dash/portal/')
            own_page.get_by_role('link', name='مشاهده نسخه ثبت‌شده و چاپ').click()
            own_page.wait_for_url('**/dash/advice-records/*/')
            self.assertEqual(own_page.url, record_url)
            self.assertIn('بند دوم آزمایشی', own_page.locator('main').inner_text())
            self.assertNotIn('نسخه جدید کتابخانه', own_page.locator('main').inner_text())
            self.assertLessEqual(own_page.evaluate('document.documentElement.scrollWidth'), 390)
            own_page.screenshot(path=str(output / 'advice-patient-mobile.png'), full_page=True)
            own_page.emulate_media(color_scheme='dark', media='print')
            self.assertEqual(own_page.evaluate('getComputedStyle(document.body).backgroundColor'), 'rgb(255, 255, 255)')
            own_page.pdf(path=str(output / 'advice-record-example.pdf'), format='A4', print_background=True)
            self.assertEqual(errors, [])
            browser.close()
        self.assertEqual(AdviceDelivery.objects.count(), 1)

    def test_bilingual_library_combined_pdf_and_published_summary(self):
        from clinic.advice_catalog import load_defaults
        from clinic.models import Patient, AdvicePacket, Advice
        doctor=User.objects.create_user('education-browser-doctor',password='Browser-test-only-73!')
        doctor.groups.add(Group.objects.get_or_create(name='clinic_manager')[0])
        patient=Patient.objects.create(first_name='بیمار',last_name='آزمایشی',phone='00000000000',history='یادداشت خصوصی آزمایشی')
        load_defaults(doctor)
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=(os.getenv('CHROMIUM_PATH') or shutil.which('chromium') or p.chromium.executable_path),headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':390,'height':844},locale='fa-IR')
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(self.live_server_url+'/dash/login/manager/')
            page.get_by_label('نام کاربری').fill(doctor.username)
            page.get_by_label('رمز عبور').fill('Browser-test-only-73!')
            page.get_by_role('button',name='ورود به پنل').click()
            page.wait_for_url('**/dash/')
            page.goto(self.live_server_url+'/dash/advice/?patient='+str(patient.pk))
            page.locator('#advice-search').fill('رِفلـاکس GERD')
            self.assertEqual(page.locator('[data-advice-card]:visible').count(),1)
            page.locator('[name=advice_ids]:visible').check()
            page.locator('#advice-search').fill('HTN')
            page.locator('[name=advice_ids]:visible').check()
            self.assertIn('۲',page.locator('[data-selection-count]').inner_text())
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.get_by_role('button',name='بازبینی و آماده‌سازی چاپ').click()
            page.wait_for_url('**/bundles/prepare/')
            page.get_by_label('همهٔ متن‌های بالا را برای این بیمار بازبینی و تأیید می‌کنم.').check()
            page.get_by_role('button',name='تأیید و ثبت نسخهٔ چاپی در پرونده').click()
            page.wait_for_url('**/dash/advice/bundles/*/')
            self.assertEqual(page.locator('.patient-guide').count(),2)
            self.assertIn('رفلاکس',page.locator('.patient-guide').first.inner_text())
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            response=page.request.get(page.url+'pdf/')
            self.assertEqual(response.status,200)
            self.assertTrue(response.body().startswith(b'%PDF-'))
            page.get_by_role('link',name='خلاصه پرونده',exact=True).click()
            self.assertNotIn('یادداشت خصوصی آزمایشی',page.locator('main').inner_text())
            page.get_by_role('link',name='ویرایش پیش‌نویس / انتشار خلاصه').click()
            page.get_by_label('خلاصه شرح حال').fill('خلاصه منتشرشده آزمایشی')
            page.get_by_label('این نسخه را برای بیمار منتشر می‌کنم').check()
            page.get_by_role('button',name='ذخیره',exact=True).click()
            page.wait_for_url('**/summary/')
            self.assertIn('خلاصه منتشرشده آزمایشی',page.locator('main').inner_text())
            self.assertFalse(errors,errors)
            browser.close()


class ClinicalWorkspaceAcceptance(LiveServerTestCase):
    def test_doctor_and_patient_use_shared_account_with_distinct_dashboards(self):
        from clinic.models import Patient, PortalAccount, PatientIntakeSubmission, Visit
        doctor=User.objects.create_user('workspace-browser-doctor',password='Browser-test-only-73!',first_name='پزشک آزمایشی')
        doctor.groups.add(Group.objects.get_or_create(name='clinic_manager')[0])
        patient=Patient.objects.create(first_name='بیمار',last_name='آزمایشی',phone='09123456789',history='یادداشت خصوصی پزشک در آزمون')
        member=User.objects.create_user('workspace-browser-member',password='Browser-test-only-73!',first_name='بیمار آزمایشی')
        PortalAccount.objects.create(user=member,patient=patient,email='workspace-browser@example.test')
        output=settings.BASE_DIR/'test-results';output.mkdir(exist_ok=True)
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=(os.getenv('CHROMIUM_PATH') or shutil.which('chromium') or p.chromium.executable_path),headless=True,args=['--no-sandbox'])
            context=browser.new_context(viewport={'width':1440,'height':1050},locale='fa-IR')
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(self.live_server_url+'/dash/account/')
            page.get_by_label('نام کاربری یا ایمیل').fill(doctor.username)
            page.locator('#shared-login [name=password]').fill('Browser-test-only-73!')
            page.get_by_role('button',name='ورود به حساب مشترک').click();page.wait_for_url('**/dash/')
            self.assertEqual(page.locator('.physician-stats .stat-card').count(),4)
            page.evaluate('document.fonts.ready');page.screenshot(path=str(output/'physician-workspace-desktop.png'),full_page=True)
            page.goto(self.live_server_url+patient.get_absolute_url())
            page.get_by_label('نوع ویزیت').select_option('online')
            page.get_by_label('علت مراجعه',exact=True).fill('پیگیری آنلاین آزمایشی')
            page.get_by_label('شرح ویزیت و برنامه پیگیری').fill('شرح ساختگی برای آزمون')
            page.get_by_label('ارزیابی و تشخیص پزشک').fill('ارزیابی آزمایشی')
            page.get_by_label('برنامه درمان و پیگیری',exact=True).fill('برنامه آزمایشی')
            page.get_by_role('button',name='ثبت در خط زمانی').click();page.wait_for_url('**/dash/patients/*/')
            self.assertIn('پیگیری آنلاین آزمایشی',page.locator('#visits').inner_text())
            page.goto(self.live_server_url+'/dash/prescriptions/?patient='+str(patient.pk))
            context.route('https://panel.drnext.ir/**',lambda route:route.fulfill(status=200,content_type='text/html',body='<html><body>Provider test stub</body></html>'))
            with context.expect_page() as opened:
                page.locator('[data-prescription-window]').first.click()
            popup=opened.value;popup.wait_for_load_state()
            self.assertEqual(popup.url,'https://panel.drnext.ir/')
            self.assertTrue(popup.evaluate('window.opener===null'));popup.close()
            patient_context=browser.new_context(viewport={'width':390,'height':844},locale='fa-IR')
            own=patient_context.new_page();own.on('pageerror',lambda e:errors.append(str(e)))
            own.goto(self.live_server_url+'/dash/account/')
            own.get_by_label('نام کاربری یا ایمیل').fill(member.username)
            own.locator('#shared-login [name=password]').fill('Browser-test-only-73!')
            own.get_by_role('button',name='ورود به حساب مشترک').click();own.wait_for_url('**/dash/portal/')
            own.wait_for_load_state('networkidle');own.evaluate('document.fonts.ready')
            self.assertEqual(own.locator('.patient-summary-grid .patient-metric').count(),3)
            self.assertNotIn('یادداشت خصوصی پزشک در آزمون',own.locator('body').inner_text())
            own.locator('[name=reported_family_history]').fill('سابقه خانوادگی آزمایشی')
            own.locator('[name=reported_current_problem]').fill('مشکل جدید آزمایشی')
            with own.expect_response(lambda r:r.url.endswith('/api/portal/profile') and r.request.method=='POST') as saved:
                own.get_by_role('button',name='ذخیرهٔ پروفایل مشترک').click()
            self.assertEqual(saved.value.status,200,saved.value.text())
            own.locator('#portal-notice').filter(has_text='ذخیره شدند').wait_for()
            own.evaluate('window.scrollTo(0,0)');own.screenshot(path=str(output/'patient-workspace-mobile.png'),full_page=True)
            self.assertLessEqual(own.evaluate('document.documentElement.scrollWidth'),390)
            page.goto(self.live_server_url+patient.get_absolute_url())
            self.assertIn('سابقه خانوادگی آزمایشی',page.locator('#patient-intake').inner_text())
            page.set_viewport_size({'width':390,'height':844})
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            signup_context=browser.new_context(viewport={'width':390,'height':844},locale='fa-IR')
            signup=signup_context.new_page();signup.on('pageerror',lambda e:errors.append(str(e)))
            signup.goto(self.live_server_url+'/dash/account/')
            signup.locator('[data-auth-mode=signup]').click()
            form=signup.locator('#shared-signup')
            form.locator('[name=display_name]').fill('عضو آزمایشی جدید')
            form.locator('[name=username]').fill('new-workspace-member')
            form.locator('[name=email]').fill('new-workspace@example.test')
            form.locator('[name=password]').fill('New-test-member-only-73!')
            form.get_by_role('button',name='ساخت حساب و ورود').click()
            signup.wait_for_url('**/dash/portal/')
            self.assertTrue(signup.request.get(self.live_server_url+'/dash/').url.endswith('/dash/portal/'))
            self.assertEqual(signup.request.get(self.live_server_url+'/dash/patients/').status,403)
            self.assertFalse(errors,errors)
            browser.close()
        self.assertEqual(Visit.objects.count(),1)
        self.assertEqual(PatientIntakeSubmission.objects.count(),1)
