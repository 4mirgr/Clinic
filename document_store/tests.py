import tempfile
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase, override_settings


class PrivateDatabaseStorageTests(TestCase):
    def setUp(self):
        from .storage import DatabaseDocumentStorage
        self.storage = DatabaseDocumentStorage()

    def test_bytes_survive_a_new_storage_instance_without_a_local_media_file(self):
        from .storage import DatabaseDocumentStorage
        name = self.storage.save('synthetic/record.pdf', ContentFile(b'%PDF-1.7\nprivate sample\n%%EOF'))
        with tempfile.TemporaryDirectory() as empty, override_settings(MEDIA_ROOT=empty):
            with DatabaseDocumentStorage().open(name) as file:
                self.assertEqual(file.read(), b'%PDF-1.7\nprivate sample\n%%EOF')
        self.assertEqual(self.storage.size(name), 29)

    @override_settings(CLINIC_DOCUMENT_BUDGET_BYTES=50)
    def test_hard_budget_rejects_new_data_and_keeps_existing_files(self):
        from .exceptions import DocumentStorageFull
        from .models import DocumentBlob, StorageBudget
        name = self.storage.save('one.pdf', ContentFile(b'a'*30))
        with self.assertRaises(DocumentStorageFull):
            self.storage.save('two.pdf', ContentFile(b'b'*30))
        self.assertEqual(DocumentBlob.objects.count(), 1)
        self.assertEqual(StorageBudget.objects.get().used_bytes, 30)
        self.assertEqual(self.storage.open(name).read(), b'a'*30)
        self.storage.delete(name)
        self.assertEqual(StorageBudget.objects.get().used_bytes, 0)
        self.storage.save('three.pdf', ContentFile(b'c'*40))

    def test_document_and_storage_transaction_roll_back_together(self):
        from .models import DocumentBlob
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.storage.save('rolled-back.pdf',ContentFile(b'synthetic'))
                raise RuntimeError('synthetic metadata failure')
        self.assertEqual(DocumentBlob.objects.count(),0)

    def test_public_urls_and_filesystem_paths_are_not_available(self):
        with self.assertRaises(NotImplementedError):self.storage.url('private.pdf')
        with self.assertRaises(NotImplementedError):self.storage.path('private.pdf')

    def test_collision_does_not_overwrite_and_checksum_is_checked(self):
        from .models import DocumentBlob
        name=self.storage.save('same.pdf',ContentFile(b'first'))
        other=self.storage.save('same.pdf',ContentFile(b'second'))
        self.assertNotEqual(name,other)
        self.assertEqual(self.storage.open(name).read(),b'first')
        DocumentBlob.objects.filter(name=name).update(content=b'changed')
        with self.assertRaises(OSError):self.storage.open(name)

    def test_missing_delete_is_idempotent_and_missing_open_is_explicit(self):
        self.storage.delete('missing.pdf')
        with self.assertRaises(FileNotFoundError):self.storage.open('missing.pdf')


@override_settings(STORAGES={'default':{'BACKEND':'document_store.storage.DatabaseDocumentStorage'},
    'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}},CLINIC_DOCUMENT_BUDGET_BYTES=30)
class PrivateUploadBudgetTests(TestCase):
    def setUp(self):
        import json
        from django.test import Client
        self.client=Client(enforce_csrf_checks=True)
        def post(route,data):
            token=self.client.get('/dash/api/portal/session').json()['csrf_token']
            return self.client.post('/dash/api/portal/'+route,json.dumps(data),content_type='application/json',HTTP_X_CSRFTOKEN=token)
        self.assertEqual(post('signup',{'username':'quota-reader','email':'quota@example.test','display_name':'آزمایشی','password':'Synthetic storage password 937!'}).status_code,201)
        self.assertEqual(post('profile',{'first_name':'بیمار','last_name':'آزمایشی','phone':'09123456789'}).status_code,200)

    def upload(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        csrf=self.client.get('/dash/api/portal/session').json()['csrf_token']
        return self.client.post('/dash/api/portal/documents',{'title':'مدرک ساختگی','category':'lab',
            'file':SimpleUploadedFile('synthetic.pdf',b'%PDF-1.7\nsynthetic\n%%EOF')},HTTP_X_CSRFTOKEN=csrf)

    def test_full_storage_rejects_only_the_new_upload_and_keeps_private_downloads(self):
        from clinic.models import Document
        first=self.upload();self.assertEqual(first.status_code,201)
        url=first.json()['document']['download_url']
        second=self.upload();self.assertEqual(second.status_code,507)
        self.assertEqual(second.json()['error'],'document_storage_full')
        self.assertEqual(Document.objects.count(),1)
        response=self.client.get(url)
        self.assertEqual(b''.join(response.streaming_content),b'%PDF-1.7\nsynthetic\n%%EOF')
        self.assertIn('no-store',response['Cache-Control'])
        from django.test import Client
        self.assertEqual(Client().get(url).status_code,401)


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, skipUnlessDBFeature


@override_settings(CLINIC_DOCUMENT_BUDGET_BYTES=50)
class ConcurrentDocumentBudgetTests(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_parallel_postgresql_uploads_cannot_exceed_the_shared_budget(self):
        from .models import DocumentBlob,StorageBudget
        from .storage import DatabaseDocumentStorage
        from .exceptions import DocumentStorageFull
        StorageBudget.objects.create(pk=1)
        barrier=Barrier(2)
        def write(index):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                try:
                    DatabaseDocumentStorage().save(f'race-{index}.pdf',ContentFile(b'x'*35))
                    return 'saved'
                except DocumentStorageFull:
                    return 'full'
            finally:
                # Persistent connections are thread-local; close them even when
                # fresh so Django can drop the disposable PostgreSQL database.
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(write,range(2)))
        self.assertCountEqual(results,['saved','full'])
        self.assertEqual(DocumentBlob.objects.count(),1)
        self.assertEqual(StorageBudget.objects.get().used_bytes,35)
