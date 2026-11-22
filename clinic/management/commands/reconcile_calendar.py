import json

from django.core.management.base import BaseCommand, CommandError

from clinic.calendar_reconciliation import reconcile_calendar


class Command(BaseCommand):
    help = ('Count future confirmed clinic events locally. --probe reads only exact owned events; '
            '--apply-google adopts owned changes locally, or --flag-reviewed-mismatches preserves time holds. Never writes to Google.')

    def add_arguments(self, parser):
        parser.add_argument('--probe', action='store_true')
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--flag-reviewed-mismatches', action='store_true')
        mode.add_argument('--apply-google', action='store_true')
        parser.add_argument('--limit', type=int, default=50)
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **options):
        if (options['flag_reviewed_mismatches'] or options['apply_google']) and not options['probe']:
            raise CommandError('--flag-reviewed-mismatches and --apply-google require --probe.')
        report = reconcile_calendar(probe=options['probe'],
            flag_reviewed_mismatches=options['flag_reviewed_mismatches'], apply_google=options['apply_google'], limit=options['limit'])
        if options['as_json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False))
        else:
            self.stdout.write('Calendar reconciliation: '+report['status'])
            self.stdout.write(' '.join(f'{key}={value}' for key, value in report.items()
                                      if isinstance(value, int) and not isinstance(value, bool)))
            if report['issues']:
                self.stdout.write('Issues: '+', '.join(report['issues']))
            self.stdout.write('No Google events were changed. '
                              + ('Provider reads explicitly requested.' if options['probe'] else 'No provider request or local write performed.'))
