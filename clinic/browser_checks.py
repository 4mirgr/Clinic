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
