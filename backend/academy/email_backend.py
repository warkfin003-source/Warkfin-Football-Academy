"""Send transactional mail over HTTPS, with diagnostics that never expose secrets."""
import json
import logging
from email.utils import parseaddr
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

class EmailDeliveryError(Exception):
    """A safe, actionable failure; never include provider response bodies."""


def provider_error(error):
    """Classify a bounded provider response without logging its private contents."""
    try:
        body = error.read(8192).decode('utf-8', errors='replace').lower()
    except Exception:
        body = ''
    # Only fixed descriptions leave this function, even if the provider echoes a key.
    if 'ip' in body and ('unauthorized' in body or 'unrecognised' in body or 'unrecognized' in body):
        reason = 'Provider IP authorization blocked this server; check Brevo authorized IP settings.'
    elif 'not activated' in body or 'not active' in body or 'suspended' in body:
        reason = 'Transactional sending is inactive or suspended; check Brevo account activation.'
    elif 'sender' in body:
        reason = 'Provider rejected the sender; check its verification and address.'
    elif error.code == 401:
        reason = 'Provider rejected authentication; check the API key and authorized IP settings.'
    elif error.code == 403:
        reason = 'Provider denied access; check key permissions and transactional account status.'
    elif error.code == 429:
        reason = 'Provider rate limit or sending quota was reached.'
    else:
        reason = 'Provider rejected the request; review transactional email configuration.'
    return EmailDeliveryError(f'Brevo HTTP {error.code}: {reason}')


class BrevoEmailBackend(BaseEmailBackend):
    """Plain-text account mail only; campaigns and attachments are unsupported."""

    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            try:
                if message.attachments or message.cc or message.bcc:
                    raise EmailDeliveryError('This transport supports plain-text transactional messages only.')
                name, address = parseaddr(message.from_email)
                recipients = [{'email': parseaddr(value)[1]} for value in message.to]
                key = settings.BREVO_API_KEY.strip()
                if not address or not recipients or not key:
                    raise EmailDeliveryError('Email sender, recipients and API credential are required.')
                if key == 'Your private Brevo API key':
                    raise EmailDeliveryError('Replace the API-key placeholder with the actual private credential.')
                payload = {'sender': {'name': name or 'Warkfin Football Academy', 'email': address},
                           'to': recipients, 'subject': message.subject, 'textContent': message.body}
                request = Request('https://api.brevo.com/v3/smtp/email',
                                  data=json.dumps(payload).encode(),
                                  headers={'api-key': key, 'Content-Type': 'application/json', 'Accept': 'application/json'},
                                  method='POST')
                with urlopen(request, timeout=settings.EMAIL_TIMEOUT) as response:
                    if response.status != 201:
                        raise EmailDeliveryError('Email provider did not accept the message.')
                sent += 1
            except HTTPError as error:
                failure = provider_error(error)
                logger.error('%s', failure)
                if not self.fail_silently:
                    raise failure from None
            except (URLError, TimeoutError):
                logger.error('Email provider network connection failed or timed out.')
                if not self.fail_silently:
                    raise EmailDeliveryError('Email provider network connection failed or timed out.') from None
            except EmailDeliveryError as error:
                logger.error('%s', error)
                if not self.fail_silently:
                    raise
        return sent
