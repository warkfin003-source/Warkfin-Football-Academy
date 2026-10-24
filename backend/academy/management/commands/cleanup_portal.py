"""Remove expired rate counters and sessions while retaining academy and audit records."""
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
from academy.models import RateBucket

class Command(BaseCommand):
    help='Remove expired throttle counters and sessions. Schedule daily in production.'
    def handle(self,*args,**options):
        RateBucket.objects.filter(expires_at__lt=timezone.now()).delete()
        call_command('clearsessions')
        self.stdout.write('Expired counters and sessions removed.')
