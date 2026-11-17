"""Check the public snapshot in Chromium against the actual preview Worker."""
import os
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
        page.get_by_role('link',name='مشاهده نسخه ثبت‌شده و چاپ').click()
        expect(page.get_by_role('heading',name='راهنمای نمونه نمایشی',exact=True)).to_be_visible()
        page.emulate_media(media='print')
        expect(page.get_by_role('status')).to_be_visible()
        page.pdf(path=str(output/'clinic-preview-print.pdf'),format='A4',print_background=True)
        assert not errors, errors
        assert not failures, failures
        assert all(method in ('GET','HEAD') and '/api/' not in url for method,url in requests), requests
        assert not page.locator('[name=csrfmiddlewaretoken]').count()
        browser.close()
        print('Preview browser check passed: desktop/mobile navigation, theme, disabled writes/uploads, print label, fonts/art, no API traffic')
finally:
    server.terminate()
    server.wait(timeout=5)
