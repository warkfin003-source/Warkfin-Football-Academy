"""Transactional email over HTTPS for hosts that block SMTP ports."""
import json
from email.utils import parseaddr
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

class EmailDeliveryError(Exception):
    pass

class BrevoEmailBackend(BaseEmailBackend):
    def send_messages(self,email_messages):
        sent=0
        for message in email_messages:
            try:
                if message.attachments or message.cc or message.bcc:
                    raise EmailDeliveryError('This portal transport supports plain-text transactional messages only.')
                name,address=parseaddr(message.from_email)
                recipients=[{'email':parseaddr(x)[1]} for x in message.to]
                if not address or not recipients or not settings.BREVO_API_KEY:
                    raise EmailDeliveryError('Email sender, recipients and API credential are required.')
                payload={'sender':{'name':name or 'Warkfin Football Academy','email':address},'to':recipients,'subject':message.subject,'textContent':message.body}
                request=Request('https://api.brevo.com/v3/smtp/email',data=json.dumps(payload).encode(),headers={'api-key':settings.BREVO_API_KEY,'Content-Type':'application/json','Accept':'application/json'},method='POST')
                with urlopen(request,timeout=settings.EMAIL_TIMEOUT) as response:
                    if response.status!=201: raise EmailDeliveryError('Email provider did not accept the message.')
                sent+=1
            except (HTTPError,URLError,TimeoutError,EmailDeliveryError):
                if not self.fail_silently:
                    raise EmailDeliveryError('Email delivery failed. Check the email service configuration and quota.') from None
        return sent
