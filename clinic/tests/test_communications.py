import io
import json
import uuid
from datetime import timedelta
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import requests
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from clinic.communication_models import ContactPreference, PatientNotification, TelegramLinkChallenge
from clinic.communications import DeliveryFailure, dispatch, eligible, message_text, plan_reminders, readiness
from clinic.models import AdvicePacket, Appointment, Patient, PortalAccount, Visit


@override_settings(COMMUNICATIONS_ENABLED=True, COMMUNICATION_PORTAL_URL='https://drgerami-md.ir/dash/portal/',
                   EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='smtp.example.test', DEFAULT_FROM_EMAIL='clinic@example.test')
class CommunicationTests(TestCase):
    def setUp(self):
        self.doctor = User.objects.create_user('communication-doctor', password='Synthetic-only-73!')
        self.doctor.groups.add(Group.objects.get_or_create(name='clinic_manager')[0])
        self.member = User.objects.create_user('communication-patient', password='Synthetic-only-73!')
        self.patient = Patient.objects.create(first_name='بیمار محرمانه', last_name='ساختگی', phone='09123456789', history='تشخیص خصوصی و نام داروی خصوصی')
        self.account = PortalAccount.objects.create(user=self.member, patient=self.patient, email='patient@example.test')
        self.pref = ContactPreference.objects.create(account=self.account, email_opt_in=True, verified_email=self.account.email)
        self.appointment = Appointment.objects.create(patient=self.patient, created_by=self.doctor, starts_at=timezone.now()+timedelta(hours=2), ends_at=timezone.now()+timedelta(hours=3), status='confirmed', connection_generation=uuid.uuid4())

    def member_login(self, client=None):
        client = client or self.client
        client.force_login(self.member)
        session = client.session; session['portal_auth_version'] = self.account.auth_version; session.save()

    def planned(self):
        plan_reminders()
        return PatientNotification.objects.get()

    def test_explicit_consent_and_verified_destination_both_required(self):
        self.pref.email_opt_in = False; self.pref.save()
        self.assertEqual(plan_reminders(), 0)
        self.pref.email_opt_in = True; self.pref.verified_email = ''; self.pref.save()
        self.assertEqual(plan_reminders(), 0)
        self.pref.verified_email = self.account.email; self.pref.save()
        self.assertEqual(plan_reminders(), 1)
        self.assertEqual(plan_reminders(), 0)

    def test_planner_includes_followup_and_recorded_packet_not_draft(self):
        Visit.objects.create(patient=self.patient, author=self.doctor, note='متن خصوصی', follow_up_on=timezone.localdate()+timedelta(days=1))
        AdvicePacket.objects.create(patient=self.patient, patient_name=self.patient.full_name, created_by=self.doctor, request_key=uuid.uuid4(), selection_fingerprint='x'*64)
        self.assertEqual(plan_reminders(), 3)
        self.assertEqual(set(PatientNotification.objects.values_list('kind', flat=True)), {'appointment', 'followup', 'advice'})

    def test_changed_or_cancelled_appointment_invalidates_old_queued_row(self):
        old = self.planned()
        self.appointment.starts_at += timedelta(hours=1); self.appointment.ends_at += timedelta(hours=1); self.appointment.save()
        self.assertEqual(plan_reminders(), 1)
        old.refresh_from_db(); self.assertEqual(old.status, 'cancelled')
        self.appointment.status='cancelled'; self.appointment.save()
        plan_reminders()
        self.assertFalse(PatientNotification.objects.exclude(status='cancelled').exists())

    def test_completed_followup_and_revoked_account_are_never_sent(self):
        visit=Visit.objects.create(patient=self.patient, author=self.doctor, note='خصوصی', follow_up_on=timezone.localdate())
        plan_reminders()
        visit.follow_up_done=True;visit.save()
        row=PatientNotification.objects.get(kind='followup')
        self.assertEqual(eligible(row)[1], 'event_changed')
        self.account.auth_version += 1;self.account.save()
        with patch('clinic.communications.deliver') as send:
            result=dispatch(dry_run=False)
        send.assert_not_called();self.assertEqual(result['cancelled'],2)

    def test_disabled_and_dry_run_never_send_or_mutate(self):
        row=self.planned()
        with patch('clinic.communications.deliver') as send:
            self.assertEqual(dispatch()['ready'],1)
        send.assert_not_called();row.refresh_from_db();self.assertEqual(row.status,'queued');self.assertEqual(row.attempts,0)
        row.status='sending';row.claimed_at=timezone.now()-timedelta(hours=1);row.save()
        dispatch(dry_run=True);row.refresh_from_db();self.assertEqual(row.status,'sending')
        row.status='queued';row.save()
        with override_settings(COMMUNICATIONS_ENABLED=False),patch('clinic.communications.deliver') as send:
            self.assertEqual(dispatch(dry_run=False)['disabled'],1)
        send.assert_not_called();row.refresh_from_db();self.assertEqual(row.status,'queued')

    def test_provider_acceptance_has_no_medical_text_and_does_not_repeat(self):
        row=self.planned()
        with patch('clinic.communications.EmailMessage.send',return_value=1) as send:
            self.assertEqual(dispatch(dry_run=False)['sent'],1)
            self.assertEqual(dispatch(dry_run=False)['sent'],0)
        self.assertEqual(send.call_count,1)
        row.refresh_from_db();self.assertEqual(row.status,'sent')
        body=message_text(row)
        self.assertNotIn(self.patient.first_name,body)
        self.assertNotIn(self.patient.history,body)
        self.assertNotIn(self.patient.phone,body)
        self.assertIn('/dash/portal/',body)

    def test_uncertain_send_is_not_automatically_or_manually_retried(self):
        row=self.planned()
        with patch('clinic.communications.deliver',side_effect=DeliveryFailure('read_timeout',ambiguous=True)) as send:
            self.assertEqual(dispatch(dry_run=False)['unknown'],1)
            dispatch(dry_run=False,now=timezone.now()+timedelta(hours=1))
        self.assertEqual(send.call_count,1)
        self.account.email='other@example.test';self.account.save()
        self.pref.verified_email=self.account.email;self.pref.save()
        self.assertEqual(plan_reminders(),0)
        self.client.force_login(self.doctor)
        self.client.post('/dash/communications/',{'action':'retry','notification':row.pk})
        row.refresh_from_db();self.assertEqual(row.status,'unknown')

    def test_safe_pre_send_failure_has_bounded_delayed_retries(self):
        row=self.planned();now=timezone.now()
        with patch('clinic.communications.deliver',side_effect=DeliveryFailure('connection_timeout')) as send:
            dispatch(dry_run=False,now=now)
            dispatch(dry_run=False,now=now+timedelta(minutes=1))
            self.assertEqual(send.call_count,1)
            dispatch(dry_run=False,now=now+timedelta(minutes=16))
            dispatch(dry_run=False,now=now+timedelta(minutes=32))
            dispatch(dry_run=False,now=now+timedelta(minutes=48))
        self.assertEqual(send.call_count,3)
        row.refresh_from_db();self.assertEqual(row.attempts,3)

    def test_new_verified_contact_replaces_pending_but_not_sent_notice(self):
        old=self.planned()
        self.account.email='new@example.test';self.account.save()
        self.pref.verified_email=self.account.email;self.pref.save()
        self.assertEqual(plan_reminders(),1)
        old.refresh_from_db();self.assertEqual(old.status,'cancelled')

    def test_opt_in_again_resumes_only_an_unsent_reminder(self):
        row=self.planned();self.member_login()
        self.client.post('/dash/api/communications/preferences',{'email_opt_in':False},content_type='application/json')
        row.refresh_from_db();self.assertEqual(row.status,'cancelled')
        self.client.post('/dash/api/communications/preferences',{'email_opt_in':True},content_type='application/json')
        self.assertEqual(plan_reminders(),1)
        row.refresh_from_db();self.assertEqual(row.status,'queued')

    @override_settings(TELEGRAM_BOT_TOKEN='test-only-token',EMAIL_HOST='')
    def test_disabled_channel_cannot_starve_a_connected_channel(self):
        self.pref.telegram_opt_in=True;self.pref.verified_telegram='1234567';self.pref.save()
        self.assertEqual(plan_reminders(),2)
        with patch('clinic.communications.deliver',return_value='accepted') as send:
            result=dispatch(dry_run=False,limit=1)
        self.assertEqual(result['disabled'],1)
        self.assertEqual(result['sent'],1)
        self.assertEqual(send.call_args.args[0].channel,'telegram')

    def test_patient_preferences_are_scoped_csrf_protected_and_immediately_opt_out(self):
        row=self.planned();self.member_login()
        url='/dash/api/communications/preferences'
        response=self.client.post(url,{'email_opt_in':False},content_type='application/json')
        self.assertEqual(response.status_code,200)
        row.refresh_from_db();self.assertEqual(row.status,'cancelled')
        self.assertEqual(self.client.post(url,{'email_opt_in':'yes'},content_type='application/json').status_code,400)
        self.assertEqual(self.client.post(url,{'verified_telegram':'123456'},content_type='application/json').status_code,400)
        csrf_client=Client(enforce_csrf_checks=True);self.member_login(csrf_client)
        self.assertEqual(csrf_client.post(url,{'email_opt_in':True},content_type='application/json').status_code,403)
        self.account.auth_version+=1;self.account.save()
        self.assertEqual(self.client.get(url).status_code,401)

    def test_secretary_with_linked_account_cannot_receive_or_administer_messages(self):
        self.member.groups.add(Group.objects.get_or_create(name='clinic_secretary')[0])
        self.member_login()
        self.assertEqual(plan_reminders(),0)
        self.assertEqual(self.client.get('/dash/api/communications/preferences').status_code,403)
        self.assertEqual(self.client.get('/dash/communications/').status_code,403)
        self.assertEqual(self.client.post('/dash/communications/',{'action':'plan'}).status_code,403)

    def test_contact_verification_requires_matching_patient_and_explicit_attestation(self):
        self.client.force_login(self.doctor)
        base={'action':'verify','account':str(self.account.pk),'channel':'email','destination':'foreign@example.test','ownership_confirmed':'on'}
        self.assertEqual(self.client.post('/dash/communications/',base).status_code,200)
        self.pref.refresh_from_db();self.assertEqual(self.pref.verified_email,self.account.email)
        self.client.post('/dash/communications/',{**base,'channel':'telegram','destination':'-12345'})
        self.pref.refresh_from_db();self.assertFalse(self.pref.verified_telegram)
        self.assertEqual(self.client.post('/dash/communications/',{**base,'channel':'telegram','destination':'1234567'}).status_code,302)
        self.pref.refresh_from_db();self.assertEqual(self.pref.verified_telegram,'1234567')

    def test_health_and_planning_commands_default_to_no_side_effects_or_network(self):
        output=io.StringIO()
        with patch('clinic.communications.requests.post') as network:
            call_command('plan_patient_reminders',stdout=output)
            self.assertFalse(PatientNotification.objects.exists())
            call_command('send_patient_notifications','--check',stdout=output)
        network.assert_not_called();self.assertIn('dry_run',output.getvalue())

    @override_settings(TELEGRAM_BOT_TOKEN='test-token', WHATSAPP_ACCESS_TOKEN='test-token', WHATSAPP_PHONE_NUMBER_ID='12345', WHATSAPP_TEMPLATE_NAME='portal_reminder', WHATSAPP_TEMPLATE_LANGUAGE='fa', WHATSAPP_API_VERSION='v22.0')
    def test_official_adapter_payloads_and_malformed_success_result(self):
        from clinic.communications import deliver
        row=self.planned();row.channel='telegram'
        response=Mock(status_code=200);response.json.return_value={'ok':True,'result':{'message_id':123}}
        with patch('clinic.communications.requests.post',return_value=response) as network:
            self.assertEqual(deliver(row,'1234567'),'123')
            args=network.call_args
            self.assertTrue(args.args[0].startswith('https://api.telegram.org/bot'))
            self.assertNotIn(self.patient.phone,json.dumps(args.kwargs))
            response.json.return_value=[]
            with self.assertRaises(DeliveryFailure) as failure:deliver(row,'1234567')
            self.assertTrue(failure.exception.ambiguous)
            response.json.return_value={}
            with self.assertRaises(DeliveryFailure) as failure:deliver(row,'1234567')
            self.assertTrue(failure.exception.ambiguous)
            row.channel='whatsapp';response.json.return_value={'messages':[{'id':'accepted-test-id'}]}
            self.assertEqual(deliver(row,'989123456789'),'accepted-test-id')
            self.assertEqual(network.call_args.kwargs['json']['type'],'template')
            self.assertNotIn('components',network.call_args.kwargs['json']['template'])
        with patch('clinic.communications.requests.post',side_effect=requests.ReadTimeout):
            with self.assertRaises(DeliveryFailure) as failure:deliver(row,'989123456789')
            self.assertTrue(failure.exception.ambiguous)
        self.assertTrue(readiness('telegram')[0])


@override_settings(TELEGRAM_BOT_TOKEN='synthetic-bot-token', TELEGRAM_BOT_USERNAME='SyntheticClinicBot', TELEGRAM_WEBHOOK_SECRET='synthetic-webhook-secret-only-73-abcdefgh', COMMUNICATIONS_ENABLED=False)
class TelegramLinkTests(TestCase):
    link_url='/dash/api/communications/telegram/link'
    webhook_url='/dash/api/communications/telegram/webhook'
    secret='synthetic-webhook-secret-only-73-abcdefgh'

    def setUp(self):
        self.member=User.objects.create_user('telegram-link-patient',password='Synthetic-only-73!')
        self.account=PortalAccount.objects.create(user=self.member,email='link-patient@example.test')
        self.client.force_login(self.member)
        session=self.client.session;session['portal_auth_version']=self.account.auth_version;session.save()

    def link(self):
        response=self.client.post(self.link_url,{},content_type='application/json')
        self.assertEqual(response.status_code,200)
        data=response.json();self.assertEqual(data['expires_in'],900)
        self.assertEqual(urlsplit(data['url']).netloc,'t.me')
        return parse_qs(urlsplit(data['url']).query)['start'][0]

    def update(self,raw,**kwargs):
        return {'update_id':123,'message':{'chat':{'id':1234567,'type':'private'},'from':{'id':1234567,'is_bot':False},'text':'/start '+raw,**kwargs}}

    def webhook(self,payload,secret=None,client=None):
        return (client or self.client).post(self.webhook_url,payload,content_type='application/json',HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret or self.secret)

    def test_private_pairing_is_single_use_hashed_and_never_implies_consent(self):
        with patch('clinic.communications.requests.post') as network:
            raw=self.link()
            challenge=TelegramLinkChallenge.objects.get()
            self.assertNotEqual(challenge.token_digest,raw)
            self.assertNotIn(raw,str(challenge.__dict__))
            # An external webhook has no browser CSRF cookie or login session.
            external=Client(enforce_csrf_checks=True)
            self.assertEqual(self.webhook(self.update(raw),client=external).status_code,200)
            preference=ContactPreference.objects.get(account=self.account)
            self.assertEqual(preference.verified_telegram,'1234567')
            self.assertFalse(preference.telegram_opt_in)
            challenge.refresh_from_db();self.assertIsNotNone(challenge.consumed_at)
            self.webhook(self.update(raw,chat={'id':7654321,'type':'private'},**{'from':{'id':7654321,'is_bot':False}}),client=external)
            preference.refresh_from_db();self.assertEqual(preference.verified_telegram,'1234567')
        network.assert_not_called()

    def test_expired_replaced_and_revoked_tokens_cannot_bind(self):
        raw=self.link()
        TelegramLinkChallenge.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.webhook(self.update(raw));self.assertFalse(ContactPreference.objects.exists())
        old=self.link();fresh=self.link()
        self.webhook(self.update(old));self.assertFalse(ContactPreference.objects.exists())
        self.account.auth_version+=1;self.account.save()
        self.webhook(self.update(fresh));self.assertFalse(ContactPreference.objects.exists())

    def test_link_cannot_target_another_account_and_webhook_uses_token_bound_owner(self):
        other=User.objects.create_user('other-telegram-user')
        other_account=PortalAccount.objects.create(user=other,email='other-telegram@example.test')
        self.assertEqual(self.client.post(self.link_url,{'account':str(other_account.pk)},content_type='application/json').status_code,400)
        raw=self.link()
        payload=self.update(raw);payload['account']=str(other_account.pk)
        self.assertEqual(self.webhook(payload).status_code,200)
        self.assertTrue(ContactPreference.objects.filter(account=self.account,verified_telegram='1234567').exists())
        self.assertFalse(ContactPreference.objects.filter(account=other_account).exists())

    def test_secret_body_size_private_chat_and_sender_are_strict(self):
        raw=self.link();payload=self.update(raw)
        self.assertEqual(self.webhook(payload,secret='wrong').status_code,403)
        self.assertEqual(self.webhook({'message':'x'*9000}).status_code,400)
        for override in [
            {'chat':{'id':-12345,'type':'group'}},
            {'chat':{'id':True,'type':'private'}},
            {'from':{'id':7654321,'is_bot':False}},
            {'from':{'id':1234567,'is_bot':True}},
        ]:
            self.assertEqual(self.webhook(self.update(raw,**override)).status_code,400)
        self.assertEqual(self.webhook(self.update(raw,text='/start '+raw+' extra')).status_code,200)
        self.assertFalse(ContactPreference.objects.exists())
        self.assertIsNone(TelegramLinkChallenge.objects.get().consumed_at)

    def test_patient_role_session_and_csrf_are_required_to_issue_challenge(self):
        csrf_client=Client(enforce_csrf_checks=True);csrf_client.force_login(self.member)
        session=csrf_client.session;session['portal_auth_version']=0;session.save()
        self.assertEqual(csrf_client.post(self.link_url,{},content_type='application/json').status_code,403)
        self.member.groups.add(Group.objects.get_or_create(name='clinic_secretary')[0])
        self.assertEqual(self.client.post(self.link_url,{},content_type='application/json').status_code,403)
        self.member.groups.clear();raw=self.link()
        self.member.is_active=False;self.member.save()
        self.webhook(self.update(raw));self.assertFalse(ContactPreference.objects.exists())
        self.client.logout()
        self.assertEqual(self.client.post(self.link_url,{},content_type='application/json').status_code,401)

    def test_link_readiness_can_be_available_while_delivery_is_off(self):
        response=self.client.get('/dash/api/communications/preferences')
        self.assertTrue(response.json()['telegram_link_available'])
        self.assertFalse(any(channel['enabled'] for channel in response.json()['channels']))
        with override_settings(TELEGRAM_WEBHOOK_SECRET='too-short'):
            self.assertFalse(self.client.get('/dash/api/communications/preferences').json()['telegram_link_available'])
            self.assertEqual(self.client.post(self.link_url,{},content_type='application/json').status_code,503)
            self.assertEqual(self.webhook(self.update('x'*43)).status_code,403)
