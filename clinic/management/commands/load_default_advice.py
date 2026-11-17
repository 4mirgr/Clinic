from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from clinic.access import role_for
from clinic.advice_catalog import load_defaults


class Command(BaseCommand):
    help='Import original source-backed patient handouts as drafts, without overwriting existing entries.'
    def add_arguments(self, parser):
        parser.add_argument('--reviewer', required=True, help='Existing active clinic manager username; does not approve the drafts.')
    def handle(self, *args, **options):
        actor=get_user_model().objects.filter(username=options['reviewer'],is_active=True).first()
        if not actor or role_for(actor) != 'manager':
            raise CommandError('An active clinic manager is required.')
        count=load_defaults(actor)
        self.stdout.write(f'Imported {count} drafts; existing handouts preserved.')
