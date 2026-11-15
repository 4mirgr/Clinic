from datetime import date,datetime,timezone as dt_timezone
from unittest.mock import patch
from django import forms
from django.contrib.auth.models import Group,User
from django.test import TestCase,SimpleTestCase


class JalaliTests(SimpleTestCase):
    def test_jalali_input_round_trip_and_leap_day(self):
        from clinic.jalali import JalaliDateField,format_jalali
        field=JalaliDateField()
        self.assertEqual(field.clean('۱۴۰۵/۰۸/۲۴'),date(2026,11,15))
        self.assertEqual(field.clean('1403/12/30'),date(2025,3,20))
        with self.assertRaises(forms.ValidationError):field.clean('1404/12/30')
        with self.assertRaises(forms.ValidationError):field.clean('2026-11-15')
        self.assertEqual(format_jalali(date(2026,11,15)),'۱۴۰۵/۰۸/۲۴')

    def test_today_is_tehran_not_utc_and_widget_is_a_popup(self):
        from clinic.jalali import JalaliDateInput,today_tehran
        with patch('clinic.jalali.timezone.now',return_value=datetime(2026,11,15,21,tzinfo=dt_timezone.utc)):
            self.assertEqual(today_tehran(),date(2026,11,16))
            html=JalaliDateInput().render('day',today_tehran())
            self.assertIn('۱۴۰۵/۰۸/۲۵',html)
            self.assertIn('data-jalali-picker',html)
            self.assertIn('باز کردن تقویم شمسی',html)


class SecretarySchedulingTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('secretary',password='Strong-test-only-73!')
        self.user.groups.add(Group.objects.get_or_create(name='clinic_secretary')[0])
        self.client.force_login(self.user)

    def test_secretary_can_schedule_but_cannot_read_records_or_connect_google(self):
        for url in ['/dash/calendar/','/dash/calendar/settings/','/dash/calendar/availability/']:
            self.assertEqual(self.client.get(url).status_code,200,url)
        for url in ['/dash/patients/','/dash/advice/','/dash/activity/','/dash/calendar/connect/','/dash/calendar/disconnect/']:
            self.assertEqual(self.client.get(url).status_code,403,url)
            self.assertEqual(self.client.post(url).status_code,403,url)
        self.assertEqual(self.client.get('/dash/calendar/slots/',{'day':'۱۴۰۵/۰۸/۲۴'}).status_code,503)

    def test_specific_date_can_override_weekly_hours_and_holidays(self):
        response=self.client.post('/dash/calendar/availability/',{'day':'۱۴۰۵/۰۸/۲۴','opens_at':'09:00','closes_at':'12:00','opens_second':'16:00','closes_second':'18:00'})
        self.assertEqual(response.status_code,302)
        from clinic.calendar_models import AvailabilityOverride
        override=AvailabilityOverride.objects.get()
        self.assertEqual(override.day,date(2026,11,15))
        self.assertEqual(override.windows,[{'start':'09:00','end':'12:00'},{'start':'16:00','end':'18:00'}])
        response=self.client.post('/dash/calendar/availability/',{'day':'۱۴۰۵/۰۸/۲۴','closed':'on'})
        self.assertEqual(response.status_code,302)
        override.refresh_from_db();self.assertTrue(override.closed);self.assertEqual(override.windows,[])


class SlotTests(TestCase):
    def setUp(self):
        from clinic.tests.test_calendar import TEST_GOOGLE
        from django.test import override_settings
        self.override=override_settings(**TEST_GOOGLE);self.override.enable();self.addCleanup(self.override.disable)
        from clinic.calendar_models import CalendarConnection,ScheduleSettings
        self.actor=User.objects.create_user('doctor')
        self.patient=__import__('django.apps',fromlist=['apps']).apps.get_model('clinic','Patient').objects.create(first_name='آزمایش',last_name='شمسی',phone='09123456789')
        self.connection=CalendarConnection(pk=1,owner=self.actor,active=True);self.connection.set_refresh_token('test-only');self.connection.save()
        self.settings=ScheduleSettings.objects.create(pk=1,enabled=True,weekdays=[0],opens_at=__import__('datetime').time(9),closes_at=__import__('datetime').time(10),slot_minutes=20,horizon_days=30)
        self.now=datetime(2030,1,7,4,30,tzinfo=dt_timezone.utc)
        self.clock=patch('clinic.scheduling.timezone.now',return_value=self.now);self.clock.start();self.addCleanup(self.clock.stop)

    def test_date_override_slots_and_explicit_choice_revalidation(self):
        from clinic.calendar_models import AvailabilityOverride
        from clinic.tests.test_calendar import FakeCalendar
        from clinic.scheduling import available_slots,book_selected_slot,BookingError
        day=date(2030,1,8) # Tuesday, normally closed.
        AvailabilityOverride.objects.create(day=day,windows=[{'start':'16:00','end':'17:00'}])
        provider=FakeCalendar()
        slots=available_slots(day,provider=provider)
        self.assertEqual([x[0].strftime('%H:%M') for x in slots],['16:00','16:20','16:40'])
        selected=slots[1][0]
        appointment=book_selected_slot(self.patient,day,selected,self.actor,provider=provider)
        self.assertEqual(appointment.starts_at,selected)
        self.assertEqual(appointment.status,'confirmed')
        with self.assertRaises(BookingError):book_selected_slot(self.patient,day,selected,self.actor,provider=provider)
        AvailabilityOverride.objects.filter(day=day).update(closed=True,windows=[])
        self.assertEqual(available_slots(day,provider=provider),[])

    def test_same_submission_key_does_not_create_two_appointments(self):
        import uuid
        from clinic.tests.test_calendar import FakeCalendar
        from clinic.scheduling import available_slots,book_selected_slot
        provider=FakeCalendar();day=date(2030,1,7);slot=available_slots(day,provider=provider)[0][0];key=uuid.uuid4()
        one=book_selected_slot(self.patient,day,slot,self.actor,provider=provider,request_key=key)
        two=book_selected_slot(self.patient,day,slot,self.actor,provider=provider,request_key=key)
        self.assertEqual(one.pk,two.pk)
        self.assertEqual(len(provider.events),1)
