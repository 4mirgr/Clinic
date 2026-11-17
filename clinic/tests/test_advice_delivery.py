import uuid
import threading
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import OperationalError, connection, connections
from django.db.models.query import QuerySet
from django.test import Client, TestCase, TransactionTestCase

from clinic.models import Advice, AuditEvent, Patient, PortalAccount


class AdviceDeliveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.doctor = User.objects.create_user('delivery-doctor')
        cls.doctor.groups.add(Group.objects.create(name='clinic_manager'))
        cls.secretary = User.objects.create_user('delivery-secretary')
        cls.secretary.groups.add(Group.objects.create(name='clinic_secretary'))
        cls.patient = Patient.objects.create(first_name='نمونه', last_name='آزمایشی', phone='09123456789')
        cls.other = Patient.objects.create(first_name='پرونده', last_name='دیگر', phone='09123456788')
        cls.member = User.objects.create_user('advice-patient')
        cls.account = PortalAccount.objects.create(user=cls.member, email='patient@example.test', patient=cls.patient)
        cls.advice = Advice.objects.create(title='توصیه آزمایشی کبد', body='نسخه اول\n\n<script>unsafe()</script>', tags='آزمایشی', source='منبع اول', is_approved=True, updated_by=cls.doctor)
        cls.draft = Advice.objects.create(title='پیش‌نویس پنهان', body='پیش‌نویس', updated_by=cls.doctor)

    def setUp(self):
        self.client.force_login(self.doctor)

    def delivery_model(self):
        return apps.get_model('clinic', 'AdviceDelivery')

    def select_url(self, patient=None):
        return f'/dash/patients/{(patient or self.patient).pk}/advice/'

    def confirm_url(self, advice=None, patient=None):
        return self.select_url(patient) + f'{(advice or self.advice).pk}/'

    def payload(self, **changes):
        return {'revision': self.advice.updated_at.isoformat(), 'request_key': str(uuid.uuid4()), **changes}

    def record(self):
        response = self.client.post(self.confirm_url(), self.payload())
        self.assertEqual(response.status_code, 302, response.content[:500])
        return self.delivery_model().objects.get()

    def patient_login(self, user=None, version=0):
        self.client.force_login(user or self.member)
        session = self.client.session
        session['portal_auth_version'] = version
        session.save()

    def test_selection_searches_approved_only_and_preview_does_not_record(self):
        response = self.client.get(self.select_url(), {'q': 'كبد'})
        self.assertContains(response, 'توصیه آزمایشی کبد')
        self.assertNotContains(response, 'پیش‌نویس پنهان')
        self.assertContains(self.client.get(self.confirm_url()), 'نسخه اول')
        self.assertEqual(self.delivery_model().objects.count(), 0)

    def test_record_keeps_original_snapshot_after_library_edit_or_withdrawal(self):
        delivery = self.record()
        self.advice.title = 'عنوان جدید'
        self.advice.body = 'نسخه دوم'
        self.advice.source = 'منبع دوم'
        self.advice.tags = 'جدید'
        self.advice.is_approved = False
        self.advice.save()
        page = self.client.get(delivery.get_absolute_url())
        for original in ['توصیه آزمایشی کبد', 'نسخه اول', 'منبع اول', 'آزمایشی']:
            self.assertContains(page, original)
        self.assertNotContains(page, 'نسخه دوم')
        self.assertContains(page, '&lt;script&gt;unsafe()&lt;/script&gt;')
        self.assertNotContains(page, '<script>unsafe()</script>')
        self.assertEqual(delivery.created_by, self.doctor)
        self.assertContains(self.client.get(self.patient.get_absolute_url()), delivery.get_absolute_url())
        self.assertContains(page, 'data:image/svg+xml;base64,')
        self.assertIn('no-store', page['Cache-Control'])
        self.assertNotIn('نسخه اول', str(list(AuditEvent.objects.values())))
        delivery.body = 'بازنویسی سابقه'
        with self.assertRaises(ValidationError):
            delivery.save()

    def test_changed_or_withdrawn_advice_requires_fresh_review(self):
        old = self.payload()
        self.advice.body = 'نسخه تازه'
        self.advice.save()
        self.assertEqual(self.client.post(self.confirm_url(), old).status_code, 409)
        self.advice.is_approved = False
        self.advice.save()
        self.assertEqual(self.client.post(self.confirm_url(), self.payload()).status_code, 409)
        self.assertEqual(self.client.get(self.confirm_url(self.draft)).status_code, 404)
        self.assertEqual(self.delivery_model().objects.count(), 0)

    def test_repeated_form_records_once_and_patient_in_payload_cannot_change_target(self):
        data = self.payload(patient=str(self.other.pk))
        first = self.client.post(self.confirm_url(), data)
        self.assertEqual(first.status_code, 302)
        second = self.client.post(self.confirm_url(), data)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(first['Location'], second['Location'])
        self.assertEqual(self.delivery_model().objects.count(), 1)
        self.assertEqual(self.delivery_model().objects.get().patient, self.patient)
        self.assertEqual(self.client.post(self.confirm_url(patient=self.other), data).status_code, 409)

    def test_invalid_or_incomplete_confirmation_does_not_record(self):
        for data in [{}, self.payload(request_key='invalid'), self.payload(revision='invalid')]:
            self.assertEqual(self.client.post(self.confirm_url(), data).status_code, 400)
        self.assertEqual(self.delivery_model().objects.count(), 0)

    @skipUnless(connection.vendor == 'sqlite', 'SQLite busy response')
    def test_persistent_contention_preserves_same_form_for_safe_retry(self):
        cause = sqlite3.OperationalError('database is locked')
        cause.sqlite_errorcode = sqlite3.SQLITE_BUSY
        error = OperationalError('database is locked')
        error.__cause__ = cause
        data = self.payload()
        with patch('clinic.advice_views.AdviceDelivery.objects.create', side_effect=error):
            response = self.client.post(self.confirm_url(), data)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response['Retry-After'], '1')
        self.assertContains(response, data['request_key'], status_code=503)
        self.assertEqual(self.delivery_model().objects.count(), 0)
        self.assertEqual(self.client.post(self.confirm_url(), data).status_code, 302)
        self.assertEqual(self.delivery_model().objects.count(), 1)

    def test_staff_assignment_requires_csrf_and_only_manager_role(self):
        delivery = self.record()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.doctor)
        self.assertEqual(csrf_client.post(self.confirm_url(), self.payload()).status_code, 403)
        for user in [self.secretary, self.member]:
            self.patient_login(user)
            for url in [self.select_url(), self.confirm_url()]:
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, self.payload()).status_code, 403)
        self.client.force_login(self.secretary)
        self.assertEqual(self.client.get(delivery.get_absolute_url()).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(delivery.get_absolute_url()).status_code, 302)

    def test_patient_sees_own_snapshot_but_other_accounts_and_website_admin_cannot(self):
        delivery = self.record()
        self.patient_login()
        self.assertContains(self.client.get('/dash/portal/'), delivery.get_absolute_url())
        self.assertContains(self.client.get(delivery.get_absolute_url()), 'نسخه اول')
        self.assertEqual(self.client.post(delivery.get_absolute_url(), {}).status_code, 405)
        stranger = User.objects.create_user('advice-stranger')
        account = PortalAccount.objects.create(user=stranger, email='stranger@example.test', patient=self.other, site_role='admin')
        self.patient_login(stranger)
        self.assertNotContains(self.client.get('/dash/portal/'), delivery.get_absolute_url())
        self.assertEqual(self.client.get(delivery.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.post(self.confirm_url(), self.payload()).status_code, 403)
        account.patient = None
        account.save()
        self.assertEqual(self.client.get(delivery.get_absolute_url()).status_code, 404)

    def test_patient_snapshot_checks_session_generation_and_active_status(self):
        delivery = self.record()
        self.patient_login(version=9)
        self.assertEqual(self.client.get(delivery.get_absolute_url()).status_code, 302)
        self.patient_login()
        self.member.is_active = False
        self.member.save()
        self.assertEqual(self.client.get(delivery.get_absolute_url()).status_code, 302)

    def test_secretary_with_linked_portal_account_still_has_no_advice_access(self):
        delivery = self.record()
        self.account.patient = None
        self.account.save()
        PortalAccount.objects.create(user=self.secretary, email='assistant@example.test', patient=self.patient)
        self.patient_login(self.secretary)
        self.assertNotContains(self.client.get('/dash/portal/'), delivery.get_absolute_url())
        self.assertEqual(self.client.get(delivery.get_absolute_url()).status_code, 403)

    def test_history_is_paginated_for_doctor_and_patient_without_losing_old_versions(self):
        urls = []
        for _ in range(21):
            response = self.client.post(self.confirm_url(), self.payload())
            self.assertEqual(response.status_code, 302)
            urls.append(response['Location'])
        for url in [self.patient.get_absolute_url(), '/dash/portal/']:
            if url == '/dash/portal/':
                self.patient_login()
            first = self.client.get(url)
            self.assertContains(first, urls[-1])
            self.assertNotContains(first, urls[0])
            self.assertContains(self.client.get(url, {'advice_page': 2}), urls[0])


class AdviceDeliveryConcurrencyTests(TransactionTestCase):
    @skipUnless(connection.vendor == 'sqlite', 'Reproduces SQLite deferred transaction contention')
    def test_simultaneous_same_form_retries_transaction_and_returns_one_snapshot(self):
        doctor = User.objects.create_user('concurrent-advice-doctor')
        doctor.groups.add(Group.objects.create(name='clinic_manager'))
        patient = Patient.objects.create(first_name='نمونه', last_name='هم‌زمان', phone='09123456789')
        advice = Advice.objects.create(title='نمونه آزمون', body='متن آزمون', is_approved=True, updated_by=doctor)
        clients = [Client(), Client()]
        for client in clients:
            client.force_login(doctor)
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        reads = 0
        original_first = QuerySet.first

        def simultaneous_key_read(queryset):
            nonlocal reads
            result = original_first(queryset)
            if queryset.model.__name__ == 'AdviceDelivery':
                with lock:
                    reads += 1
                    synchronize = reads <= 2
                if synchronize:
                    barrier.wait(timeout=5)
            return result

        data = {'revision': advice.updated_at.isoformat(), 'request_key': str(uuid.uuid4())}
        url = f'/dash/patients/{patient.pk}/advice/{advice.pk}/'

        def submit(client):
            try:
                return client.post(url, data)
            finally:
                connections.close_all()

        with patch.object(QuerySet, 'first', simultaneous_key_read), ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(submit, clients))
        self.assertEqual([response.status_code for response in responses], [302, 302])
        self.assertEqual(responses[0]['Location'], responses[1]['Location'])
        self.assertEqual(apps.get_model('clinic', 'AdviceDelivery').objects.count(), 1)
