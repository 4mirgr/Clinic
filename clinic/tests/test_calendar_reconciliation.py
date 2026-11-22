import json
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from clinic.calendar_api import CalendarUnavailable, GoogleCalendar
from clinic.calendar_models import Appointment, CalendarConnection, ScheduleSettings
from clinic.calendar_reconciliation import reconcile_calendar
from clinic.models import AuditEvent, Patient
from clinic.scheduling import BookingError, request_cancellation, reschedule_appointment, sync_appointment
from clinic.tests.test_calendar import TEST_GOOGLE


class InspectOwnedEventTests(SimpleTestCase):
    def setUp(self):
        key = uuid.uuid4()
        start = datetime(2030, 1, 7, 9, tzinfo=dt_timezone.utc)
        self.appointment = SimpleNamespace(pk=key, google_event_id=key.hex,
                                           starts_at=start, ends_at=start+timedelta(minutes=20))
        self.transport = Mock()
        self.provider = GoogleCalendar(SimpleNamespace(calendar_id='primary'), session=self.transport)

    def event(self):
        a = self.appointment
        return {'id': a.pk.hex, 'status': 'confirmed',
                'extendedProperties': {'private': {'appointment_id': str(a.pk)}},
                'start': {'dateTime': a.starts_at.isoformat()},
                'end': {'dateTime': a.ends_at.isoformat()}, 'summary': 'not-for-reports'}

    def respond(self, body=None, status=200):
        response = Mock(status_code=status)
        response.json.return_value = self.event() if body is None else body
        self.transport.request.return_value = response
        return self.provider.inspect_event(self.appointment)

    def test_matching_and_moved_are_exact_owned_gets_with_aware_times(self):
        self.assertEqual(self.respond(), {'state': 'matching'})
        event = self.event()
        event['start']['dateTime'] = (self.appointment.starts_at+timedelta(hours=1)).isoformat()
        event['end']['dateTime'] = (self.appointment.ends_at+timedelta(hours=1)).isoformat()
        moved = self.respond(event)
        self.assertEqual(moved['state'], 'moved')
        self.assertTrue(timezone.is_aware(moved['starts_at']))
        self.assertEqual(set(moved), {'state', 'starts_at', 'ends_at'})
        for call in self.transport.request.call_args_list:
            self.assertEqual(call.args, ('GET', self.provider.events_url+'/'+self.appointment.pk.hex))
            self.assertNotIn('json', call.kwargs)

    def test_timezone_offset_is_compared_as_an_instant(self):
        event = self.event()
        offset = dt_timezone(timedelta(hours=3, minutes=30))
        event['start']['dateTime'] = self.appointment.starts_at.astimezone(offset).isoformat()
        event['end']['dateTime'] = self.appointment.ends_at.astimezone(offset).isoformat()
        self.assertEqual(self.respond(event), {'state': 'matching'})

    def test_missing_codes_and_verified_cancellation(self):
        for status in (404, 410):
            self.assertEqual(self.respond(status=status), {'state': 'missing'})
        event = self.event()
        event['status'] = 'cancelled'
        event.pop('start'); event.pop('end')
        self.assertEqual(self.respond(event), {'state': 'missing'})

    def test_sparse_cancelled_tombstone_uses_stored_owned_id_proof(self):
        tombstone = {'id': self.appointment.pk.hex, 'status': 'cancelled'}
        self.assertEqual(self.respond(tombstone), {'state': 'missing'})
        tombstone['extendedProperties'] = {'private': {'appointment_id': str(uuid.uuid4())}}
        self.assertEqual(self.respond(tombstone), {'state': 'unknown'})
        tombstone.pop('extendedProperties')
        tombstone['id'] = uuid.uuid4().hex
        self.assertEqual(self.respond(tombstone), {'state': 'unknown'})
        self.transport.request.reset_mock()
        self.appointment.google_event_id = 'foreign-id'
        self.assertEqual(self.respond({'id': self.appointment.pk.hex, 'status': 'cancelled'}), {'state': 'unknown'})
        self.transport.request.assert_not_called()

    def test_untrusted_or_malformed_event_never_becomes_a_missing_event(self):
        cases = [[], {}, {'id': self.appointment.pk.hex, 'status': 'confirmed'},
                 {'id': self.appointment.pk.hex, 'status': 'cancelled', 'extendedProperties': None}]
        event = self.event(); event['id'] = uuid.uuid4().hex; cases.append(event)
        event = self.event(); event['extendedProperties']['private']['appointment_id'] = str(uuid.uuid4()); cases.append(event)
        event = self.event(); event['start'] = {'date': '2030-01-07'}; cases.append(event)
        event = self.event(); event['start']['dateTime'] = '2030-01-07T09:00:00'; cases.append(event)
        event = self.event(); event['end'] = event['start']; cases.append(event)
        event = self.event(); event['status'] = 'unrecognized'; cases.append(event)
        for body in cases:
            with self.subTest(body_type=type(body).__name__):
                self.assertEqual(self.respond(body), {'state': 'unknown'})
        self.transport.request.return_value.json.side_effect = ValueError('private-provider-content')
        self.assertEqual(self.provider.inspect_event(self.appointment), {'state': 'unknown'})

    def test_bad_local_event_identifier_never_reaches_google(self):
        self.appointment.google_event_id = 'personal-event'
        self.assertEqual(self.provider.inspect_event(self.appointment), {'state': 'unknown'})
        self.transport.request.assert_not_called()

    def test_provider_error_is_not_reported_as_deletion(self):
        for status in (401, 403, 429, 500):
            with self.assertRaises(CalendarUnavailable):
                self.respond(status=status)


@override_settings(**TEST_GOOGLE)
class ReconciliationTests(TransactionTestCase):
    def setUp(self):
        self.actor = User.objects.create_user('reconciliation-doctor')
        self.patient = Patient.objects.create(first_name='Synthetic', last_name='Reconciliation', phone='00000000000')
        self.binding = CalendarConnection(pk=1, owner=self.actor, active=True,
            account_email=settings.GOOGLE_CALENDAR_ACCOUNT, google_subject='synthetic-subject')
        self.binding.set_refresh_token('synthetic-refresh-only')
        self.binding.save()
        ScheduleSettings.objects.create(pk=1)
        self.start = timezone.now().replace(second=0, microsecond=0)+timedelta(days=2)
        self.appointment = self.make_appointment()
        self.provider = Mock()
        self.provider.inspect_event.return_value = {'state': 'matching'}
        self.provider_patch = patch('clinic.calendar_reconciliation.GoogleCalendar', return_value=self.provider)
        self.factory = self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)

    def make_appointment(self, **overrides):
        data = {'patient': self.patient, 'created_by': self.actor, 'starts_at': self.start,
                'ends_at': self.start+timedelta(minutes=20), 'status': 'confirmed',
                'connection_generation': self.binding.generation}
        data.update(overrides)
        appointment = Appointment.objects.create(**data)
        appointment.google_event_id = appointment.pk.hex
        appointment.save(update_fields=['google_event_id'])
        return appointment

    def moved(self, hours=2):
        return {'state': 'moved', 'starts_at': self.start+timedelta(hours=hours),
                'ends_at': self.start+timedelta(hours=hours, minutes=20)}

    def run_probe(self, **kwargs):
        return reconcile_calendar(probe=True, actor=self.actor, **kwargs)

    def test_default_command_is_local_read_only_and_flag_requires_probe(self):
        output = StringIO()
        with CaptureQueriesContext(connection) as queries:
            call_command('reconcile_calendar', stdout=output)
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries))
        self.factory.assert_not_called()
        self.assertIn('local_only', output.getvalue())
        self.assertNotIn(self.patient.first_name, output.getvalue())
        self.assertNotIn(str(self.appointment.pk), output.getvalue())
        for option in ('--flag-reviewed-mismatches', '--apply-google'):
            with self.assertRaises(CommandError):
                call_command('reconcile_calendar', option, stdout=StringIO())
        with self.assertRaises(ValueError):
            self.run_probe(apply_google=True, flag_reviewed_mismatches=True)
        self.assertFalse(AuditEvent.objects.exists())

    def test_report_only_does_not_write_or_hold_locks_during_provider_read(self):
        def inspect(appointment):
            self.assertFalse(connection.in_atomic_block)
            return self.moved()
        self.provider.inspect_event.side_effect = inspect
        before = Appointment.objects.values().get()
        with CaptureQueriesContext(connection) as queries:
            report = self.run_probe()
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('UPDATE', 'INSERT', 'DELETE')) for q in queries))
        self.assertEqual(report['moved'], 1)
        self.assertEqual(Appointment.objects.values().get(), before)
        self.assertFalse(AuditEvent.objects.exists())
        self.assertEqual([call[0] for call in self.provider.mock_calls], ['inspect_event'])

    def test_explicit_flag_preserves_holds_and_blocks_force_retry_edit_and_cancel(self):
        for state in ('moved', 'missing'):
            with self.subTest(state=state):
                Appointment.objects.filter(pk=self.appointment.pk).update(status='confirmed', calendar_review_required=False, last_error='')
                self.provider.inspect_event.return_value = self.moved() if state == 'moved' else {'state': state}
                report = self.run_probe(flag_reviewed_mismatches=True)
                self.appointment.refresh_from_db()
                self.assertEqual(report['flagged'], 1)
                self.assertEqual(self.appointment.status, 'attention')
                self.assertTrue(self.appointment.calendar_review_required)
                self.assertEqual(self.appointment.starts_at, self.start)
                self.assertIn(self.appointment.status, Appointment.RESERVING)
                provider = Mock()
                sync_appointment(self.appointment.pk, self.actor, provider=provider, force=True)
                with self.assertRaises(BookingError):
                    request_cancellation(self.appointment.pk, self.actor, provider=provider)
                with self.assertRaises(BookingError):
                    reschedule_appointment(self.appointment.pk, self.start.date(), self.start, self.actor, provider=provider)
                self.assertFalse(provider.mock_calls)

    def test_matching_only_clears_flag_with_explicit_write_mode(self):
        self.provider.inspect_event.return_value = {'state': 'missing'}
        self.run_probe(flag_reviewed_mismatches=True)
        self.provider.inspect_event.return_value = {'state': 'matching'}
        self.run_probe()
        self.appointment.refresh_from_db()
        self.assertTrue(self.appointment.calendar_review_required)
        report = self.run_probe(flag_reviewed_mismatches=True)
        self.appointment.refresh_from_db()
        self.assertEqual(report['restored'], 1)
        self.assertEqual(self.appointment.status, 'confirmed')
        self.assertFalse(self.appointment.calendar_review_required)
        self.assertTrue(AuditEvent.objects.filter(action='calendar.reconcile_restored').exists())

    def test_explicit_apply_adopts_move_even_outside_working_hours_without_google_write(self):
        self.provider.inspect_event.return_value = self.moved()
        report = self.run_probe(apply_google=True)
        self.appointment.refresh_from_db()
        self.assertEqual(report['applied_moved'], 1)
        self.assertEqual(self.appointment.starts_at, self.moved()['starts_at'])
        self.assertEqual(self.appointment.status, 'confirmed')
        self.assertFalse(self.appointment.calendar_review_required)
        self.assertEqual([call[0] for call in self.provider.mock_calls], ['inspect_event'])
        self.assertTrue(AuditEvent.objects.filter(action='calendar.reconcile_adopt_move').exists())

    def test_explicit_apply_missing_cancels_locally_without_removing_record_or_recreating_event(self):
        self.provider.inspect_event.return_value = {'state': 'missing'}
        report = self.run_probe(apply_google=True)
        self.appointment.refresh_from_db()
        self.assertEqual(report['applied_missing'], 1)
        self.assertEqual(self.appointment.status, 'cancelled')
        self.assertFalse(self.appointment.calendar_review_required)
        self.assertEqual(Appointment.objects.count(), 1)
        provider = Mock()
        sync_appointment(self.appointment.pk, provider=provider, force=True)
        self.assertFalse(provider.mock_calls)
        self.assertTrue(AuditEvent.objects.filter(action='calendar.reconcile_adopt_delete').exists())

    def test_colliding_google_move_preserves_original_and_previous_holds(self):
        moved = self.moved()
        self.make_appointment(starts_at=moved['starts_at'], ends_at=moved['ends_at'], status='pending')
        previous = self.start-timedelta(hours=1)
        Appointment.objects.filter(pk=self.appointment.pk).update(previous_starts_at=previous, previous_ends_at=previous+timedelta(minutes=20))
        self.provider.inspect_event.return_value = moved
        report = self.run_probe(apply_google=True)
        self.appointment.refresh_from_db()
        self.assertEqual(report['overlap'], 1)
        self.assertEqual(report['applied_moved'], 0)
        self.assertEqual(self.appointment.starts_at, self.start)
        self.assertEqual(self.appointment.previous_starts_at, previous)
        self.assertEqual(self.appointment.status, 'attention')
        self.assertTrue(self.appointment.calendar_review_required)

    def test_overlap_with_another_previous_hold_is_also_rejected(self):
        moved = self.moved()
        self.make_appointment(starts_at=self.start+timedelta(hours=4), ends_at=self.start+timedelta(hours=4, minutes=20),
            previous_starts_at=moved['starts_at']-timedelta(minutes=5), previous_ends_at=moved['ends_at'], status='update_pending')
        self.provider.inspect_event.return_value = moved
        self.assertEqual(self.run_probe(apply_google=True)['overlap'], 1)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.starts_at, self.start)

    def test_binding_changes_after_network_invalidate_result_before_any_flag_or_adoption(self):
        def inspect(appointment):
            self.assertFalse(connection.in_atomic_block)
            CalendarConnection.objects.filter(pk=1).update(generation=uuid.uuid4())
            return {'state': 'missing'}
        self.provider.inspect_event.side_effect = inspect
        report = self.run_probe(apply_google=True)
        self.appointment.refresh_from_db()
        self.assertEqual(report['status'], 'connection_changed')
        self.assertEqual(self.appointment.status, 'confirmed')
        self.assertFalse(AuditEvent.objects.exists())

    def test_local_cancellation_during_network_is_not_overwritten(self):
        def inspect(appointment):
            Appointment.objects.filter(pk=appointment.pk).update(status='cancel_pending', sync_operation='cancel')
            return self.moved()
        self.provider.inspect_event.side_effect = inspect
        report = self.run_probe(apply_google=True)
        self.appointment.refresh_from_db()
        self.assertEqual(report['stale'], 1)
        self.assertEqual(self.appointment.status, 'cancel_pending')
        self.assertEqual(self.appointment.starts_at, self.start)
        self.assertFalse(AuditEvent.objects.exists())

    def test_only_future_confirmed_owned_current_binding_events_are_read(self):
        self.make_appointment(starts_at=self.start+timedelta(hours=1), ends_at=self.start+timedelta(hours=1, minutes=20), status='cancelled')
        self.make_appointment(starts_at=self.start+timedelta(hours=2), ends_at=self.start+timedelta(hours=2, minutes=20), status='pending')
        self.make_appointment(starts_at=self.start-timedelta(days=3), ends_at=self.start-timedelta(days=3)+timedelta(minutes=20))
        old = self.make_appointment(starts_at=self.start+timedelta(hours=3), ends_at=self.start+timedelta(hours=3, minutes=20), connection_generation=uuid.uuid4())
        unowned = self.make_appointment(starts_at=self.start+timedelta(hours=4), ends_at=self.start+timedelta(hours=4, minutes=20))
        Appointment.objects.filter(pk=unowned.pk).update(google_event_id='personal-event')
        report = self.run_probe(apply_google=True)
        self.assertEqual(report['inspected'], 1)
        self.assertEqual(report['skipped_binding'], 1)
        self.assertEqual(report['unknown'], 1)
        self.provider.inspect_event.assert_called_once()
        old.refresh_from_db()
        self.assertEqual(old.status, 'confirmed')

    def test_unknown_payload_and_provider_failures_never_flag_or_leak_details(self):
        for result in ({'state': 'unknown'}, {'state': 'moved', 'starts_at': 'bad', 'ends_at': 'bad'}):
            self.provider.inspect_event.return_value = result
            report = self.run_probe(apply_google=True)
            self.assertEqual(report['unknown'], 1)
            self.appointment.refresh_from_db()
            self.assertEqual(self.appointment.status, 'confirmed')
        self.provider.inspect_event.side_effect = RuntimeError('sensitive-provider-response-and-token')
        output = StringIO()
        call_command('reconcile_calendar', '--probe', '--apply-google', '--json', stdout=output)
        report = json.loads(output.getvalue())
        self.assertEqual(report['provider_failed'], 1)
        self.assertEqual(report['status'], 'incomplete')
        for value in ('sensitive-provider', str(self.appointment.pk), self.patient.first_name, self.binding.account_email):
            self.assertNotIn(value, output.getvalue())
        self.assertFalse(AuditEvent.objects.exists())

    def test_missing_config_disconnected_preview_or_wrong_account_cannot_probe(self):
        with override_settings(GOOGLE_CLIENT_SECRET=''):
            self.assertEqual(self.run_probe()['status'], 'not_configured')
        with override_settings(CLINIC_PREVIEW_EXPORT=True):
            self.assertEqual(self.run_probe()['status'], 'preview_disabled')
        CalendarConnection.objects.filter(pk=1).update(active=False)
        self.assertEqual(self.run_probe()['status'], 'not_connected')
        CalendarConnection.objects.filter(pk=1).update(active=True, account_email='wrong@example.test')
        self.assertEqual(self.run_probe()['status'], 'account_mismatch')
        self.factory.assert_not_called()

    def test_limited_scan_reports_remaining_work(self):
        self.make_appointment(starts_at=self.start+timedelta(hours=1), ends_at=self.start+timedelta(hours=1, minutes=20))
        report = self.run_probe(limit=1)
        self.assertEqual(report['inspected'], 1)
        self.assertEqual(report['remaining'], 1)
        self.assertIn('limit_reached', report['issues'])
        self.assertEqual(report['status'], 'incomplete')

    def test_two_limited_apply_runs_rotate_confirmed_events(self):
        other = self.make_appointment(starts_at=self.start+timedelta(hours=1), ends_at=self.start+timedelta(hours=1, minutes=20))
        self.run_probe(apply_google=True, limit=1)
        self.run_probe(apply_google=True, limit=1)
        inspected = [call.args[0].pk for call in self.provider.inspect_event.call_args_list]
        self.assertEqual(inspected, [self.appointment.pk, other.pk])
        self.assertEqual(Appointment.objects.filter(calendar_checked_at__isnull=False).count(), 2)
        self.assertFalse(AuditEvent.objects.exists())

    def test_unknown_and_failed_attempts_rotate_but_read_only_does_not_write_timestamp(self):
        other = self.make_appointment(starts_at=self.start+timedelta(hours=1), ends_at=self.start+timedelta(hours=1, minutes=20))
        self.provider.inspect_event.side_effect = [RuntimeError('private'), {'state': 'unknown'}]
        self.assertEqual(self.run_probe(apply_google=True, limit=1)['provider_failed'], 1)
        self.assertEqual(self.run_probe(flag_reviewed_mismatches=True, limit=1)['unknown'], 1)
        inspected = [call.args[0].pk for call in self.provider.inspect_event.call_args_list]
        self.assertEqual(inspected, [self.appointment.pk, other.pk])
        Appointment.objects.update(calendar_checked_at=None)
        self.provider.inspect_event.side_effect = None
        self.run_probe(limit=1)
        self.assertFalse(Appointment.objects.exclude(calendar_checked_at=None).exists())

    def test_old_binding_does_not_starve_current_binding_in_limited_apply(self):
        old = self.make_appointment(starts_at=self.start-timedelta(hours=1), ends_at=self.start-timedelta(minutes=40), connection_generation=uuid.uuid4())
        report = self.run_probe(apply_google=True, limit=1)
        self.assertEqual(report['skipped_binding'], 1)
        self.provider.inspect_event.assert_called_once()
        self.assertEqual(self.provider.inspect_event.call_args.args[0].pk, self.appointment.pk)
        old.refresh_from_db()
        self.assertIsNone(old.calendar_checked_at)

    def test_local_write_failure_rolls_back_and_reports_no_database_details(self):
        self.provider.inspect_event.return_value = self.moved()
        with patch('clinic.calendar_reconciliation.AuditEvent.objects.create', side_effect=IntegrityError('private-row-detail')):
            report = self.run_probe(apply_google=True)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.starts_at, self.start)
        self.assertEqual(report['local_failed'], 1)
        self.assertNotIn('private-row-detail', str(report))
        self.assertIn('local_write_failed', report['issues'])
