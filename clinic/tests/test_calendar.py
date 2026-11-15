from datetime import date,datetime,time,timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet
from django.apps import apps
from django.contrib.auth.models import Group,User
from django.test import TestCase,override_settings
from django.utils import timezone

TZ=ZoneInfo('Asia/Tehran')
TEST_GOOGLE={'GOOGLE_CLIENT_ID':'test-client.apps.googleusercontent.com','GOOGLE_CLIENT_SECRET':'test-client-secret','GOOGLE_TOKEN_ENCRYPTION_KEY':Fernet.generate_key().decode(),'GOOGLE_REDIRECT_URI':'https://drgerami-md.ir/dash/calendar/oauth/callback/'}


class CalendarAccessTests(TestCase):
    def setUp(self):
        self.manager=User.objects.create_user('doctor',password='Strong-test-only-73!')
        self.manager.groups.add(Group.objects.get_or_create(name='clinic_manager')[0])
        self.secretary=User.objects.create_user('secretary',password='Strong-test-only-73!')
        self.secretary.groups.add(Group.objects.get_or_create(name='clinic_secretary')[0])

    def test_calendar_requires_manager_even_for_direct_posts(self):
        self.assertEqual(self.client.get('/dash/calendar/').status_code,302)
        self.client.force_login(self.secretary)
        for url in ['/dash/calendar/','/dash/calendar/settings/','/dash/calendar/connect/','/dash/calendar/disconnect/','/dash/calendar/book/','/dash/calendar/oauth/callback/']:
            self.assertEqual(self.client.get(url).status_code,403,url)
            self.assertEqual(self.client.post(url).status_code,403,url)

    def test_missing_configuration_is_honest_and_booking_fails_closed(self):
        self.client.force_login(self.manager)
        with override_settings(GOOGLE_CLIENT_ID='',GOOGLE_CLIENT_SECRET='',GOOGLE_TOKEN_ENCRYPTION_KEY=''):
            self.assertContains(self.client.get('/dash/calendar/'),'اتصال گوگل تنظیم نشده')
            self.assertEqual(self.client.post('/dash/calendar/connect/').status_code,302)
            self.assertNotIn('google_oauth',self.client.session)
        self.assertEqual(apps.get_model('clinic','Appointment').objects.count(),0)

    @override_settings(**TEST_GOOGLE)
    def test_oauth_state_pkce_callback_owner_expiry_and_token_encryption(self):
        from urllib.parse import urlparse,parse_qs
        from clinic.calendar_models import CalendarConnection
        self.client.force_login(self.manager)
        response=self.client.post('/dash/calendar/connect/')
        self.assertEqual(response.status_code,302)
        query=parse_qs(urlparse(response.headers['Location']).query)
        self.assertEqual(urlparse(response.headers['Location']).hostname,'accounts.google.com')
        self.assertIn('code_challenge',query)
        self.assertEqual(query['code_challenge_method'],['S256'])
        self.assertEqual(query['access_type'],['offline'])
        self.assertNotIn('code_verifier',query)
        self.assertEqual(self.client.get('/dash/calendar/oauth/callback/',{'state':'wrong','code':'x'}).status_code,302)
        self.assertFalse(CalendarConnection.objects.exists())
        # A new valid flow; mock only Google's network token exchange.
        self.client.post('/dash/calendar/connect/')
        state=self.client.session['google_oauth']['state']
        def fetch(flow,**kwargs):
            flow.oauth2session.token={'access_token':'test-access','refresh_token':'test-refresh-must-stay-encrypted','token_type':'Bearer','expires_in':3600,'expires_at':timezone.now().timestamp()+3600,'scope':' '.join(flow.oauth2session.scope)}
            return flow.oauth2session.token
        with patch('clinic.calendar_oauth.Flow.fetch_token',autospec=True,side_effect=fetch):
            self.assertEqual(self.client.get('/dash/calendar/oauth/callback/',{'state':state,'code':'test-code'}).status_code,302)
        connection=CalendarConnection.objects.get()
        self.assertTrue(connection.active)
        self.assertEqual(connection.get_refresh_token(),'test-refresh-must-stay-encrypted')
        self.assertNotIn('test-refresh-must-stay-encrypted',str(list(CalendarConnection.objects.values())))
        self.assertNotIn('google_oauth',self.client.session)
        self.assertEqual(self.client.get('/dash/calendar/oauth/callback/',{'state':state,'code':'again'}).status_code,302)
        self.client.post('/dash/calendar/disconnect/')
        connection.refresh_from_db();self.assertFalse(connection.active);self.assertEqual(connection.refresh_token_encrypted,'')

    @override_settings(**TEST_GOOGLE)
    def test_stale_or_different_manager_oauth_state_is_rejected_without_exchange(self):
        self.client.force_login(self.manager)
        for change in [{'created_at':0},{'user_id':999999}]:
            self.client.post('/dash/calendar/connect/')
            session=self.client.session;flow=session['google_oauth'];flow.update(change);session['google_oauth']=flow;session.save()
            with patch('clinic.calendar_oauth.Flow.fetch_token') as fetch:
                self.client.get('/dash/calendar/oauth/callback/',{'state':flow['state'],'code':'must-not-be-exchanged'})
                fetch.assert_not_called()
        self.assertEqual(apps.get_model('clinic','CalendarConnection').objects.count(),0)


@override_settings(**TEST_GOOGLE)
class SchedulingTests(TestCase):
    def setUp(self):
        from clinic.calendar_models import CalendarConnection,ScheduleSettings
        self.manager=User.objects.create_user('doctor')
        self.patient=apps.get_model('clinic','Patient').objects.create(first_name='بیمار',last_name='آزمایشی',phone='09123456789')
        self.connection=CalendarConnection(pk=1,owner=self.manager,active=True)
        self.connection.set_refresh_token('test-refresh');self.connection.save()
        self.day=date(2030,1,7)
        self.schedule=ScheduleSettings.objects.create(pk=1,enabled=True,weekdays=[0],opens_at=time(9),closes_at=time(10),slot_minutes=20,horizon_days=30)
        self.now=datetime(2030,1,7,8,tzinfo=TZ)
        self.now_patch=patch('clinic.scheduling.timezone.now',return_value=self.now);self.now_patch.start();self.addCleanup(self.now_patch.stop)

    def book(self,provider):
        from clinic.scheduling import book_next_available
        return book_next_available(self.patient,self.day,self.manager,provider=provider)

    def test_chooses_next_slot_excluding_google_busy_and_local_reservations(self):
        provider=FakeCalendar(busy=[(datetime(2030,1,7,9,tzinfo=TZ),datetime(2030,1,7,9,20,tzinfo=TZ))])
        one=self.book(provider);two=self.book(provider)
        self.assertEqual(one.starts_at.astimezone(TZ).strftime('%H:%M'),'09:20')
        self.assertEqual(two.starts_at.astimezone(TZ).strftime('%H:%M'),'09:40')
        self.assertEqual(one.status,'confirmed');self.assertEqual(two.status,'confirmed')
        from clinic.scheduling import BookingError
        with self.assertRaises(BookingError):self.book(provider)

    def test_closed_days_disabled_schedule_and_past_dates_cannot_book(self):
        from clinic.scheduling import BookingError,book_next_available
        for day in [date(2030,1,6),date(2030,1,8),date(2030,3,1)]:
            with self.assertRaises(BookingError):book_next_available(self.patient,day,self.manager,provider=FakeCalendar())
        self.schedule.enabled=False;self.schedule.save()
        with self.assertRaises(BookingError):self.book(FakeCalendar())
        self.assertEqual(apps.get_model('clinic','Appointment').objects.count(),0)

    def test_uncertain_insert_retries_by_deterministic_id_without_duplicate(self):
        from clinic.scheduling import sync_appointment
        provider=FakeCalendar(fail_after_insert=True)
        appointment=self.book(provider)
        self.assertEqual(appointment.status,'pending')
        self.assertEqual(len(provider.events),1)
        sync_appointment(appointment.pk,self.manager,provider=provider,force=True)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status,'confirmed')
        self.assertEqual(len(provider.events),1)
        self.assertEqual(appointment.google_event_id,appointment.pk.hex)

    def test_remote_conflict_between_reservation_and_retry_is_not_confirmed(self):
        from clinic.calendar_api import CalendarUnavailable
        from clinic.scheduling import sync_appointment
        provider=FakeCalendar(fail_before_insert=True)
        appointment=self.book(provider)
        self.assertEqual(appointment.status,'pending')
        provider.fail_before_insert=False
        provider.busy=[(appointment.starts_at,appointment.ends_at)]
        sync_appointment(appointment.pk,self.manager,provider=provider,force=True)
        appointment.refresh_from_db();self.assertEqual(appointment.status,'conflict')
        self.assertEqual(len(provider.events),0)
        with self.assertRaises(CalendarUnavailable):self.book(FakeCalendar(fail_freebusy=True))

    def test_cancellation_retries_and_old_connection_never_writes_new_account(self):
        from clinic.scheduling import request_cancellation,sync_appointment
        provider=FakeCalendar();appointment=self.book(provider)
        provider.fail_delete=True
        request_cancellation(appointment.pk,self.manager,provider=provider)
        appointment.refresh_from_db();self.assertEqual(appointment.status,'cancel_pending')
        provider.fail_delete=False
        sync_appointment(appointment.pk,self.manager,provider=provider,force=True)
        appointment.refresh_from_db();self.assertEqual(appointment.status,'cancelled')
        self.assertEqual(provider.events,{})
        second=self.book(FakeCalendar(fail_before_insert=True))
        import uuid
        self.connection.generation=uuid.uuid4();self.connection.save()
        fresh=FakeCalendar()
        sync_appointment(second.pk,self.manager,provider=fresh,force=True)
        second.refresh_from_db();self.assertEqual(second.status,'attention');self.assertEqual(fresh.events,{})

    def test_office_hours_form_requires_explicit_valid_configuration(self):
        from clinic.calendar_forms import ScheduleForm
        self.assertFalse(ScheduleForm({'enabled':'on','weekdays':[],'opens_at':'','closes_at':'','slot_minutes':20,'horizon_days':30}).is_valid())
        self.assertFalse(ScheduleForm({'enabled':'on','weekdays':['0'],'opens_at':'17:00','closes_at':'09:00','slot_minutes':20,'horizon_days':30}).is_valid())
        self.assertTrue(ScheduleForm({'enabled':'on','weekdays':['0'],'opens_at':'09:00','closes_at':'12:00','slot_minutes':20,'horizon_days':30}).is_valid())


class FakeCalendar:
    """Only the external provider is doubled; scheduling, encryption and DB are real."""
    def __init__(self,busy=None,fail_after_insert=False,fail_before_insert=False,fail_freebusy=False):
        self.busy=busy or [];self.events={};self.fail_after_insert=fail_after_insert;self.fail_before_insert=fail_before_insert;self.fail_freebusy=fail_freebusy;self.fail_delete=False;self.deletions=[]
    def free_busy(self,start,end):
        from clinic.calendar_api import CalendarUnavailable
        if self.fail_freebusy:raise CalendarUnavailable()
        return self.busy
    def find_event(self,appointment):return self.events.get(appointment.pk.hex)
    def insert_event(self,appointment):
        from clinic.calendar_api import CalendarUnavailable
        if self.fail_before_insert:raise CalendarUnavailable()
        self.events[appointment.pk.hex]={'id':appointment.pk.hex}
        if self.fail_after_insert:
            self.fail_after_insert=False;raise CalendarUnavailable()
        return self.events[appointment.pk.hex]
    def delete_event(self,appointment):
        self.deletions.append(appointment.pk.hex)
        from clinic.calendar_api import CalendarUnavailable
        if self.fail_delete:raise CalendarUnavailable()
        self.events.pop(appointment.pk.hex,None)

@override_settings(**TEST_GOOGLE)
class GoogleTransportTests(TestCase):
    def setUp(self):
        from clinic.calendar_models import Appointment,CalendarConnection
        self.user=User.objects.create_user('doctor')
        patient=apps.get_model('clinic','Patient').objects.create(first_name='PRIVATE-PATIENT',last_name='DO-NOT-SEND',phone='09123456789',history='PRIVATE-HISTORY')
        self.connection=CalendarConnection(pk=1,owner=self.user,active=True)
        self.connection.set_refresh_token('test-only-refresh')
        self.appointment=Appointment(patient=patient,created_by=self.user,starts_at=datetime(2030,1,7,9,tzinfo=TZ),ends_at=datetime(2030,1,7,9,20,tzinfo=TZ),connection_generation=self.connection.generation)

    def test_google_event_payload_is_private_and_idempotent_without_patient_data(self):
        from clinic.calendar_api import GoogleCalendar
        transport=FakeTransport([(200,{'id':self.appointment.pk.hex})])
        result=GoogleCalendar(self.connection,session=transport).insert_event(self.appointment)
        self.assertEqual(result['id'],self.appointment.pk.hex)
        method,url,kwargs=transport.requests[0]
        self.assertEqual(method,'POST')
        self.assertEqual(kwargs['json']['id'],self.appointment.pk.hex)
        self.assertEqual(kwargs['json']['visibility'],'private')
        self.assertEqual(kwargs['params']['sendUpdates'],'none')
        self.assertEqual(kwargs['json']['start']['timeZone'],'Asia/Tehran')
        self.assertNotIn('attendees',kwargs['json'])
        self.assertNotIn('PRIVATE',str(kwargs))
        self.assertNotIn('09123456789',str(kwargs))

    def test_freebusy_errors_and_malformed_response_do_not_mean_free_time(self):
        from clinic.calendar_api import CalendarUnavailable,GoogleCalendar
        for data in [{},{'calendars':{'primary':{'errors':[{'reason':'notFound'}]}}},{'calendars':{'primary':{'busy':[{'start':'invalid','end':'invalid'}]}}}]:
            with self.assertRaises(CalendarUnavailable):GoogleCalendar(self.connection,session=FakeTransport([(200,data)])).free_busy(self.appointment.starts_at,self.appointment.ends_at)
        data={'calendars':{'primary':{'busy':[{'start':'2030-01-07T05:30:00Z','end':'2030-01-07T05:50:00Z'}]}}}
        busy=GoogleCalendar(self.connection,session=FakeTransport([(200,data)])).free_busy(self.appointment.starts_at,self.appointment.ends_at)
        self.assertEqual(busy[0][0].astimezone(TZ).hour,9)

    def test_event_id_collision_is_only_reused_for_matching_appointment(self):
        from clinic.calendar_api import GoogleCalendar,CalendarUnavailable
        data={'id':self.appointment.pk.hex,'extendedProperties':{'private':{'appointment_id':str(self.appointment.pk)}},'start':{'dateTime':self.appointment.starts_at.isoformat()},'end':{'dateTime':self.appointment.ends_at.isoformat()}}
        transport=FakeTransport([(409,{}),(200,data)])
        self.assertEqual(GoogleCalendar(self.connection,session=transport).insert_event(self.appointment)['id'],self.appointment.pk.hex)
        with self.assertRaises(CalendarUnavailable):GoogleCalendar(self.connection,session=FakeTransport([(200,{'id':self.appointment.pk.hex,'extendedProperties':{'private':{'appointment_id':'other'}}})])).find_event(self.appointment)


class FakeTransport:
    def __init__(self,responses):self.responses=list(responses);self.requests=[]
    def request(self,method,url,**kwargs):
        self.requests.append((method,url,kwargs))
        status,data=self.responses.pop(0)
        return FakeResponse(status,data)


class FakeResponse:
    def __init__(self,status,data):self.status_code=status;self.data=data
    def json(self):return self.data

@override_settings(**TEST_GOOGLE)
class ReviewRegressionTests(TestCase):
    def setUp(self):
        from clinic.calendar_models import CalendarConnection
        self.user=User.objects.create_user('review-doctor',password='Strong-test-only-73!')
        self.user.groups.add(Group.objects.get_or_create(name='clinic_manager')[0])
        self.patient=apps.get_model('clinic','Patient').objects.create(first_name='آزمایش',last_name='نوبت',phone='09123456789')
        self.connection=CalendarConnection(pk=1,owner=self.user,active=True)
        self.connection.set_refresh_token('test-token');self.connection.save()
        self.client.force_login(self.user)

    def test_conflict_cancellation_does_not_re_reserve_and_deletes_only_own_event(self):
        from clinic.calendar_models import Appointment
        from clinic.scheduling import request_cancellation
        start=timezone.now()+timedelta(days=2)
        first=Appointment.objects.create(patient=self.patient,created_by=self.user,starts_at=start,ends_at=start+timedelta(minutes=20),connection_generation=self.connection.generation,status='conflict')
        replacement=Appointment.objects.create(patient=self.patient,created_by=self.user,starts_at=start,ends_at=start+timedelta(minutes=20),connection_generation=self.connection.generation,status='confirmed')
        provider=FakeCalendar()
        result=request_cancellation(first.pk,self.user,provider=provider)
        self.assertEqual(result.status,'cancelled')
        replacement.refresh_from_db();self.assertEqual(replacement.status,'confirmed')
        self.assertEqual(provider.events,{})
        self.assertEqual(provider.deletions,[first.pk.hex])

    def test_nearest_appointment_is_visible_and_all_pages_are_accessible(self):
        from clinic.calendar_models import Appointment
        start=timezone.now()+timedelta(days=1)
        items=[]
        for i in range(61):
            items.append(Appointment.objects.create(patient=self.patient,created_by=self.user,starts_at=start+timedelta(hours=i),ends_at=start+timedelta(hours=i,minutes=20),connection_generation=self.connection.generation,status='confirmed'))
        response=self.client.get('/dash/calendar/')
        self.assertTrue(str(items[0].pk).encode() in response.content, 'Nearest appointment must appear on the first page')
        self.assertFalse(str(items[-1].pk).encode() in response.content)
        page2=self.client.get('/dash/calendar/',{'page':2})
        self.assertEqual(page2.status_code,200)
        last=self.client.get('/dash/calendar/',{'page':3})
        self.assertTrue(str(items[-1].pk).encode() in last.content, 'Last appointment must remain accessible through pagination')

    def test_google_mutations_still_require_csrf_and_missing_scopes_are_not_connected(self):
        from django.test import Client
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post('/dash/calendar/connect/').status_code,403)
        self.assertEqual(client.post('/dash/calendar/disconnect/').status_code,403)
        self.client.post('/dash/calendar/disconnect/')
        self.client.post('/dash/calendar/connect/')
        state=self.client.session['google_oauth']['state']
        def fetch(flow,**kwargs):
            flow.oauth2session.token={'access_token':'test-only','refresh_token':'test-only','token_type':'Bearer','expires_at':timezone.now().timestamp()+3600,'scope':'https://www.googleapis.com/auth/calendar.freebusy'}
        with patch('clinic.calendar_oauth.Flow.fetch_token',autospec=True,side_effect=fetch):
            self.client.get('/dash/calendar/oauth/callback/',{'state':state,'code':'test-only'})
        self.connection.refresh_from_db();self.assertFalse(self.connection.active)

    def test_unsent_past_appointment_never_creates_a_retroactive_google_event(self):
        from clinic.calendar_models import Appointment
        from clinic.scheduling import sync_appointment
        start=timezone.now()-timedelta(hours=1)
        appointment=Appointment.objects.create(patient=self.patient,created_by=self.user,starts_at=start,ends_at=start+timedelta(minutes=20),connection_generation=self.connection.generation)
        provider=FakeCalendar()
        result=sync_appointment(appointment.pk,self.user,provider=provider,force=True)
        self.assertEqual(result.status,'attention')
        self.assertEqual(provider.events,{})
