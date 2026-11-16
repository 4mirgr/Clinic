import tempfile
import os
import subprocess
import sys
from pathlib import Path
from django.test import SimpleTestCase
from config.local_database import load_local_database


class LocalDatabaseConfigurationTests(SimpleTestCase):
    def test_explicit_empty_runtime_database_disables_local_direct_database_too(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'.env').write_text('DATABASE_URL_UNPOOLED=postgresql://synthetic@localhost/direct\n')
            env={'DATABASE_URL':''}
            load_local_database(directory,['manage.py','migrate'],env)
            self.assertEqual(env,{'DATABASE_URL':''})

    def test_migration_with_explicit_empty_database_ignores_inherited_direct_url(self):
        from django.conf import settings
        with tempfile.TemporaryDirectory() as directory:
            env={**os.environ,'CLINIC_ENV':'development','DATABASE_URL':'',
                 'DATABASE_URL_UNPOOLED':'postgresql://synthetic@localhost/not-a-test-database',
                 'CLINIC_DATA_DIR':directory}
            result=subprocess.run([sys.executable,'-c',
                "import sys; sys.argv=['manage.py','migrate']; from config import settings; print(settings.DATABASES['default']['ENGINE'])"],
                cwd=settings.BASE_DIR,env=env,capture_output=True,text=True,check=True)
            self.assertEqual(result.stdout.strip(),'django.db.backends.sqlite3')

    def test_reads_only_database_keys_and_keeps_runtime_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'.env').write_text('DATABASE_URL="postgresql://synthetic@localhost/local"\nDATABASE_URL_UNPOOLED=postgresql://synthetic@localhost/direct\nOTHER_SECRET=must-not-load\n')
            env={'DATABASE_URL':'explicit-runtime-value'}
            load_local_database(directory,['manage.py','check'],env)
            self.assertEqual(env['DATABASE_URL'],'explicit-runtime-value')
            self.assertEqual(env['DATABASE_URL_UNPOOLED'],'postgresql://synthetic@localhost/direct')
            self.assertNotIn('OTHER_SECRET',env)

    def test_never_loads_real_local_database_for_tests_or_production(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'.env').write_text('DATABASE_URL=postgresql://synthetic@localhost/local\n')
            for env,args in [({},['manage.py','test']),({'CLINIC_ENV':'production'},['manage.py','runserver'])]:
                load_local_database(directory,args,env)
                self.assertNotIn('DATABASE_URL',env)

    def test_environment_text_is_not_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            marker=Path(directory)/'must-not-exist'
            (Path(directory)/'.env').write_text("DATABASE_URL='$(touch "+str(marker)+")'\n")
            env={};load_local_database(directory,['manage.py','check'],env)
            self.assertFalse(marker.exists())
            self.assertTrue(env['DATABASE_URL'].startswith('$('))
