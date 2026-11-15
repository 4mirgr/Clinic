from django.core.management.base import BaseCommand
from django.utils import timezone

from clinic.calendar_models import Appointment
from clinic.scheduling import sync_appointment


class Command(BaseCommand):
    help = 'Retry due Google Calendar operations. Schedule every minute in the hosting scheduler.'

    def add_arguments(self,parser):
        parser.add_argument('--limit',type=int,default=50)

    def handle(self,*args,**options):
        ids = list(Appointment.objects.filter(status__in=['pending','update_pending','cancel_pending','conflict_cancelling'],sync_attempts__lt=10,next_retry_at__lte=timezone.now()).order_by('next_retry_at').values_list('pk',flat=True)[:max(1,min(options['limit'],500))])
        for pk in ids:
            sync_appointment(pk)
        self.stdout.write(f'Processed {len(ids)} due calendar operations. No patient details logged.')
