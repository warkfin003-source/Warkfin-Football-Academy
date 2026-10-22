"""Read-only SMS credit check; never sends a message or prints account details."""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from django.conf import settings
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Check Brevo API access and SMS credit availability without sending SMS.'

    def handle(self, *args, **options):
        if not settings.BREVO_API_KEY:
            self.stdout.write('SMS readiness: API key missing.')
            return
        request = Request('https://api.brevo.com/v3/account',
            headers={'api-key': settings.BREVO_API_KEY, 'Accept': 'application/json'})
        try:
            with urlopen(request, timeout=15) as response:
                account = json.loads(response.read(262144))
            plans = [p for p in account.get('plan', []) if p.get('type') == 'sms']
            credits = [p.get('credits') for p in plans if isinstance(p.get('credits'), (float, int))]
            if not credits:
                self.stdout.write('SMS readiness: API accessible; SMS credit availability not confirmed. Check Brevo SMS credits and sender approval.')
            else:
                self.stdout.write(f'SMS readiness: reported SMS credits = {sum(credits):g}. Sender approval and delivery still require verification.')
        except HTTPError as error:
            self.stdout.write(f'SMS readiness: provider HTTP {error.code}; check key permissions and authorized IPs.')
        except Exception:
            self.stdout.write('SMS readiness: provider check unavailable; no account details logged.')
