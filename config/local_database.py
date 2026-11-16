"""Read only Neon's database keys locally, without sourcing executable shell."""
import os
import shlex
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


def load_local_database(directory, argv, environ=None):
    env = os.environ if environ is None else environ
    # Automated tests use only explicitly supplied disposable test connections.
    if ('test' in argv or env.get('CLINIC_ENV') == 'production'
            or env.get('DATABASE_URL') == ''):
        return
    file = Path(directory)/'.env'
    if not file.is_file():
        return
    for line in file.read_text().splitlines():
        key, separator, value = line.strip().removeprefix('export ').partition('=')
        key = key.strip()
        if not separator or key not in {'DATABASE_URL','DATABASE_URL_UNPOOLED'} or key in env:
            continue
        try:
            parts = shlex.split(value, comments=True)
        except ValueError:
            raise ImproperlyConfigured('Invalid local database environment value.') from None
        if len(parts) != 1:
            raise ImproperlyConfigured('A local database URL must be a single value.')
        env[key] = parts[0]
