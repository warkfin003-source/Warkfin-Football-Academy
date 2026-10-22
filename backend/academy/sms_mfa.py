"""Password-first SMS verification with bounded sends, attempts and provider failures."""
import json
import logging
import re
import secrets
import time
from datetime import timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from django import forms
from django.conf import settings
from django.db import transaction
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.crypto import salted_hmac, constant_time_compare
from .models import User, OwnerSMSChallenge, AuditEvent

logger = logging.getLogger(__name__)


class SMSDeliveryError(Exception):
    """Safe errors contain no provider body, API credential or verification code."""


class SMSCodeForm(forms.Form):
    token = forms.RegexField(regex=r'^\d{6}$', label='Six-digit SMS code',
        widget=forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'one-time-code', 'maxlength': '6'}))


def fingerprint(value):
    """Keyed hashes protect short numeric codes against offline enumeration."""
    return salted_hmac('academy.owner.sms.v1', value, algorithm='sha256').hexdigest()


def identity(request):
    return fingerprint(f'{request.user.pk}:{settings.OWNER_SMS_PHONE}')


def sms_verified(request):
    return bool(request.user.is_authenticated and request.user.is_active and
        request.user.is_superuser and request.user.email_verified and
        constant_time_compare(request.session.get('owner_sms_verified', ''), identity(request)) and
        0 <= time.time() - request.session.get('owner_mfa_at', 0) < settings.OWNER_MFA_MAX_AGE)


def send_sms(code):
    """Submit one transactional SMS. Provider acceptance is not delivery confirmation."""
    phone = settings.OWNER_SMS_PHONE
    if not re.fullmatch(r'\+[1-9]\d{7,14}', phone) or not settings.BREVO_API_KEY:
        raise SMSDeliveryError('SMS delivery is not configured. Contact the academy owner.')
    payload = {'sender': settings.OWNER_SMS_SENDER, 'recipient': phone.lstrip('+'),
        'content': f'Warkfin Academy: Your sign-in code is {code}. Valid for 5 minutes. Never share this code.',
        'type': 'transactional', 'tag': 'ownerLogin'}
    request = Request('https://api.brevo.com/v3/transactionalSMS/send',
        data=json.dumps(payload).encode(), method='POST',
        headers={'api-key': settings.BREVO_API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'})
    try:
        with urlopen(request, timeout=15) as response:
            if response.status != 201:
                raise SMSDeliveryError('SMS provider did not accept this message.')
    except HTTPError as error:
        # Never log response bodies: some providers echo sensitive request values.
        logger.warning('Owner SMS provider rejected request (HTTP %s).', error.code)
        raise SMSDeliveryError('SMS could not be sent. Check Brevo SMS activation, sender approval, credits and authorized IPs.') from None
    except (URLError, TimeoutError, OSError):
        logger.warning('Owner SMS provider connection failed.')
        raise SMSDeliveryError('SMS service is temporarily unavailable. Please try again later.') from None


def sms_security(request):
    """Called only through the active, email-verified owner decorator in mfa.py."""
    if sms_verified(request):
        return redirect('dashboard')
    form = SMSCodeForm()
    notice = ''
    error = ''
    now = timezone.now()
    if request.method == 'POST' and request.POST.get('action') == 'send':
        # Serialize per owner so concurrent browsers cannot bypass quotas.
        with transaction.atomic():
            User.objects.select_for_update().get(pk=request.user.pk)
            challenge, _ = OwnerSMSChallenge.objects.get_or_create(user=request.user)
            if challenge.sent_at and (now - challenge.sent_at).total_seconds() < 60:
                error = 'Please wait 60 seconds between code requests.'
            else:
                if not challenge.window_at or now - challenge.window_at >= timedelta(hours=1):
                    challenge.window_at, challenge.sends = now, 0
                if challenge.sends >= 10:
                    error = 'Hourly SMS limit reached. Please try again later.'
                else:
                    code = f'{secrets.randbelow(1000000):06d}'
                    binding = secrets.token_urlsafe(32)
                    nonce = secrets.token_hex(24)
                    challenge.nonce = nonce
                    challenge.binding = fingerprint(binding)
                    challenge.digest = fingerprint(f'{nonce}:{code}:{identity(request)}')
                    challenge.expires_at = now + timedelta(minutes=5)
                    challenge.sent_at, challenge.attempts = now, 0
                    challenge.sends += 1
                    challenge.accepted = False
                    challenge.save()
                    request.session['owner_sms_binding'] = binding
        if not error:
            try:
                send_sms(code)
            except SMSDeliveryError as failure:
                error = str(failure)
                AuditEvent.objects.create(actor=request.user, action='owner.sms_send_failed', object_reference=f'user:{request.user.pk}')
            else:
                # A later request must never be activated by an earlier response.
                OwnerSMSChallenge.objects.filter(user=request.user, nonce=nonce).update(accepted=True)
                AuditEvent.objects.create(actor=request.user, action='owner.sms_accepted', object_reference=f'user:{request.user.pk}')
                notice = 'SMS requested. Enter the code when it arrives. It expires after five minutes.'
    elif request.method == 'POST':
        form = SMSCodeForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                challenge = OwnerSMSChallenge.objects.select_for_update().filter(user=request.user).first()
                binding = fingerprint(request.session.get('owner_sms_binding', ''))
                eligible = (challenge and challenge.accepted and challenge.expires_at > now and
                    challenge.attempts < 5 and constant_time_compare(challenge.binding, binding))
                if eligible:
                    challenge.attempts += 1
                    valid = constant_time_compare(challenge.digest,
                        fingerprint(f"{challenge.nonce}:{form.cleaned_data['token']}:{identity(request)}"))
                    if valid:
                        challenge.accepted = False
                        challenge.digest = ''
                        request.session.cycle_key()
                        request.session['owner_sms_verified'] = identity(request)
                        request.session['owner_mfa_at'] = time.time()
                        request.session.pop('owner_sms_binding', None)
                        AuditEvent.objects.create(actor=request.user, action='owner.sms_verified', object_reference=f'user:{request.user.pk}')
                    challenge.save()
                    if valid:
                        return redirect('dashboard')
                form.add_error('token', 'Code not accepted. It may be expired, already used, or locked after five attempts. Request a new code if needed.')
    return render(request, 'registration/sms_security.html', {
        'form': form, 'notice': notice, 'error': error,
        'phone_suffix': settings.OWNER_SMS_PHONE[-4:],
    })
