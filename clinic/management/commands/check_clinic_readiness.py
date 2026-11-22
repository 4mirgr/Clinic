"""Read-only local operations report. No provider probes or configuration writes."""
import json
import os
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import DatabaseError, connections
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Count


def present(name):
    return bool(getattr(settings, name, ''))


def storage_status(directory):
    """Permission inspection is not a write/durability/restore test."""
    try:
        path = Path(directory)
        exists = path.is_dir()
        permission = exists and os.access(path, os.W_OK | os.X_OK)
    except (OSError, TypeError, ValueError):
        exists = permission = False
    return {'directory_exists': exists, 'writable_by_permission_check': bool(permission),
            'write_probe_performed': False, 'durability_verified': False}


def status_counts(model):
    known = {value for value, label in model._meta.get_field('status').choices}
    counts = {}
    for status, total in model.objects.order_by().values_list('status').annotate(total=Count('pk')):
        safe = status if status in known else 'unrecognized_status'
        counts[safe] = counts.get(safe, 0) + total
    return counts


def communication_status():
    from clinic.communications import portal_url, readiness
    required = {
        'email': ('EMAIL_HOST', 'DEFAULT_FROM_EMAIL'),
        'telegram': ('TELEGRAM_BOT_TOKEN',),
        'whatsapp': ('WHATSAPP_ACCESS_TOKEN', 'WHATSAPP_PHONE_NUMBER_ID',
                     'WHATSAPP_TEMPLATE_NAME', 'WHATSAPP_TEMPLATE_LANGUAGE', 'WHATSAPP_API_VERSION'),
    }
    result = {}
    for channel, names in required.items():
        missing = [name for name in names if not present(name)]
        invalid = []
        if not portal_url():
            invalid.append('COMMUNICATION_PORTAL_URL')
        if channel == 'email':
            if getattr(settings, 'EMAIL_BACKEND', '') != 'django.core.mail.backends.smtp.EmailBackend':
                invalid.append('EMAIL_BACKEND')
            if getattr(settings, 'EMAIL_USE_TLS', False) and getattr(settings, 'EMAIL_USE_SSL', False):
                invalid.extend(('EMAIL_USE_TLS', 'EMAIL_USE_SSL'))
        if channel == 'whatsapp':
            if present('WHATSAPP_API_VERSION') and not re.fullmatch(r'v[0-9]+\.[0-9]+', settings.WHATSAPP_API_VERSION):
                invalid.append('WHATSAPP_API_VERSION')
            if present('WHATSAPP_PHONE_NUMBER_ID') and not re.fullmatch(r'[0-9]+', settings.WHATSAPP_PHONE_NUMBER_ID):
                invalid.append('WHATSAPP_PHONE_NUMBER_ID')
        result[channel] = {'runtime_configured': not missing and not invalid,
                           'missing_settings': missing, 'invalid_settings': invalid,
                           'outbound_enabled': bool(getattr(settings, 'COMMUNICATIONS_ENABLED', False)),
                           'dispatch_ready': bool(readiness(channel)[0] and not invalid),
                           'live_connection_verified': False}
    return result


class Command(BaseCommand):
    help = 'Report safe local configuration/schema/queue status; no network, writes, sends or secret values.'
    requires_system_checks = []

    def handle(self, *args, **options):
        db = connections['default']
        database = {'reachable': False, 'engine': db.vendor, 'schema_pending_count': None,
                    'schema_current': False, 'production_postgresql_tls_configured': bool(
                        db.vendor == 'postgresql' and db.settings_dict.get('OPTIONS', {}).get('sslmode') == 'verify-full')}
        report = {
            'mode': 'local_read_only', 'provider_network_performed': False, 'database_reads_only': True,
            'provider_connections_verified': False,
            'private_runtime_deployment_verified': False,
            'database': database,
            'private_storage': storage_status(settings.MEDIA_ROOT),
            'security': {'production_mode': bool(getattr(settings, 'PRODUCTION', False)),
                         'debug_disabled': not settings.DEBUG,
                         'secure_session_cookie': settings.SESSION_COOKIE_SECURE,
                         'https_redirect_enabled': settings.SECURE_SSL_REDIRECT},
            'identity': {'shared_bridge_enabled': bool(getattr(settings, 'SHARED_AUTH_ENABLED', False)),
                         'shared_session_endpoint_verified': False,
                         'local_google_signin_configured': all(present(name) for name in (
                             'GOOGLE_AUTH_CLIENT_ID', 'GOOGLE_AUTH_CLIENT_SECRET', 'GOOGLE_AUTH_REDIRECT_URI')),
                         'live_google_signin_verified': False},
            'communications': communication_status(),
            'queue_counts': {},
            'scheduler_installation_verified': False,
            'production_backup_restore_verified': False,
        }
        inspect_database = True
        if db.vendor == 'sqlite' and not db.creation.is_in_memory_db(db.settings_dict['NAME']):
            try:
                inspect_database = Path(db.settings_dict['NAME']).is_file()
            except (OSError, TypeError, ValueError):
                inspect_database = False
        try:
            if not inspect_database:
                raise DatabaseError('local database absent')
            executor = MigrationExecutor(db)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            database.update(reachable=True, schema_pending_count=len(plan), schema_current=not plan)
        except (DatabaseError, OSError):
            database['error_code'] = 'database_or_schema_unavailable'
        if database['schema_current']:
            from clinic.calendar_health import diagnose_calendar
            from clinic.models import Appointment
            from clinic.communication_models import PatientNotification
            try:
                calendar = diagnose_calendar(probe=False)
                report['calendar'] = {name: calendar[name] for name in (
                    'status', 'missing_settings', 'invalid_settings', 'hours_ready', 'local_ready',
                    'probe_attempted', 'probe_verified')}
                report['calendar']['runtime_configured'] = not calendar['missing_settings'] and not calendar['invalid_settings']
                report['calendar']['live_connection_verified'] = False
                report['queue_counts'] = {
                    'calendar': status_counts(Appointment),
                    'notifications': status_counts(PatientNotification),
                }
            except (DatabaseError, OSError):
                report['clinical_status_error_code'] = 'local_status_unavailable'
        else:
            report['calendar'] = {'status': 'schema_not_ready', 'live_connection_verified': False}
        self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
