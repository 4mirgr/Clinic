"""Generate a synthetic multi-page PDF and verify embedded fonts/branding.
Requires poppler-utils (pdfinfo, pdffonts, pdftotext); never reads checkout data.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
with tempfile.TemporaryDirectory(prefix='clinic-pdf-check-') as scratch:
    os.environ.update(CLINIC_ENV='development',DATABASE_URL='',CLINIC_DATA_DIR=scratch,
        DJANGO_SETTINGS_MODULE='config.settings',CLINIC_PUBLIC_URL='https://drgerami-md.ir/clinic',
        DJANGO_SECRET_KEY='synthetic-pdf-test-only-not-a-production-secret-8543189265074138')
    import django
    django.setup()
    from django.contrib.auth.models import User
    from django.core.management import call_command
    from clinic.advice_catalog import load_defaults
    from clinic.education_views import decorate,qr_for
    from clinic.education_pdf import pdf_response
    from clinic.models import Advice,Patient
    call_command('migrate',interactive=False,verbosity=0)
    doctor=User.objects.create_user('synthetic-pdf-doctor')
    load_defaults(doctor)
    patient=Patient.objects.create(id='11111111-1111-4111-8111-111111111111',first_name='بیمار',last_name='آزمایشی',phone='00000000000')
    guides=[decorate(Advice.objects.get(catalog_key=key)) for key in ['gerd','hypertension','diabetes','ckd']]
    response=pdf_response({'patient_name':patient.full_name,'guides':guides,'qr_data':qr_for(patient),'sample':True})
    output=ROOT/'test-results';output.mkdir(exist_ok=True)
    path=output/'education-demo.pdf';path.write_bytes(response.content)
    fonts=subprocess.check_output(['pdffonts',str(path)],text=True)
    info=subprocess.check_output(['pdfinfo',str(path)],text=True)
    extracted=subprocess.check_output(['pdftotext',str(path),'-'],text=True)
    pages=int(next(line.split(':')[1] for line in info.splitlines() if line.startswith('Pages:')))
    assert pages>=3,info
    assert 'Vazirmatn' in fonts,fonts
    fontlines=fonts.splitlines()[2:]
    assert fontlines and all('yes' in line for line in fontlines),fonts
    assert extracted.count('drgerami-md.ir')>=pages*2,(pages,extracted)
    assert 'GERD' in extracted and 'Hypertension' in extracted
    assert 'NIDDK' not in extracted and 'www.niddk.nih.gov' not in extracted
    assert 'NHS' not in extracted
    # Poppler emits bidi presentation order; don't equate it to Unicode source order.
    from PIL import Image
    import zxingcpp
    raster=Path(scratch)/'qr-page'
    subprocess.run(['pdftoppm','-r','160','-f',str(pages),'-singlefile','-png',str(path),str(raster)],check=True)
    codes=zxingcpp.read_barcodes(Image.open(str(raster)+'.png'))
    assert len(codes)==1 and codes[0].text=='https://drgerami-md.ir/clinic/patients/11111111-1111-4111-8111-111111111111/summary/',codes
    print('Final-page QR decoded successfully to the synthetic summary URL.')
    print(f'Synthetic PDF: {pages} pages, {len(response.content)} bytes; Vazirmatn embedded, bilingual text, repeated site branding. {path}')
    print(fonts)
