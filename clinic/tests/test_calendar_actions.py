from unittest.mock import patch
from django.contrib.auth.models import Group, User
from django.test import TestCase, Client
from django.urls import reverse


class CalendarActionTests(TestCase):
    def setUp(self):
        self.manager=User.objects.create_user('calendar-action-manager')
        self.manager.groups.add(Group.objects.get_or_create(name='clinic_manager')[0])
        self.secretary=User.objects.create_user('calendar-action-secretary')
        self.secretary.groups.add(Group.objects.get_or_create(name='clinic_secretary')[0])
        self.url=reverse('calendar_reconcile')

    def test_manager_post_only_and_csrf_are_required(self):
        self.client.force_login(self.secretary)
        with patch('clinic.calendar_actions.reconcile_calendar') as probe:
            self.assertEqual(self.client.post(self.url).status_code,403);probe.assert_not_called()
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(self.url).status_code,405)
        secure=Client(enforce_csrf_checks=True);secure.force_login(self.manager)
        self.assertEqual(secure.post(self.url).status_code,403)

    def test_unconfigured_action_does_not_claim_connected_or_send(self):
        self.client.force_login(self.manager)
        with patch('clinic.calendar_api.GoogleCalendar.request') as network:
            response=self.client.post(self.url)
        self.assertEqual(response.status_code,302);network.assert_not_called()
        self.assertTrue(any('کامل نشد' in str(m) for m in list(response.wsgi_request._messages)))

    def test_explicit_action_uses_bounded_batch_and_actor(self):
        self.client.force_login(self.manager)
        result={'status':'checked','applied_moved':1,'applied_missing':1,'overlap':0,'remaining':0}
        with patch('clinic.calendar_actions.reconcile_calendar',return_value=result) as probe:
            self.assertEqual(self.client.post(self.url).status_code,302)
        probe.assert_called_once_with(probe=True,apply_google=True,limit=3,actor=self.manager)

    def test_flagged_cancellation_returns_warning_without_google_write(self):
        import uuid
        from datetime import timedelta
        from django.utils import timezone
        from clinic.models import Appointment, Patient
        patient=Patient.objects.create(first_name='بیمار',last_name='آزمایشی',phone='09123456789')
        start=timezone.now()+timedelta(days=1)
        event=Appointment.objects.create(patient=patient,created_by=self.manager,starts_at=start,ends_at=start+timedelta(minutes=20),connection_generation=uuid.uuid4(),status='attention',calendar_review_required=True)
        self.client.force_login(self.manager)
        with patch('clinic.calendar_api.GoogleCalendar.request') as provider:
            response=self.client.post(reverse('calendar_cancel',args=[event.pk]))
        self.assertEqual(response.status_code,302);provider.assert_not_called()
        event.refresh_from_db();self.assertEqual(event.status,'attention')
