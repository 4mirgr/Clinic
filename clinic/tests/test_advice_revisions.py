"""Editorial versions stay private and preserve the exact saved library state."""
from django.apps import apps
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import patch

from clinic.models import Advice, AdviceDelivery, AuditEvent, Patient


class AdviceRevisionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user('revision-author')
        cls.editor = User.objects.create_user('revision-editor')
        doctors = Group.objects.get_or_create(name='clinic_manager')[0]
        cls.author.groups.add(doctors)
        cls.editor.groups.add(doctors)
        cls.secretary = User.objects.create_user('revision-secretary')
        cls.secretary.groups.add(Group.objects.get_or_create(name='clinic_secretary')[0])
        cls.patient_user = User.objects.create_user('revision-patient')

    def revisions(self, advice):
        self.assertIn('advicerevision', apps.all_models['clinic'], 'Advice editorial history is missing')
        return apps.get_model('clinic', 'AdviceRevision').objects.filter(advice=advice).order_by('created_at', 'pk')

    def values(self, **changes):
        values = {'title':'راهنمای اول', 'title_en':'First guide', 'specialty':'cardiology',
                  'body':'متن نخست', 'tags':'قلب، heart', 'source':'منبع نخست'}
        values.update(changes)
        return values

    def create_via_form(self, **changes):
        self.client.force_login(self.author)
        response = self.client.post(reverse('advice_new'), self.values(**changes))
        self.assertEqual(response.status_code, 302)
        return Advice.objects.get(title=changes.get('title', 'راهنمای اول'))

    def test_created_draft_has_exact_private_version(self):
        advice = self.create_via_form()
        version = self.revisions(advice).get()
        self.assertEqual(version.title, 'راهنمای اول')
        self.assertEqual(version.title_en, 'First guide')
        self.assertEqual(version.specialty, 'cardiology')
        self.assertEqual(version.tags, 'قلب، heart')
        self.assertEqual(version.body, 'متن نخست')
        self.assertEqual(version.source, 'منبع نخست')
        self.assertEqual(version.actor, self.author)
        self.assertEqual(version.advice_updated_at, advice.updated_at)
        self.assertFalse(version.is_approved)
        self.assertFalse(version.is_baseline)

    def test_first_legacy_edit_preserves_old_actor_time_and_source_metadata(self):
        advice = Advice.objects.create(updated_by=self.author, is_approved=True,
            source_metadata={'publisher':'Original publisher', 'retrieved_on':'2026-11-17'},
            **self.values())
        # Simulate a row written before revision tracking was installed.
        self.revisions(advice).delete()
        original_time = advice.updated_at
        self.client.force_login(self.editor)
        response = self.client.post(reverse('advice_edit', args=[advice.pk]), self.values(body='متن دوم'))
        self.assertEqual(response.status_code, 302)
        old, current = self.revisions(advice)
        self.assertTrue(old.is_baseline)
        self.assertEqual(old.actor, self.author)
        self.assertEqual(old.advice_updated_at, original_time)
        self.assertEqual(old.source_metadata, {'publisher':'Original publisher', 'retrieved_on':'2026-11-17'})
        self.assertTrue(old.is_approved)
        self.assertEqual(old.body, 'متن نخست')
        self.assertEqual(current.actor, self.editor)
        self.assertEqual(current.body, 'متن دوم')
        self.assertFalse(current.is_approved)
        advice.refresh_from_db()
        self.assertFalse(advice.is_approved)
        self.assertEqual(current.advice_updated_at, advice.updated_at)

    def test_unchanged_save_does_not_steal_author_or_change_revision_timestamp(self):
        advice = self.create_via_form()
        original_time = advice.updated_at
        self.client.force_login(self.editor)
        self.client.post(reverse('advice_edit', args=[advice.pk]), self.values())
        advice.refresh_from_db()
        self.assertEqual(advice.updated_at, original_time)
        self.assertEqual(advice.updated_by, self.author)
        self.assertEqual(self.revisions(advice).count(), 1)

    def test_approval_only_change_is_recorded_and_explicit_review_is_preserved(self):
        advice = self.create_via_form()
        self.client.force_login(self.editor)
        self.client.post(reverse('advice_edit', args=[advice.pk]), self.values(is_approved='on'))
        approved = self.revisions(advice).last()
        self.assertTrue(approved.is_approved)
        self.assertEqual(approved.actor, self.editor)
        self.client.post(reverse('advice_edit', args=[advice.pk]), self.values(body='بازبینی صریح متن تازه', is_approved='on'))
        reviewed = self.revisions(advice).last()
        self.assertEqual(reviewed.body, 'بازبینی صریح متن تازه')
        self.assertTrue(reviewed.is_approved)
        self.assertEqual(self.revisions(advice).count(), 3)

    def test_future_edits_do_not_mutate_old_versions_or_patient_deliveries(self):
        advice = self.create_via_form(is_approved='on')
        patient = Patient.objects.create(first_name='بیمار', last_name='آزمایشی', phone='00000000000')
        import uuid
        delivery = AdviceDelivery.objects.create(patient=patient, advice=advice, title=advice.title,
            body=advice.body, tags=advice.tags, source=advice.source,
            advice_updated_at=advice.updated_at, created_by=self.author, request_key=uuid.uuid4())
        version = self.revisions(advice).get()
        self.client.force_login(self.editor)
        self.client.post(reverse('advice_edit', args=[advice.pk]), self.values(title='عنوان تازه', body='متن تازه', source='منبع تازه'))
        version.refresh_from_db()
        delivery.refresh_from_db()
        self.assertEqual((version.title, version.body, version.source), ('راهنمای اول', 'متن نخست', 'منبع نخست'))
        self.assertEqual((delivery.title, delivery.body, delivery.source), ('راهنمای اول', 'متن نخست', 'منبع نخست'))
        version.body = 'بازنویسی غیرمجاز'
        with self.assertRaises(ValidationError):
            version.save()
        self.assertFalse(AuditEvent.objects.filter(target__contains='متن').exists())

    def test_history_requires_doctor_even_when_secretary_has_patient_access(self):
        advice = self.create_via_form()
        version = self.revisions(advice).get()
        urls = [reverse('advice_history', args=[advice.pk]), reverse('advice_revision_detail', args=[advice.pk, version.pk])]
        for shared in (False, True):
            with override_settings(SHARED_AUTH_ENABLED=shared, MIDDLEWARE=['django.contrib.sessions.middleware.SessionMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware']):
                for user in (self.secretary, self.patient_user):
                    client = self.client_class()
                    client.force_login(user)
                    for url in urls:
                        response = client.get(url)
                        self.assertEqual(response.status_code, 403, (shared, user.username, url, dict(response.headers)))
        self.client.force_login(self.author)
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn('no-store', response.headers['Cache-Control'])
            self.assertContains(response, self.author.username)
        other = Advice.objects.create(title='راهنمای دیگر', body='متن دیگر', updated_by=self.author)
        self.assertEqual(self.client.get(reverse('advice_revision_detail', args=[other.pk, version.pk])).status_code, 404)

    def test_invalid_edit_does_not_create_a_revision_or_change_existing_advice(self):
        advice = self.create_via_form()
        response = self.client.post(reverse('advice_edit', args=[advice.pk]), self.values(title=''))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.revisions(advice).count(), 1)
        advice.refresh_from_db()
        self.assertEqual(advice.title, 'راهنمای اول')

    def test_ordinary_model_edit_resets_approval_and_preserves_source_metadata(self):
        advice = Advice.objects.create(updated_by=self.author, is_approved=True,
            source_metadata={'publisher':'Original publisher'}, **self.values())
        advice.source_metadata = {'publisher':'Corrected publisher'}
        advice.updated_by = self.editor
        advice.save()
        original, changed = self.revisions(advice)
        self.assertEqual(original.source_metadata, {'publisher':'Original publisher'})
        self.assertEqual(changed.source_metadata, {'publisher':'Corrected publisher'})
        self.assertFalse(changed.is_approved)

    def test_packet_review_records_actual_approver_without_exposing_editorial_metadata(self):
        advice = self.create_via_form()
        patient = Patient.objects.create(first_name='بیمار', last_name='آزمایشی', phone='00000000000')
        self.client.force_login(self.editor)
        response = self.client.post(reverse('advice_packet_prepare'), {'patient':patient.pk, 'advice_ids':[advice.pk]})
        response = self.client.post(reverse('advice_packet_confirm'), {'review_token':response.context['review_token'], 'reviewed':'on'})
        self.assertEqual(response.status_code, 302)
        approved = self.revisions(advice).last()
        self.assertTrue(approved.is_approved)
        self.assertEqual(approved.actor, self.editor)
        self.assertNotContains(self.client.get(response.url), self.author.username)

    def test_history_write_failure_rolls_back_advice_update(self):
        advice = self.create_via_form()
        model = apps.get_model('clinic', 'AdviceRevision')
        advice.body = 'تغییر ناموفق'
        with patch.object(model, 'save', side_effect=RuntimeError('isolated history storage failure')):
            with self.assertRaises(RuntimeError):
                advice.save()
        advice.refresh_from_db()
        self.assertEqual(advice.body, 'متن نخست')
        self.assertEqual(self.revisions(advice).count(), 1)

    def test_stale_partial_save_does_not_overwrite_an_unspecified_updater(self):
        advice = self.create_via_form()
        stale = Advice.objects.get(pk=advice.pk)
        advice.body = 'متن ثبت‌شده توسط پزشک دوم'
        advice.updated_by = self.editor
        advice.save()
        stale.tags = 'برچسب تازه'
        stale.save(update_fields=['tags'])
        advice.refresh_from_db()
        self.assertEqual(advice.body, 'متن ثبت‌شده توسط پزشک دوم')
        self.assertEqual(advice.updated_by, self.editor)
        version = self.revisions(advice).last()
        self.assertEqual(version.actor, self.editor)
        self.assertEqual(version.body, 'متن ثبت‌شده توسط پزشک دوم')
        self.assertEqual(version.tags, 'برچسب تازه')

    def test_partial_save_with_explicit_updater_id_records_requested_actor(self):
        advice = self.create_via_form()
        advice.tags = 'برچسب بازبینی‌شده'
        advice.updated_by_id = self.editor.pk
        advice.save(update_fields=['tags', 'updated_by_id'])
        advice.refresh_from_db()
        self.assertEqual(advice.updated_by, self.editor)
        self.assertEqual(self.revisions(advice).last().actor, self.editor)
