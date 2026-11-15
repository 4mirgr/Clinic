from datetime import date,datetime,time,timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase,override_settings
from django.utils import timezone

from clinic.tests.test_calendar import TEST_GOOGLE,FakeCalendar,FakeTransport

TZ=ZoneInfo('Asia/Tehran')


class EditableCalendar(FakeCalendar):
    def __init__(self,**kwargs):
        super().__init__(**kwargs);self.updates=0;self.fail_update_once=False
    def free_busy(self,start,end):
        from clinic.calendar_api import timestamp
        return self.busy+[(timestamp(event['start']['dateTime']),timestamp(event['end']['dateTime'])) for event in self.events.values()]
    def free_busy_except(self,start,end,appointment):
        from clinic.calendar_api import timestamp
        return self.busy+[(timestamp(event['start']['dateTime']),timestamp(event['end']['dateTime'])) for key,event in self.events.items() if key!=appointment.pk.hex]
    def find_event(self,appointment,match_times=True):return self.events.get(appointment.pk.hex)
    def insert_event(self,appointment):
        self.events[appointment.pk.hex]={'id':appointment.pk.hex,'start':{'dateTime':appointment.starts_at.isoformat()},'end':{'dateTime':appointment.ends_at.isoformat()},'extendedProperties':{'private':{'appointment_id':str(appointment.pk)}}};return self.events[appointment.pk.hex]
    def update_event(self,appointment):
        from clinic.calendar_api import CalendarUnavailable
        self.updates+=1;self.events[appointment.pk.hex]={'id':appointment.pk.hex,'start':{'dateTime':appointment.starts_at.isoformat()},'end':{'dateTime':appointment.ends_at.isoformat()},'extendedProperties':{'private':{'appointment_id':str(appointment.pk)}}}
        if self.fail_update_once:self.fail_update_once=False;raise CalendarUnavailable()
        return self.events[appointment.pk.hex]


@override_settings(**TEST_GOOGLE)
class ReschedulingTests(TestCase):
    def setUp(self):
        from clinic.models import Patient
        from clinic.calendar_models import CalendarConnection,ScheduleSettings
        self.actor=User.objects.create_user('doctor')
        self.patient=Patient.objects.create(first_name='تست',last_name='ویرایش',phone='09123456789')
        self.connection=CalendarConnection(pk=1,owner=self.actor,active=True,account_email='dr.gerami.md@gmail.com',google_subject='test-subject')
        self.connection.set_refresh_token('fake-only');self.connection.save()
        ScheduleSettings.objects.create(pk=1,enabled=True,weekdays=[0],opens_at=time(9),closes_at=time(11),slot_minutes=20,horizon_days=30)
        self.clock=patch('clinic.scheduling.timezone.now',return_value=datetime(2030,1,7,8,tzinfo=TZ));self.clock.start();self.addCleanup(self.clock.stop)
        self.provider=EditableCalendar();self.day=date(2030,1,7)
        from clinic.scheduling import book_next_available
        self.appointment=book_next_available(self.patient,self.day,self.actor,provider=self.provider)

    def test_edit_updates_same_event_and_clears_previous_hold_only_after_ack(self):
        from clinic.scheduling import reschedule_appointment
        target=datetime(2030,1,7,9,40,tzinfo=TZ)
        result=reschedule_appointment(self.appointment.pk,self.day,target,self.actor,provider=self.provider)
        self.assertEqual(result.pk,self.appointment.pk);self.assertEqual(result.status,'confirmed')
        self.assertEqual(result.starts_at,target);self.assertIsNone(result.previous_starts_at)
        self.assertEqual(list(self.provider.events),[self.appointment.pk.hex]);self.assertEqual(self.provider.updates,1)

    def test_uncertain_update_holds_both_slots_and_retry_does_not_patch_twice(self):
        from clinic.scheduling import reschedule_appointment,available_slots,sync_appointment
        old=self.appointment.starts_at;target=old+timedelta(minutes=40);self.provider.fail_update_once=True
        result=reschedule_appointment(self.appointment.pk,self.day,target,self.actor,provider=self.provider)
        self.assertEqual(result.status,'update_pending');self.assertEqual(result.previous_starts_at,old)
        slots=[a for a,b in available_slots(self.day,provider=self.provider)]
        self.assertNotIn(old,slots);self.assertNotIn(target,slots)
        sync_appointment(result.pk,self.actor,provider=self.provider,force=True)
        result.refresh_from_db();self.assertEqual(result.status,'confirmed');self.assertIsNone(result.previous_starts_at)
        self.assertEqual(self.provider.updates,1)
        self.assertIn(old,[a for a,b in available_slots(self.day,provider=self.provider)])

    def test_external_conflict_prevents_edit_and_cancelled_update_releases_both_holds(self):
        from clinic.scheduling import reschedule_appointment,BookingError,request_cancellation,available_slots
        old=self.appointment.starts_at;target=old+timedelta(minutes=40)
        self.provider.busy=[(target,target+timedelta(minutes=20))]
        with self.assertRaises(BookingError):reschedule_appointment(self.appointment.pk,self.day,target,self.actor,provider=self.provider)
        self.appointment.refresh_from_db();self.assertEqual(self.appointment.starts_at,old)
        self.provider.busy=[];self.provider.fail_update_once=True
        result=reschedule_appointment(self.appointment.pk,self.day,target,self.actor,provider=self.provider)
        result=request_cancellation(result.pk,self.actor,provider=self.provider)
        self.assertEqual(result.status,'cancelled');self.assertIsNone(result.previous_starts_at)
        self.assertIn(old,[a for a,b in available_slots(self.day,provider=self.provider)])

    def test_wrong_google_account_is_not_used(self):
        from clinic.scheduling import available_slots,BookingError
        self.connection.account_email='other@example.com';self.connection.save()
        with self.assertRaises(BookingError):available_slots(self.day,provider=self.provider)

    def test_google_update_is_patch_on_existing_id_and_exclusion_keeps_other_busy_events(self):
        from clinic.calendar_api import GoogleCalendar
        owned={'id':self.appointment.pk.hex,'extendedProperties':{'private':{'appointment_id':str(self.appointment.pk)}},'start':{'dateTime':self.appointment.starts_at.isoformat()},'end':{'dateTime':self.appointment.ends_at.isoformat()}}
        target=self.appointment.starts_at+timedelta(minutes=40);self.appointment.starts_at=target;self.appointment.ends_at=target+timedelta(minutes=20)
        transport=FakeTransport([(200,owned),(200,{'id':self.appointment.pk.hex})])
        GoogleCalendar(self.connection,session=transport).update_event(self.appointment)
        self.assertEqual([r[0] for r in transport.requests],['GET','PATCH'])
        self.assertTrue(transport.requests[-1][1].endswith('/'+self.appointment.pk.hex))
        self.assertEqual(transport.requests[-1][2]['json']['start']['dateTime'],target.isoformat())
        other={'id':'other-event','start':{'dateTime':'2030-01-07T09:10:00+03:30'},'end':{'dateTime':'2030-01-07T09:30:00+03:30'}}
        transport=FakeTransport([(200,{'items':[owned,other]})])
        busy=GoogleCalendar(self.connection,session=transport).free_busy_except(target,target+timedelta(hours=1),self.appointment)
        self.assertEqual(busy,[(datetime(2030,1,7,9,10,tzinfo=TZ),datetime(2030,1,7,9,30,tzinfo=TZ))])

@override_settings(**TEST_GOOGLE)
class GoogleIdentityTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import Group
        self.user=User.objects.create_user('owner')
        self.user.groups.add(Group.objects.get_or_create(name='clinic_manager')[0]);self.client.force_login(self.user)

    def finish(self,email='dr.gerami.md@gmail.com',verified=True,nonce_valid=True):
        self.client.post('/dash/calendar/connect/')
        saved=self.client.session['google_oauth']
        def exchange(flow,**kwargs):
            flow.oauth2session.token={'access_token':'fake-access','refresh_token':'fake-refresh','id_token':'fake-id-token','token_type':'Bearer','expires_at':timezone.now().timestamp()+3600,'scope':' '.join(flow.oauth2session.scope)}
        claims={'email':email,'email_verified':verified,'nonce':saved['nonce'] if nonce_valid else 'wrong-nonce','sub':'same-google-subject'}
        with patch('clinic.calendar_oauth.Flow.fetch_token',autospec=True,side_effect=exchange),patch('clinic.calendar_oauth.id_token.verify_oauth2_token',return_value=claims) as verify:
            result=self.client.get('/dash/calendar/oauth/callback/',{'state':saved['state'],'code':'fake-code'})
            self.assertEqual(verify.call_args.kwargs['audience'],settings.GOOGLE_CLIENT_ID)
        return result

    def test_wrong_email_unverified_email_and_nonce_never_connect(self):
        from clinic.calendar_models import CalendarConnection
        for options in [{'email':'other@gmail.com'},{'verified':False},{'nonce_valid':False}]:
            self.assertEqual(self.finish(**options).status_code,302)
            self.assertFalse(CalendarConnection.objects.filter(active=True).exists())

    def test_reconnecting_same_verified_google_identity_preserves_event_generation(self):
        from clinic.calendar_models import CalendarConnection
        self.finish();connection=CalendarConnection.objects.get();generation=connection.generation
        self.assertEqual(connection.account_email,'dr.gerami.md@gmail.com')
        self.client.post('/dash/calendar/disconnect/')
        self.finish();connection.refresh_from_db()
        self.assertEqual(connection.generation,generation);self.assertTrue(connection.active)
