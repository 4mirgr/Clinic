"""PDF rendering with embedded local assets and no remote resource access."""
import base64
from pathlib import Path
from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML, CSS
from weasyprint.urls import URLFetcher
from weasyprint.text.fonts import FontConfiguration


def data_uri(path,mime):
    return 'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode('ascii')


only_embedded = URLFetcher(allowed_protocols={'data'}, allow_redirects=False, fail_on_errors=True)

def pdf_response(context):
    root=Path(settings.BASE_DIR)/'static/clinic'
    context=dict(context,pdf_logo=data_uri(root/'brand/logo.webp','image/webp'))
    css=(root/'education.css').read_text()
    for weight in ('regular','semibold'):
        css=css.replace('fonts/vazirmatn-print-'+weight+'.ttf',data_uri(root/f'fonts/vazirmatn-print-{weight}.ttf','font/ttf'))
    # WeasyPrint margin boxes repeat the running brand on every A4 page.
    css+='''\n@page { @top-center {content:element(brand);width:176mm} @bottom-center {content:element(footer);width:176mm} }
    .print-brand {position:running(brand);height:auto;width:100%;top:auto;left:auto;right:auto}
    .page-number {flex:0 0 16mm;direction:ltr;font-size:9px}.page-number:after {content:counter(page) ' / ' counter(pages)}
    .packet-qr {width:100%;max-width:none;margin:8mm 0 0;text-align:center}.packet-qr img {display:inline-block;margin:0}
    .print-footer {position:running(footer);bottom:auto;margin:0} body{background:white;font-size:11pt}.packet-sheet{padding:0;margin:0;box-shadow:none}.patient-guide h1{font-size:16pt}.patient-guide h2{font-size:12pt}.patient-guide li{font-size:11pt}.guide-source{font-size:8pt}
    '''
    html='<html lang="fa" dir="rtl"><head><meta charset="utf-8"></head><body class="packet-body">'+render_to_string('clinic/education/packet_content.html',context)+'</body></html>'
    font_config=FontConfiguration()
    content=HTML(string=html,url_fetcher=only_embedded).write_pdf(stylesheets=[CSS(string=css,url_fetcher=only_embedded,font_config=font_config)],font_config=font_config,pdf_tags=True)
    response=HttpResponse(content,content_type='application/pdf')
    response['Content-Disposition']='inline; filename="patient-instructions.pdf"'
    response['Cache-Control']='private, no-store'
    return response
