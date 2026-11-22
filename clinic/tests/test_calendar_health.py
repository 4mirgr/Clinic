import json
from datetime import time, timedelta
from io import StringIO
from unittest.mock import patch
import uuid

from cryptography.fernet import Fernet
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.db import connection as database
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from requests import Timeout

from clinic.calendar_api import CalendarUnavailable
from clinic.calendar_health import diagnose_calendar
from clinic.calendar_models import AvailabilityOverride, CalendarConnection, ScheduleSettings
from clinic.tests.test_calendar import TEST_GOOGLE


@override_settings(**TEST_GOOGLE, GOOGLE_CALENDAR_ACCOUNT='dr.gerami.md@gmail.com', CLINIC_PREVIEW_EXPORT=False)
class CalendarHealthTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user('calendar-health-doctor')
        self.manager.groups.add(Group.objects.get_or_create(name='clinic_manager')[0])
        self.secretary = User.objects.create_user('calendar-health-secretary')
        self.secretary.groups.add(Group.objects.get_or_create(name='clinic_secretary')[0])
        self.member = User.objects.create_user('calendar-health-member')

    def connected(self):
        record = CalendarConnection(pk=1, owner=self.manager, active=True,
                                    account_email='dr.gerami.md@gmail.com', google_subject='synthetic-subject')
        record.set_refresh_token('synthetic-refresh-token-never-output')
        record.save()
        return record

    def hours(self):
        return ScheduleSettings.objects.create(pk=1, enabled=True, weekdays=[0, 1, 2, 3, 4],
                                               opens_at=time(9), closes_at=time(12), slot_minutes=20)

    def codes(self, result):
        return [issue['code'] for issue in result['issues']]

    def test_missing_configuration_reports_only_setting_names_without_network_or_writes(self):
        with override_settings(GOOGLE_CLIENT_ID='', GOOGLE_CLIENT_SECRET='', GOOGLE_TOKEN_ENCRYPTION_KEY=''):
            with patch('clinic.calendar_health.GoogleCalendar') as provider, CaptureQueriesContext(database) as captured:
                result = diagnose_calendar(probe=True)
        self.assertIn('not_configured', self.codes(result))
        self.assertIn('not_connected', self.codes(result))
        self.assertIn('working_hours_unset', self.codes(result))
        self.assertEqual(set(result['missing_settings']), {'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_TOKEN_ENCRYPTION_KEY'})
        self.assertFalse(result['can_connect']); self.assertFalse(result['probe_verified'])
        provider.assert_not_called()
        self.assertFalse(any(query['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for query in captured))
        self.assertFalse(ScheduleSettings.objects.exists())

    def test_invalid_key_https_redirect_and_expected_account_are_distinct_from_missing(self):
        with override_settings(GOOGLE_TOKEN_ENCRYPTION_KEY='invalid-secret-value',
                               GOOGLE_REDIRECT_URI='http://example.test/callback/?secret=must-not-appear',
                               GOOGLE_CALENDAR_ACCOUNT='invalid-account-value'):
            result = diagnose_calendar(probe=True)
        self.assertIn('invalid_configuration', self.codes(result))
        self.assertEqual(set(result['invalid_settings']), {'GOOGLE_TOKEN_ENCRYPTION_KEY', 'GOOGLE_REDIRECT_URI', 'GOOGLE_CALENDAR_ACCOUNT'})
        serialized = json.dumps(result)
        for secret in ('invalid-secret-value', 'must-not-appear', 'invalid-account-value'):
            self.assertNotIn(secret, serialized)

    def test_configured_but_missing_connection_never_probes(self):
        self.hours()
        with patch('clinic.calendar_health.GoogleCalendar') as provider:
            result = diagnose_calendar(probe=True)
        self.assertEqual(result['status'], 'not_connected')
        self.assertTrue(result['can_connect']); provider.assert_not_called()

    def test_stored_connection_without_subject_or_matching_account_is_not_ready(self):
        record = self.connected(); self.hours()
        for values in ({'google_subject': ''}, {'account_email': 'other@example.test'}):
            CalendarConnection.objects.filter(pk=record.pk).update(**values)
            with patch('clinic.calendar_health.GoogleCalendar') as provider:
                result = diagnose_calendar(probe=True)
            self.assertIn('account_mismatch', self.codes(result))
            self.assertFalse(result['can_probe']); provider.assert_not_called()

    def test_wrong_key_or_empty_token_requires_reconnect_not_provider_probe(self):
        record = self.connected(); self.hours()
        with override_settings(GOOGLE_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            with patch('clinic.calendar_health.GoogleCalendar') as provider:
                result = diagnose_calendar(probe=True)
        self.assertIn('token_key_mismatch', self.codes(result)); provider.assert_not_called()
        CalendarConnection.objects.filter(pk=record.pk).update(refresh_token_encrypted='')
        self.assertIn('token_key_mismatch', self.codes(diagnose_calendar()))

    def test_hours_missing_can_still_test_connection_without_claiming_booking_ready(self):
        self.connected()
        with patch('clinic.calendar_health.GoogleCalendar') as provider:
            result = diagnose_calendar(probe=True)
        self.assertTrue(result['probe_verified'])
        self.assertIn('working_hours_unset', self.codes(result)); self.assertFalse(result['local_ready'])
        provider.return_value.free_busy.assert_called_once()

    def test_override_only_hours_must_have_future_valid_sufficient_window(self):
        from clinic.jalali import today_tehran
        self.connected()
        schedule = self.hours(); schedule.weekdays = []; schedule.save()
        override = AvailabilityOverride.objects.create(day=today_tehran() - timedelta(days=1), windows=[{'start': '09:00', 'end': '10:00'}])
        self.assertFalse(diagnose_calendar()['hours_ready'])
        override.day = today_tehran() + timedelta(days=1); override.windows = [{'start': '09:00', 'end': '09:05'}]; override.save()
        self.assertFalse(diagnose_calendar()['hours_ready'])
        override.windows = [{'start': '09:00', 'end': '10:00'}]; override.save()
        self.assertTrue(diagnose_calendar()['hours_ready'])

    def test_default_local_check_does_not_claim_verified_or_contact_provider(self):
        self.connected(); self.hours()
        with patch('clinic.calendar_health.GoogleCalendar') as provider:
            result = diagnose_calendar()
        provider.assert_not_called()
        self.assertEqual(result['status'], 'locally_ready')
        self.assertFalse(result['probe_verified']); self.assertFalse(result['probe_attempted'])

    def test_explicit_probe_calls_only_short_future_freebusy_without_model_writes(self):
        self.connected(); self.hours(); before = timezone.now()
        with patch('clinic.calendar_health.GoogleCalendar') as provider, CaptureQueriesContext(database) as captured:
            result = diagnose_calendar(probe=True)
        self.assertEqual(result['status'], 'verified'); self.assertTrue(result['probe_verified'])
        instance = provider.return_value
        self.assertEqual([call[0] for call in instance.method_calls], ['free_busy'])
        start, end = instance.free_busy.call_args.args
        self.assertGreater(start, before); self.assertEqual(end - start, timedelta(minutes=10))
        self.assertFalse(any(query['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for query in captured))

    def test_failed_or_timed_out_probe_never_displays_provider_exception_or_claims_success(self):
        self.connected(); self.hours()
        for error in (CalendarUnavailable('private-provider-response'), Timeout('secret-token-in-exception')):
            with patch('clinic.calendar_health.GoogleCalendar') as provider:
                provider.return_value.free_busy.side_effect = error
                result = diagnose_calendar(probe=True)
            self.assertEqual(result['status'], 'provider_failed')
            self.assertFalse(result['probe_verified'])
            self.assertNotIn(str(error), json.dumps(result))

    def test_connection_replacement_or_disconnect_during_probe_invalidates_result(self):
        record = self.connected(); self.hours()
        for replacement in ({'generation': uuid.uuid4()}, {'active': False}):
            CalendarConnection.objects.filter(pk=record.pk).update(active=True)
            with patch('clinic.calendar_health.GoogleCalendar') as provider:
                provider.return_value.free_busy.side_effect = lambda *args: CalendarConnection.objects.filter(pk=record.pk).update(**replacement)
                result = diagnose_calendar(probe=True)
            self.assertEqual(result['status'], 'connection_changed'); self.assertFalse(result['probe_verified'])

    def test_preview_disables_real_connect_and_probe_but_preserves_official_manual_link(self):
        self.connected(); self.hours(); self.client.force_login(self.manager)
        with override_settings(CLINIC_PREVIEW_EXPORT=True):
            with patch('clinic.calendar_health.GoogleCalendar') as provider:
                result = diagnose_calendar(probe=True)
                response = self.client.get('/dash/calendar/')
        self.assertEqual(result['status'], 'private_backend_not_deployed')
        self.assertFalse(result['can_connect']); self.assertFalse(result['can_probe']); provider.assert_not_called()
        self.assertNotContains(response, 'action="' + reverse('calendar_connect') + '"')
        self.assertNotContains(response, 'action="' + reverse('calendar_connection_test') + '"')
        self.assertContains(response, 'https://calendar.google.com/calendar/u/0/r')

    def test_connection_test_is_manager_only_post_and_csrf_protected(self):
        url = reverse('calendar_connection_test')
        with patch('clinic.calendar_views.diagnose_calendar') as diagnose:
            self.assertEqual(self.client.post(url).status_code, 302)
            for user in (self.secretary, self.member):
                self.client.force_login(user)
                self.assertEqual(self.client.post(url).status_code, 403)
            self.client.force_login(self.manager)
            self.assertEqual(self.client.get(url).status_code, 405)
            csrf_client = Client(enforce_csrf_checks=True); csrf_client.force_login(self.manager)
            self.assertEqual(csrf_client.post(url).status_code, 403)
            diagnose.assert_not_called()

    def test_test_view_success_or_failure_does_not_confirm_or_mutate_appointments(self):
        self.connected(); self.hours(); self.client.force_login(self.manager)
        from clinic.calendar_models import Appointment
        with patch('clinic.calendar_health.GoogleCalendar') as provider:
            response = self.client.post(reverse('calendar_connection_test'), follow=True)
        self.assertContains(response, 'FreeBusy')
        self.assertFalse(Appointment.objects.exists())
        self.assertEqual([call[0] for call in provider.return_value.method_calls], ['free_busy'])
        with patch('clinic.calendar_health.GoogleCalendar') as provider:
            provider.return_value.free_busy.side_effect = Timeout('private-secret')
            response = self.client.post(reverse('calendar_connection_test'), follow=True)
        self.assertContains(response, 'هیچ نوبتی تأیید نشده')
        self.assertNotContains(response, 'private-secret'); self.assertFalse(Appointment.objects.exists())

    def test_secretary_summary_excludes_configuration_profile_and_account_email(self):
        self.connected(); self.hours(); self.client.force_login(self.secretary)
        response = self.client.get('/dash/calendar/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('missing_settings', response.context['calendar_health'])
        for value in ('dr.gerami.md@gmail.com', TEST_GOOGLE['GOOGLE_CLIENT_SECRET'], 'synthetic-refresh-token-never-output', 'GOOGLE_CLIENT_ID'):
            self.assertNotContains(response, value)
        self.assertNotContains(response, 'بررسی اتصال بدون ساخت نوبت')

    def test_command_defaults_local_and_probe_is_explicit_without_sensitive_output(self):
        self.connected(); self.hours()
        output = StringIO()
        with patch('clinic.calendar_health.GoogleCalendar') as provider:
            call_command('check_calendar', '--json', stdout=output)
        provider.assert_not_called()
        result = json.loads(output.getvalue()); self.assertFalse(result['probe_verified'])
        output = StringIO()
        with patch('clinic.calendar_health.GoogleCalendar') as provider:
            call_command('check_calendar', '--probe', '--json', stdout=output)
        self.assertTrue(json.loads(output.getvalue())['probe_verified'])
        self.assertEqual([call[0] for call in provider.return_value.method_calls], ['free_busy'])
        for secret in (TEST_GOOGLE['GOOGLE_CLIENT_SECRET'], TEST_GOOGLE['GOOGLE_TOKEN_ENCRYPTION_KEY'], 'synthetic-refresh-token-never-output'):
            self.assertNotIn(secret, output.getvalue())
