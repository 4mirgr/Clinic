"""Operational diagnostics must remain read-only and never expose credentials."""
from contextlib import ExitStack
import importlib.util
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.db import connection, DatabaseError
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext


class ReadinessTests(TestCase):
    def report(self):
        output = StringIO()
        call_command('check_clinic_readiness', stdout=output)
        return json.loads(output.getvalue())

    @override_settings(COMMUNICATIONS_ENABLED=False, GOOGLE_CLIENT_ID='', GOOGLE_CLIENT_SECRET='',
                       GOOGLE_TOKEN_ENCRYPTION_KEY='', GOOGLE_AUTH_CLIENT_ID='',
                       EMAIL_HOST='', DEFAULT_FROM_EMAIL='', TELEGRAM_BOT_TOKEN='',
                       WHATSAPP_ACCESS_TOKEN='', SHARED_AUTH_ENABLED=False)
    def test_default_is_read_only_without_network_and_reports_missing_configuration(self):
        with ExitStack() as stack:
            stack.enter_context(patch('requests.sessions.Session.request', side_effect=AssertionError('network forbidden')))
            stack.enter_context(patch('smtplib.SMTP', side_effect=AssertionError('SMTP forbidden')))
            with CaptureQueriesContext(connection) as queries:
                result = self.report()
        writes = [entry['sql'] for entry in queries if entry['sql'].lstrip().upper().split(' ', 1)[0] in
                  {'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'REPLACE'}]
        self.assertEqual(writes, [])
        self.assertEqual(result['mode'], 'local_read_only')
        self.assertFalse(result['provider_network_performed'])
        self.assertFalse(result['provider_connections_verified'])
        self.assertFalse(result['scheduler_installation_verified'])
        self.assertFalse(result['production_backup_restore_verified'])
        self.assertTrue(result['database']['schema_current'])
        self.assertFalse(result['private_storage']['write_probe_performed'])
        self.assertIn('GOOGLE_CLIENT_ID', result['calendar']['missing_settings'])
        self.assertIn('EMAIL_HOST', result['communications']['email']['missing_settings'])
        self.assertFalse(result['communications']['email']['dispatch_ready'])
        self.assertEqual(result['queue_counts']['notifications'], {})

    @override_settings(COMMUNICATIONS_ENABLED=True, EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
                       EMAIL_HOST='smtp-secret-host.example.test',
                       DEFAULT_FROM_EMAIL='private-sender@example.test', EMAIL_HOST_PASSWORD='private-smtp-secret',
                       EMAIL_USE_TLS=True, EMAIL_USE_SSL=False, GOOGLE_CLIENT_ID='private-google-client',
                       GOOGLE_CLIENT_SECRET='private-google-secret', GOOGLE_TOKEN_ENCRYPTION_KEY='private-invalid-key',
                       TELEGRAM_BOT_TOKEN='private-telegram-secret')
    def test_configuration_presence_never_claims_live_verification_or_prints_values(self):
        result = self.report()
        encoded = json.dumps(result)
        for value in ('smtp-secret-host.example.test', 'private-sender@example.test', 'private-smtp-secret',
                      'private-google-client', 'private-google-secret', 'private-invalid-key', 'private-telegram-secret'):
            self.assertNotIn(value, encoded)
        self.assertTrue(result['communications']['email']['runtime_configured'])
        self.assertTrue(result['communications']['email']['dispatch_ready'])
        self.assertFalse(result['communications']['email']['live_connection_verified'])
        self.assertIn('GOOGLE_TOKEN_ENCRYPTION_KEY', result['calendar']['invalid_settings'])
        self.assertFalse(result['calendar']['probe_attempted'])
        self.assertFalse(result['calendar']['live_connection_verified'])

    def test_pending_schema_skips_clinical_queries(self):
        with patch('clinic.management.commands.check_clinic_readiness.MigrationExecutor') as executor:
            executor.return_value.migration_plan.return_value = [object()]
            result = self.report()
        self.assertFalse(result['database']['schema_current'])
        self.assertEqual(result['database']['schema_pending_count'], 1)
        self.assertEqual(result['calendar']['status'], 'schema_not_ready')
        self.assertEqual(result['queue_counts'], {})

    def test_missing_sqlite_file_is_not_created_by_diagnostics(self):
        with TemporaryDirectory(prefix='clinic-absent-database-') as directory:
            path = Path(directory) / 'must-not-be-created.sqlite3'
            db = SimpleNamespace(vendor='sqlite', settings_dict={'NAME': path},
                                 creation=SimpleNamespace(is_in_memory_db=lambda name: False))
            with patch('clinic.management.commands.check_clinic_readiness.connections', {'default': db}), \
                    patch('clinic.management.commands.check_clinic_readiness.MigrationExecutor') as executor:
                result = self.report()
            executor.assert_not_called()
            self.assertFalse(path.exists())
            self.assertFalse(result['database']['reachable'])

    def test_database_failure_does_not_echo_credentials_from_error(self):
        with patch('clinic.management.commands.check_clinic_readiness.MigrationExecutor',
                   side_effect=DatabaseError('password=private-db-secret host=private-host')):
            result = self.report()
        self.assertFalse(result['database']['reachable'])
        self.assertNotIn('private-db-secret', json.dumps(result))
        self.assertEqual(result['database']['error_code'], 'database_or_schema_unavailable')


class SyntheticRestoreTests(SimpleTestCase):
    def test_encrypted_sqlite_file_drill_is_isolated_and_rejects_wrong_key_and_tampering(self):
        script = Path(settings.BASE_DIR) / 'scripts' / 'check_backup_restore.py'
        spec = importlib.util.spec_from_file_location('isolated_restore_drill', script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with TemporaryDirectory(prefix='clinic-existing-data-sentinel-') as sentinel:
            path = Path(sentinel) / 'unchanged'
            path.write_bytes(b'existing-data-must-not-be-read-or-modified')
            with patch.dict('os.environ', {'DATABASE_URL': 'postgres://never-read:secret@forbidden.example/real',
                                         'CLINIC_DATA_DIR': sentinel}):
                with patch('sqlite3.connect', wraps=module.sqlite3.connect) as connect:
                    result = module.exercise_backup_restore()
            for call in connect.call_args_list:
                self.assertIn('clinic-synthetic-restore-', str(call.args[0]))
                self.assertNotIn(sentinel, str(call.args[0]))
            self.assertEqual(path.read_bytes(), b'existing-data-must-not-be-read-or-modified')
        self.assertTrue(result['synthetic_only'])
        self.assertTrue(result['wrong_key_rejected'])
        self.assertTrue(result['tampering_rejected'])
        self.assertEqual(result['restored_private_files'], 1)
        self.assertEqual(result['restored_linked_records'], 1)
        self.assertFalse(result['production_postgresql_restore_verified'])
