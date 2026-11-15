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
            self.assertEqual(page.evaluate('getComputedStyle(document.body).backgroundColor'),'rgb(12, 21, 35)')
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
                page.get_by_label('بیمار',exact=False).select_option(index=1)
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
