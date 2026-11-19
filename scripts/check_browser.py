"""Run native browser checks with independent database connections.

Django shares one in-memory SQLite connection across LiveServer HTTP threads.
Parallel portal requests can then interfere with another thread's transaction.
A disposable file-backed test database models normal runtime connections.
PostgreSQL keeps its normal isolated test database. No app database is altered.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.core.management import call_command
from django.db import connections

with tempfile.TemporaryDirectory(prefix='clinic-browser-database-') as scratch:
    db=connections['default']
    if db.vendor=='sqlite':
        db.settings_dict['TEST']['NAME']=str(Path(scratch)/'browser.sqlite3')
    call_command('test',*(sys.argv[1:] or ['clinic.browser_checks']),interactive=False)
