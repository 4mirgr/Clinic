import json
from io import StringIO

from django.apps import apps
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase

from clinic.models import Advice, Patient, PortalAccount


class EducationLibraryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.doctor = User.objects.create_user('library-doctor')
        cls.doctor.groups.add(Group.objects.create(name='clinic_manager'))
        cls.secretary = User.objects.create_user('library-secretary')
        cls.secretary.groups.add(Group.objects.create(name='clinic_secretary'))
        cls.patient = Patient.objects.create(first_name='بیمار', last_name='آزمایشی', phone='09123456789', history='یادداشت داخلی محرمانه', medications='داروی داخلی محرمانه')
        cls.member = User.objects.create_user('library-member')
        cls.account = PortalAccount.objects.create(user=cls.member, patient=cls.patient, email='library@example.test')

    def setUp(self):
        self.client.force_login(self.doctor)

    def load(self):
        call_command('load_default_advice', reviewer=self.doctor.username, stdout=StringIO())

    def test_default_import_is_draft_categorized_bilingual_and_non_destructive(self):
        self.load()
        self.assertEqual(Advice.objects.count(), 24)
        self.assertEqual(Advice.objects.values('specialty').distinct().count(), 12)
        self.assertFalse(Advice.objects.filter(is_approved=True).exists())
        item = Advice.objects.get(catalog_key='gerd')
        self.assertIn('GERD', item.title_en)
        self.assertIn('## ', item.body)
        self.assertIn('https://www.niddk.nih.gov/', item.source)
        item.body = 'متن اصلاح‌شده شخصی پزشک'
        item.save()
        self.load()
        self.assertEqual(Advice.objects.count(), 24)
        item.refresh_from_db()
        self.assertEqual(item.body, 'متن اصلاح‌شده شخصی پزشک')
        with self.assertRaises(CommandError):
            call_command('load_default_advice', reviewer=self.secretary.username, stdout=StringIO())

    def test_search_matches_persian_arabic_english_tags_and_specialty(self):
        self.load()
        from clinic.advice_catalog import search_advice
        for query in ['GERD', 'gerd', 'ريفلاكس', 'رِفلـاکس', 'گوارش GERD', 'heartburn']:
            self.assertIn('gerd', list(search_advice(query).values_list('catalog_key', flat=True)), query)
        self.assertEqual(set(search_advice('', 'gastroenterology').values_list('catalog_key', flat=True)), {'gerd','constipation'})
        self.assertFalse(search_advice('این واژه در کتابخانه نیست').exists())
        page = self.client.get('/dash/advice/')
        self.assertContains(page, 'name="advice_ids"')
        self.assertContains(page, 'GERD')
        self.assertContains(page, 'قلب و عروق')

    def test_editing_patient_text_invalidates_prior_approval(self):
        item = Advice.objects.create(title='تأیید قبلی', body='متن اول', is_approved=True, updated_by=self.doctor)
        item.body = 'متن تازه بدون بازبینی'
        item.save()
        item.refresh_from_db()
        self.assertFalse(item.is_approved)

    def prepare(self, ids):
        response = self.client.post('/dash/advice/bundles/prepare/', {'patient':str(self.patient.pk), 'advice_ids':[str(pk) for pk in ids]})
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.context['review_token']

    def record(self, token):
        response = self.client.post('/dash/advice/bundles/confirm/', {'review_token':token, 'reviewed':'on'})
        self.assertEqual(response.status_code, 302, response.content[:300])
        return apps.get_model('clinic', 'AdvicePacket').objects.get()

    def patient_login(self):
        self.client.force_login(self.member)
        session = self.client.session
        session['portal_auth_version'] = 0
        session.save()

    def test_packet_records_exact_reviewed_order_and_does_not_duplicate_on_retry(self):
        self.load()
        a,b = Advice.objects.get(catalog_key='gerd'), Advice.objects.get(catalog_key='hypertension')
        token = self.prepare([b.pk,a.pk])
        packet = self.record(token)
        self.assertEqual([x.advice_id for x in packet.deliveries.order_by('position')], [b.pk,a.pk])
        self.assertTrue(Advice.objects.get(pk=a.pk).is_approved)
        self.assertEqual(self.client.post('/dash/advice/bundles/confirm/', {'review_token':token,'reviewed':'on'}).status_code, 302)
        self.assertEqual(apps.get_model('clinic','AdvicePacket').objects.count(), 1)
        self.patient.first_name = 'نام تازه'
        self.patient.save()
        a.body = 'توصیه تازه'
        a.save()
        page = self.client.get(packet.get_absolute_url())
        self.assertContains(page, 'بیمار آزمایشی')
        self.assertNotContains(page, 'توصیه تازه')
        self.assertContains(page, 'پرونده بیمار')

    def test_stale_or_forged_review_is_rejected_without_approving_any_source(self):
        self.load()
        a=Advice.objects.get(catalog_key='gerd')
        token=self.prepare([a.pk])
        a.body += '\nمتن تازه'
        a.save()
        self.assertEqual(self.client.post('/dash/advice/bundles/confirm/', {'review_token':token,'reviewed':'on'}).status_code,409)
        self.assertEqual(self.client.post('/dash/advice/bundles/confirm/', {'review_token':token+'bad','reviewed':'on'}).status_code,400)
        self.assertEqual(self.client.post('/dash/advice/bundles/confirm/', {'review_token':self.prepare([a.pk])}).status_code,400)
        self.assertEqual(apps.get_model('clinic','AdvicePacket').objects.count(),0)
        self.assertFalse(Advice.objects.filter(is_approved=True).exists())

    def test_summary_is_explicitly_published_and_no_private_notes_are_exposed(self):
        url=f'/dash/patients/{self.patient.pk}/summary/'
        self.patient_login()
        page=self.client.get(url)
        self.assertEqual(page.status_code,200)
        self.assertNotContains(page,'یادداشت داخلی محرمانه')
        self.assertNotContains(page,'داروی داخلی محرمانه')
        self.client.force_login(self.doctor)
        data={'history':'خلاصه مجاز','conditions':'بیماری پیشین مجاز','health_status':'وضعیت مجاز','medications':'فهرست داروی مجاز','progress':'پیشرفت مجاز','publish':'on'}
        self.assertEqual(self.client.post(url+'edit/',data).status_code,302)
        self.patient_login()
        self.assertContains(self.client.get(url),'خلاصه مجاز')
        self.client.force_login(self.doctor)
        data.pop('publish')
        data['history']='پیش‌نویس جدید پنهان'
        self.client.post(url+'edit/',data)
        self.patient_login()
        page=self.client.get(url)
        self.assertContains(page,'خلاصه مجاز')
        self.assertNotContains(page,'پیش‌نویس جدید پنهان')
        self.assertIn('no-store',page['Cache-Control'])
        self.client.force_login(self.doctor)
        self.client.post(url+'withdraw/')
        self.patient_login()
        self.assertNotContains(self.client.get(url),'خلاصه مجاز')

    def test_packet_and_summary_are_patient_scoped_and_secretary_cannot_read_or_write(self):
        self.load()
        token=self.prepare([Advice.objects.get(catalog_key='gerd').pk])
        packet=self.record(token)
        urls=[packet.get_absolute_url(),packet.get_absolute_url()+'pdf/',f'/dash/patients/{self.patient.pk}/summary/']
        self.patient_login()
        for url in urls:
            self.assertEqual(self.client.get(url).status_code,200,url)
        session=self.client.session
        session['portal_auth_version']=9
        session.save()
        self.assertEqual(self.client.get(urls[-1]).status_code,302)
        stranger=User.objects.create_user('library-stranger')
        PortalAccount.objects.create(user=stranger,email='stranger@sample.test',site_role='admin')
        self.client.force_login(stranger)
        session=self.client.session
        session['portal_auth_version']=0
        session.save()
        for url in urls:
            self.assertEqual(self.client.get(url).status_code,404,url)
        self.client.force_login(self.secretary)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code,403,url)
        self.assertEqual(self.client.post('/dash/advice/bundles/confirm/', {'review_token':token,'reviewed':'on'}).status_code,403)
        csrf=Client(enforce_csrf_checks=True)
        csrf.force_login(self.doctor)
        self.assertEqual(csrf.post('/dash/advice/bundles/prepare/',{}).status_code,403)

    def test_pdf_has_real_pdf_bytes_and_branded_html_has_structured_lists(self):
        self.load()
        packet=self.record(self.prepare(list(Advice.objects.filter(catalog_key__in=['gerd','hypertension']).values_list('pk',flat=True))))
        page=self.client.get(packet.get_absolute_url())
        self.assertContains(page,'<ul>')
        self.assertContains(page,'patient-name')
        self.assertRegex(page.content.decode(), r'brand/logo(?:\.[a-f0-9]+)?\.webp')
        pdf=self.client.get(packet.get_absolute_url()+'pdf/')
        self.assertEqual(pdf['Content-Type'],'application/pdf')
        self.assertTrue(pdf.content.startswith(b'%PDF-'))
        self.assertIn('no-store',pdf['Cache-Control'])

    def test_linked_secretary_portal_does_not_expose_packet_history(self):
        self.load()
        packet=self.record(self.prepare([Advice.objects.get(catalog_key='gerd').pk]))
        self.account.patient=None;self.account.save()
        PortalAccount.objects.create(user=self.secretary,patient=self.patient,email='secretary-library@example.test')
        self.client.force_login(self.secretary)
        session=self.client.session;session['portal_auth_version']=0;session.save()
        page=self.client.get('/dash/portal/')
        self.assertEqual(page.status_code,200)
        self.assertNotContains(page,packet.get_absolute_url())
        self.assertNotContains(page,f'/dash/patients/{self.patient.pk}/summary/')

    def test_qr_login_retains_local_destination_and_rejects_external_redirect(self):
        self.doctor.set_password('Isolated-library-login-73!');self.doctor.save()
        url=f'/dash/patients/{self.patient.pk}/summary/'
        self.client.logout()
        response=self.client.get(url)
        self.assertEqual(response.status_code,302)
        self.assertIn('next=',response.url)
        page=self.client.get(response.url)
        self.assertContains(page,'next=')
        response=self.client.post('/dash/login/manager/',{'username':self.doctor.username,'password':'Isolated-library-login-73!'},QUERY_STRING='next='+url)
        self.assertRedirects(response,url,fetch_redirect_response=False)
        self.client.logout()
        response=self.client.get('/dash/portal/',{'next':url})
        self.assertIn('summary',response.url)
        self.client.logout()
        response=self.client.post('/dash/login/manager/?next=https://example.com',{'username':self.doctor.username,'password':'Isolated-library-login-73!'})
        self.assertRedirects(response,'/dash/',fetch_redirect_response=False)

    def test_packet_order_tampering_and_source_markup_do_not_escape_review(self):
        from django.core import signing
        from clinic.education_views import SALT
        self.load()
        a,b=list(Advice.objects.all()[:2])
        a.body='## <img src="https://example.test/leak">\n- <script>bad()</script>'
        a.save()
        token=self.prepare([a.pk,b.pk])
        packet=self.record(token)
        page=self.client.get(packet.get_absolute_url())
        self.assertContains(page,'&lt;script&gt;bad()&lt;/script&gt;')
        self.assertNotContains(page,'<script>bad()</script>')
        payload=signing.loads(token,salt=SALT)
        payload['items'].reverse()
        forged=signing.dumps(payload,salt=SALT)
        self.assertEqual(self.client.post('/dash/advice/bundles/confirm/',{'review_token':forged,'reviewed':'on'}).status_code,409)
        self.assertEqual(packet.deliveries.count(),2)

    def test_patient_entry_opens_full_catalog_and_final_packet_omits_editorial_metadata(self):
        self.load()
        page=self.client.get(self.patient.get_absolute_url())
        self.assertRegex(page.content.decode(),r'href="/dash/advice/\?patient='+str(self.patient.pk)+r'">افزودن توصیه برای بیمار</a>')
        guide=Advice.objects.get(catalog_key='gerd')
        token=self.prepare([guide.pk])
        review=self.client.post('/dash/advice/bundles/prepare/',{'patient':str(self.patient.pk),'advice_ids':[str(guide.pk)]})
        self.assertContains(review,'منابع و بازبینی')
        packet=self.record(token)
        final=self.client.get(packet.get_absolute_url())
        self.assertNotContains(final,'منابع و بازبینی')
        self.assertNotContains(final,'niddk.nih.gov')
        self.assertNotContains(final,'draft-stamp')
        self.assertIn('niddk.nih.gov',packet.deliveries.get().source)


from concurrent.futures import ThreadPoolExecutor
import threading
from unittest.mock import patch
from django.db import connections
from django.db.models.query import QuerySet
from django.test import TransactionTestCase


class PacketConcurrencyTests(TransactionTestCase):
    def test_duplicate_review_concurrently_records_one_packet(self):
        import uuid
        from clinic.education_views import record_packet
        from clinic.models import AdvicePacket, AdviceDelivery
        doctor=User.objects.create_user('packet-race-doctor')
        doctor.groups.add(Group.objects.get_or_create(name='clinic_manager')[0])
        patient=Patient.objects.create(first_name='نمونه',last_name='هم‌زمانی',phone='00000000000')
        advice=Advice.objects.create(title='آزمون هم‌زمانی',body='متن بازبینی‌شده',updated_by=doctor)
        payload={'actor':doctor.pk,'patient':str(patient.pk),'nonce':str(uuid.uuid4()),'items':[[str(advice.pk),advice.updated_at.isoformat()]]}
        barrier=threading.Barrier(2)
        local=threading.local()
        original=QuerySet.first
        def first(queryset):
            value=original(queryset)
            if queryset.model is AdvicePacket and not getattr(local,'waited',False):
                local.waited=True
                barrier.wait(timeout=10)
            return value
        def record():
            connections.close_all()
            try:
                return record_packet(payload,User.objects.get(pk=doctor.pk)).pk
            finally:
                connections.close_all()
        with patch.object(QuerySet,'first',first):
            with ThreadPoolExecutor(max_workers=2) as pool:
                ids=list(pool.map(lambda _:record(),range(2)))
        self.assertEqual(ids[0],ids[1])
        self.assertEqual(AdvicePacket.objects.count(),1)
        self.assertEqual(AdviceDelivery.objects.count(),1)
