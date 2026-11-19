"""Check the public snapshot in Chromium against the actual preview Worker."""
import os
import xml.etree.ElementTree as ET
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
with socket.socket() as probe:
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
base = f'http://127.0.0.1:{port}'
server = subprocess.Popen(['node', 'deploy/preview/serve-local.mjs', str(port)], cwd=ROOT, stdout=subprocess.DEVNULL)
try:
    for _ in range(50):
        try:
            urllib.request.urlopen(base+'/clinic/', timeout=1).close()
            break
        except OSError:
            time.sleep(.1)
    else:
        raise RuntimeError('Preview Worker rehearsal did not start')
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH') or shutil.which('chromium') or p.chromium.executable_path, headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width':1440,'height':1050}, locale='fa-IR')
        errors, requests, failures = [], [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append((request.method,request.url)))
        page.on('response', lambda response: failures.append((response.status,response.url)) if response.status>=400 else None)
        assert page.goto(base+'/clinic/').status == 200
        expect(page.get_by_role('status')).to_contain_text('پیش‌نمایش آزمایشی')
        expect(page.get_by_role('heading',name='پیشخوان مطب')).to_be_visible()
        page.evaluate('document.fonts.ready')
        assert page.locator('.banner-visual img').evaluate('(img) => img.complete && img.naturalWidth > 0')
        output=ROOT/'test-results'
        output.mkdir(exist_ok=True)
        page.screenshot(path=str(output/'clinic-preview-desktop.png'),full_page=True)
        page.get_by_role('button',name='تغییر حالت نمایش').click()
        assert page.locator('html').get_attribute('data-theme') == 'dark'
        page.set_viewport_size({'width':390,'height':844})
        page.get_by_role('button',name='باز کردن منو').click()
        sidebar = page.locator('.sidebar').bounding_box()
        topbar = page.locator('.topbar').bounding_box()
        assert sidebar['y'] + sidebar['height'] <= topbar['y'] + 1, (sidebar, topbar)
        page.get_by_role('link',name='پرونده بیماران').click()
        page.locator('a[href="/clinic/patients/11111111-1111-4111-8111-111111111111/"]').first.click()
        expect(page.get_by_role('heading',name='بیمار آزمایشی',exact=True)).to_be_visible()
        assert page.locator('[name=note]').is_disabled()
        assert page.locator('input[type=file]').is_disabled()
        assert page.evaluate('document.documentElement.scrollWidth') <= 390
        page.screenshot(path=str(output/'clinic-preview-mobile.png'),full_page=True)
        page.get_by_role('link',name='نمای بیمار',exact=True).click()
        expect(page.get_by_role('heading',name='پرتال بیمار',exact=True)).to_be_visible()
        assert page.locator('[name=phone]').is_disabled()
        assert page.locator('[name=reported_family_history]').is_disabled()
        page.set_viewport_size({'width':1440,'height':1050})
        page.screenshot(path=str(output/'patient-workspace-preview-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth')<=390
        page.screenshot(path=str(output/'patient-workspace-preview-mobile.png'),full_page=True)
        page.get_by_role('link',name='مشاهده نسخه ثبت‌شده و چاپ').click()
        expect(page.get_by_role('heading',name='راهنمای نمونه نمایشی',exact=True)).to_be_visible()
        page.emulate_media(media='print')
        expect(page.get_by_role('status')).to_be_visible()
        page.pdf(path=str(output/'clinic-preview-print.pdf'),format='A4',print_background=True)
        page.emulate_media(media='screen')
        page.goto(base+'/clinic/patients/11111111-1111-4111-8111-111111111111/')
        page.get_by_role('link',name='افزودن توصیه برای بیمار',exact=True).click()
        expect(page.get_by_role('heading',name='کتابخانه توصیه‌های بیمار')).to_be_visible()
        expect(page.locator('[data-advice-card]')).to_have_count(25)
        page.locator('#advice-search').fill('رِفلـاکس GERD')
        expect(page.locator('[data-advice-card]:visible')).to_have_count(1)
        page.locator('[name=advice_ids]:visible').check()
        page.locator('#advice-search').fill('فشار خون')
        page.locator('[name=specialty]').select_option('cardiology')
        expect(page.locator('[data-advice-card]:visible')).to_have_count(1)
        page.locator('[name=advice_ids]:visible').check()
        expect(page.locator('[data-selection-count]')).to_contain_text('۲')
        assert page.locator('[name=patient]').is_disabled()
        assert page.evaluate('document.documentElement.scrollWidth') <= 390
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(output/'education-library-mobile.png'),full_page=True)
        page.locator('[data-demo-combine]').click()
        expect(page.locator('.demo-print-stage .patient-guide')).to_have_count(2)
        expect(page.locator('.demo-print-stage .patient-guide').first).to_contain_text('رفلاکس')
        expect(page.locator('.demo-print-stage .patient-guide').nth(1)).to_contain_text('فشار خون')
        expect(page.locator('.demo-print-stage .packet-qr strong')).to_have_text('پرونده بیمار')
        page.evaluate('document.fonts.ready')
        assert page.locator('.demo-print-stage .print-brand img').first.evaluate('(img)=>img.complete&&img.naturalWidth>0')
        page.screenshot(path=str(output/'education-combined-mobile.png'),full_page=True)
        page.evaluate('()=>{window.__printCalls=0; window.print=()=>{window.__printCalls++; window.dispatchEvent(new Event("beforeprint"))}}')
        page.locator('.demo-print-stage .print-toolbar button').nth(1).click()
        page.wait_for_function('()=>window.__printCalls===1',timeout=2500)
        page.emulate_media(media='print')
        expect(page.locator('.demo-print-stage .draft-stamp')).to_have_count(0)
        expect(page.locator('.demo-print-stage .guide-source')).to_have_count(0)
        page.pdf(path=str(output/'education-preview-print.pdf'),format='A4',print_background=True,prefer_css_page_size=True,display_header_footer=False)
        bounds=output/'education-preview-bounds.html'
        subprocess.run(['pdftotext','-bbox',str(output/'education-preview-print.pdf'),str(bounds)],check=True)
        ns={'h':'http://www.w3.org/1999/xhtml'}
        pdf_pages=ET.parse(bounds).findall('.//h:page',ns)
        assert len(pdf_pages)>=2
        for pdf_page in pdf_pages:
            words=pdf_page.findall('h:word',ns)
            brands=[w for w in words if 'drgerami-md.ir' in (w.text or '')]
            assert len(brands)==1,[(w.text,w.attrib) for w in brands]
            brands.sort(key=lambda w:float(w.get('yMin')))
            assert float(brands[0].get('yMax'))<135
            assert all(43<=float(w.get('xMin')) and float(w.get('xMax'))<=552 for w in words), 'PDF text clipped outside A4 content margins'
        fonts=subprocess.check_output(['pdffonts',str(output/'education-preview-print.pdf')],text=True)
        assert 'Vazirmatn' in fonts and 'Liberation' not in fonts,fonts
        # A long bullet must wrap after table pagination rather than inherit
        # nowrap from the app's administrative tables.
        assert page.locator('.demo-print-stage li').first.evaluate('(e)=>getComputedStyle(e).whiteSpace')=='normal'
        page.emulate_media(media='screen')
        page.locator('.demo-print-stage .print-toolbar button').first.click()
        expect(page.locator('[data-library]')).to_be_visible()
        page.goto(base+'/clinic/patients/11111111-1111-4111-8111-111111111111/advice/')
        expect(page.locator('[data-advice-card]')).to_have_count(25)
        expect(page.locator('[data-demo-combine]')).to_be_enabled()
        page.goto(base+'/clinic/patients/11111111-1111-4111-8111-111111111111/summary/')
        expect(page.get_by_role('heading',name='خلاصه پرونده بیمار')).to_be_visible()
        expect(page.get_by_role('status')).to_contain_text('پیش‌نمایش آزمایشی')
        page.goto(base+'/clinic/visits/')
        expect(page.get_by_role('heading',name='ویزیت‌ها و پیگیری',exact=True)).to_be_visible()
        page.goto(base+'/clinic/prescriptions/')
        expect(page.locator('[data-prescription-window]')).to_have_count(3)
        assert page.locator('[name=reference]').is_disabled()
        page.goto(base+'/clinic/account/')
        assert page.locator('#shared-login [type=password]').is_disabled()
        assert page.locator('#shared-signup [type=password]').is_disabled()
        page.locator('[data-auth-mode=signup]').click()
        expect(page.locator('#shared-signup')).to_be_visible()
        assert page.locator('#shared-signup [name=username]').is_disabled()
        page.locator('[data-auth-mode=login]').click()
        expect(page.locator('#shared-login')).to_be_visible()
        assert not errors, errors
        assert not failures, failures
        assert all(method in ('GET','HEAD') and '/api/' not in url for method,url in requests), requests
        assert not page.locator('[name=csrfmiddlewaretoken]').count()
        browser.close()
        print('Preview browser check passed: desktop/mobile navigation, theme, disabled writes/uploads, print label, fonts/art, no API traffic')
finally:
    server.terminate()
    server.wait(timeout=5)
