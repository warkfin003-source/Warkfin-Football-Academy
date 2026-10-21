"""Owner authenticator enrolment, replay-safe verification and private recovery.

The maintained django-otp library handles TOTP, replay detection and throttling.
Every verification locks the device; recovery codes are random, hashed and used
once. No external QR service receives the authenticator secret.
"""
import base64
import hashlib
import io
import secrets
import time
from functools import wraps

import django_otp
import qrcode
import qrcode.image.svg
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from django_otp.plugins.otp_totp.models import TOTPDevice
from .models import User, AuditEvent, OwnerRecoveryCode


class SecurityForm(forms.Form):
    password = forms.CharField(label='Current password', widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))


class TokenForm(forms.Form):
    token = forms.RegexField(regex=r'^\d{6}$', label='Six-digit authenticator code', widget=forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'one-time-code', 'maxlength': '6'}))


class RecoveryForm(forms.Form):
    code = forms.CharField(label='Recovery code', max_length=100, widget=forms.TextInput(attrs={'autocomplete': 'off'}))


def owner_verified(request):
    """Only a verified device in this session grants owner privileges."""
    if not settings.OWNER_MFA_REQUIRED:
        return True
    return bool(request.user.is_authenticated and request.user.is_verified() and
                0 <= time.time() - request.session.get('owner_mfa_at', 0) < settings.OWNER_MFA_MAX_AGE)


class OwnerMFAMiddleware:
    """Protect all owner routes, including admin and password/email changes."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.is_superuser and not owner_verified(request):
            allowed = request.path in {'/accounts/login/', '/accounts/logout/', '/health/'} or request.path.startswith('/accounts/security/')
            if not allowed:
                return redirect('owner-otp' if TOTPDevice.objects.filter(user=request.user, confirmed=True).exists() else 'owner-security')
        return self.get_response(request)


def owner_only(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_active or not request.user.is_superuser or not request.user.email_verified:
            return HttpResponseForbidden('Verified owner access required.')
        return view(request, *args, **kwargs)
    return wrapped


def verified_session(request, device):
    request.session.cycle_key()
    django_otp.login(request, device)
    request.session['owner_mfa_at'] = time.time()


def new_recovery_codes(user):
    """Only the current response contains plaintext; the database has digests."""
    codes = [secrets.token_hex(12) for _ in range(8)]
    OwnerRecoveryCode.objects.filter(user=user).delete()
    OwnerRecoveryCode.objects.bulk_create([
        OwnerRecoveryCode(user=user, digest=hashlib.sha256(code.encode()).hexdigest()) for code in codes
    ])
    return codes


def recovery_page(request, codes):
    return render(request, 'registration/security.html', {'stage': 'codes', 'codes': codes})


@owner_only
@require_http_methods(['GET', 'POST'])
def security(request):
    """Initial enrolment requires the password and proof from the new device."""
    confirmed = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
    if confirmed:
        if not owner_verified(request):
            return redirect('owner-otp')
        form = SecurityForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            if not request.user.check_password(form.cleaned_data['password']):
                form.add_error('password', 'The password was not accepted.')
            else:
                with transaction.atomic():
                    User.objects.select_for_update().get(pk=request.user.pk)
                    codes = new_recovery_codes(request.user)
                    AuditEvent.objects.create(actor=request.user, action='owner.recovery_codes_rotated', object_reference=f'user:{request.user.pk}')
                return recovery_page(request, codes)
        return render(request, 'registration/security.html', {'stage': 'enabled', 'form': form})

    # The pending secret is bound to the enrolling browser and expires promptly.
    device_id = request.session.get('owner_setup_device')
    setup_age = time.time() - request.session.get('owner_setup_at', 0)
    device = TOTPDevice.objects.filter(pk=device_id, user=request.user, confirmed=False).first() if 0 <= setup_age < settings.OWNER_MFA_SETUP_MAX_AGE else None
    if device:
        form = TokenForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            with transaction.atomic():
                User.objects.select_for_update().get(pk=request.user.pk)
                locked = TOTPDevice.objects.select_for_update().get(pk=device.pk)
                if locked.confirmed or TOTPDevice.objects.filter(user=request.user, confirmed=True).exists():
                    return redirect('owner-otp')
                if locked.verify_token(form.cleaned_data['token']):
                    locked.confirmed = True
                    locked.save(update_fields=['confirmed'])
                    codes = new_recovery_codes(request.user)
                    AuditEvent.objects.create(actor=request.user, action='owner.mfa_enabled', object_reference=f'user:{request.user.pk}')
                    verified_session(request, locked)
                    request.session.pop('owner_setup_device', None)
                    request.session.pop('owner_setup_at', None)
                    return recovery_page(request, codes)
                form.add_error('token', 'Code not accepted. Wait for a new code and try again.')
        output = io.BytesIO()
        qrcode.make(device.config_url, image_factory=qrcode.image.svg.SvgPathImage).save(output)
        # SVG is encoded as an image data URI, never inserted as untrusted markup.
        qr = base64.b64encode(output.getvalue()).decode()
        key = base64.b32encode(device.bin_key).decode()
        return render(request, 'registration/security.html', {'stage': 'scan', 'form': form, 'qr': qr, 'setup_key': key})

    form = SecurityForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if not request.user.check_password(form.cleaned_data['password']):
            form.add_error('password', 'The password was not accepted.')
        else:
            with transaction.atomic():
                User.objects.select_for_update().get(pk=request.user.pk)
                if TOTPDevice.objects.filter(user=request.user, confirmed=True).exists():
                    return redirect('owner-otp')
                TOTPDevice.objects.filter(user=request.user, confirmed=False).delete()
                device = TOTPDevice.objects.create(user=request.user, name='Owner authenticator', confirmed=False)
                request.session['owner_setup_device'] = device.pk
                request.session['owner_setup_at'] = time.time()
            return redirect('owner-security')
    return render(request, 'registration/security.html', {'stage': 'start', 'form': form})


@owner_only
@require_http_methods(['GET', 'POST'])
def verify(request):
    if owner_verified(request):
        return redirect('dashboard')
    device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
    if not device:
        return redirect('owner-security')
    form = TokenForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            locked = TOTPDevice.objects.select_for_update().get(pk=device.pk)
            if locked.verify_token(form.cleaned_data['token']):
                verified_session(request, locked)
                return redirect('dashboard')
        form.add_error('token', 'Code not accepted. Wait for a new code and try again.')
    return render(request, 'registration/security.html', {'stage': 'verify', 'form': form})


@owner_only
@require_http_methods(['GET', 'POST'])
def recovery(request):
    """A recovery code supplements a valid password; it never replaces it."""
    device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
    if not device:
        return redirect('owner-security')
    form = RecoveryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        digest = hashlib.sha256(form.cleaned_data['code'].strip().encode()).hexdigest()
        with transaction.atomic():
            User.objects.select_for_update().get(pk=request.user.pk)
            code = OwnerRecoveryCode.objects.select_for_update().filter(user=request.user, digest=digest).first()
            if code:
                code.delete()
                verified_session(request, device)
                AuditEvent.objects.create(actor=request.user, action='owner.recovery_code_used', object_reference=f'user:{request.user.pk}')
                messages.warning(request, 'Recovery code used. Keep your remaining codes safe. Contact support if you lost your authenticator.')
                return redirect('dashboard')
        form.add_error('code', 'Recovery code not accepted.')
    return render(request, 'registration/security.html', {'stage': 'recovery', 'form': form})
