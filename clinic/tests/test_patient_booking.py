import json
from datetime import time,timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group,User
from django.test import Client,TestCase,override_settings
from django.utils import timezone

from clinic.tests.test_calendar import TEST_GOOGLE
from clinic.tests.test_rescheduling import EditableCalendar
from clinic.jalali import today_tehran,format_jalali


@override_settings(**TEST_GOOGLE)
class PatientBookingTests(TestCase):
    def setUp(self):
        from clinic.models import Patient,PortalAccount
        from clinic.calendar_models import CalendarConnection,ScheduleSettings
        self.patient=Patient.objects.create(first_name='بیمار',last_name='خودم',phone='09123456789')
        self.other_patient=Patient.objects.create(first_name='بیمار',last_name='دیگری',phone='09123456788')
        self.user=User.objects.create_user('patient-one',password='Strong-test-only-73!')
        self.account=PortalAccount.objects.create(user=self.user,email='patient@example.test',patient=self.patient)
        self.client.force_login(self.user);session=self.client.session;session['portal_auth_version']=self.account.auth_version;session.save()
        self.doctor=User.objects.create_user('doctor')
        connection=CalendarConnection(pk=1,owner=self.doctor,active=True,account_email='dr.gerami.md@gmail.com',google_subject='test-subject');connection.set_refresh_token('test-only');connection.save()
        ScheduleSettings.objects.create(pk=1,enabled=True,weekdays=list(range(7)),opens_at=time(9),closes_at=time(11),slot_minutes=20,horizon_days=30)
        self.day=today_tehran()+timedelta(days=1)
        self.provider=EditableCalendar();self.provider_patch=patch('clinic.scheduling.GoogleCalendar',return_value=self.provider);self.provider_patch.start();self.addCleanup(self.provider_patch.stop)

    def form_data(self,patient=None):
        from clinic.calendar_forms import BookingForm
        from clinic.scheduling import available_slots
        form=BookingForm(actor=self.user,patient_account=self.account)
        return {'patient':str((patient or self.patient).pk),'day':format_jalali(self.day),'slot_start':available_slots(self.day,provider=self.provider)[0][0].isoformat(),'request_token':form.fields['request_token'].initial}

    def test_patient_sees_only_own_appointments_and_cannot_open_staff_or_other_records(self):
        from clinic.scheduling import book_next_available
        one=book_next_available(self.patient,self.day,self.doctor,provider=self.provider)
        other=book_next_available(self.other_patient,self.day,self.doctor,provider=self.provider)
        response=self.client.get('/dash/booking/')
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,'دیگری')
        self.assertNotContains(response,str(other.pk))
        for url in ['/dash/calendar/','/dash/calendar/settings/','/dash/calendar/availability/',f'/dash/calendar/{one.pk}/edit/',f'/dash/calendar/{other.pk}/cancel/','/dash/patients/']:
            self.assertEqual(self.client.get(url).status_code,403,url)
            self.assertEqual(self.client.post(url,{}).status_code,403,url)
        self.assertEqual(self.client.get('/dash/calendar/slots/',{'day':format_jalali(self.day),'appointment':str(other.pk)}).status_code,403)

    def test_patient_selects_free_slot_and_cannot_post_another_patient_id(self):
        from clinic.calendar_models import Appointment
        data=self.form_data(self.other_patient)
        self.assertEqual(self.client.post('/dash/calendar/book/',data).status_code,200)
        self.assertEqual(Appointment.objects.count(),0)
        data=self.form_data()
        self.assertEqual(self.client.post('/dash/calendar/book/',data).headers['Location'],'/dash/booking/')
        self.assertEqual(Appointment.objects.get().patient_id,self.patient.pk)
        self.assertEqual(Appointment.objects.get().status,'confirmed')
        self.assertEqual(self.client.post('/dash/calendar/book/',data).status_code,302)
        self.assertEqual(Appointment.objects.count(),1)

    def test_revoked_session_and_missing_profile_cannot_book(self):
        from clinic.calendar_models import Appointment
        data=self.form_data()
        self.account.auth_version+=1;self.account.save()
        self.assertEqual(self.client.post('/dash/calendar/book/',data).status_code,302)
        self.assertEqual(Appointment.objects.count(),0)
        self.client.force_login(self.user);session=self.client.session;session['portal_auth_version']=self.account.auth_version;session.save()
        self.account.patient=None;self.account.save()
        response=self.client.get('/dash/booking/')
        self.assertContains(response,'پروفایل خود را تکمیل کنید')
        self.assertNotContains(response,str(self.other_patient.pk))

    def test_revocation_during_booking_is_rechecked_before_reservation(self):
        from clinic.calendar_models import Appointment
        from clinic.portal_api import PortalError
        data=self.form_data()
        with patch('clinic.calendar_views.locked_account',side_effect=PortalError('sign_in_required',401)):
            self.assertEqual(self.client.post('/dash/calendar/book/',data).status_code,302)
        self.assertEqual(Appointment.objects.count(),0)

    def test_last_moment_conflict_does_not_claim_slot_is_held(self):
        from types import SimpleNamespace
        data=self.form_data()
        with patch('clinic.calendar_views.book_selected_slot',return_value=SimpleNamespace(status='conflict')):
            response=self.client.post('/dash/calendar/book/',data,follow=True)
        self.assertContains(response,'ساعت دیگری انتخاب کنید')
        self.assertNotContains(response,'زمان در پنل نگه داشته شد')
