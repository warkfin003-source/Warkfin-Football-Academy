"""Security regression tests use mocked delivery; no real SMS or billing in tests."""
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings, Client
from django.utils import timezone
from .models import User, OwnerSMSChallenge
from .sms_mfa import SMSDeliveryError

@override_settings(PORTAL_ENABLED=True, OWNER_MFA_METHOD='sms', OWNER_MFA_REQUIRED=True,
    OWNER_SMS_PHONE='+2348166017588',
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class SMSMFATests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser(username='owner@sms.test', email='owner@sms.test', password='Private!12345-test', email_verified=True)
        self.client.force_login(self.owner)
        self.path = '/accounts/security/'

    def send(self):
        with patch('academy.sms_mfa.send_sms') as delivery:
            response = self.client.post(self.path, {'action': 'send', 'recipient': '+10000000000'})
            self.assertEqual(response.status_code, 200)
            return delivery.call_args.args[0]

    def test_sms_success_blocks_password_only_and_does_not_expose_code(self):
        self.assertEqual(self.client.get('/admin/').status_code, 302)
        code = self.send()
        challenge = OwnerSMSChallenge.objects.get(user=self.owner)
        self.assertNotEqual(code, challenge.digest)
        page = self.client.get(self.path)
        self.assertContains(page, '7588')
        self.assertNotContains(page, '+2348166017588')
        response = self.client.post(self.path, {'token': code})
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.assertFalse(OwnerSMSChallenge.objects.get(user=self.owner).accepted)
        self.client.logout(); self.client.force_login(self.owner)
        self.assertContains(self.client.post(self.path, {'token': code}), 'Code not accepted')
        self.assertEqual(self.client.get('/admin/').status_code, 302)

    def test_expired_and_wrong_browser_codes_are_rejected(self):
        code = self.send()
        other = Client(); other.force_login(self.owner)
        self.assertContains(other.post(self.path, {'token': code}), 'Code not accepted')
        OwnerSMSChallenge.objects.filter(user=self.owner).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertContains(self.client.post(self.path, {'token': code}), 'Code not accepted')

    def test_five_failures_lock_correct_code(self):
        code = self.send()
        wrong = '000000' if code != '000000' else '111111'
        for _ in range(5):
            self.client.post(self.path, {'token': wrong})
        self.assertContains(self.client.post(self.path, {'token': code}), 'Code not accepted')

    def test_cooldown_hourly_limit_and_provider_failure(self):
        with patch('academy.sms_mfa.send_sms', side_effect=SMSDeliveryError('Unavailable')) as delivery:
            self.assertContains(self.client.post(self.path, {'action': 'send'}), 'Unavailable')
            self.assertFalse(OwnerSMSChallenge.objects.get(user=self.owner).accepted)
            self.assertContains(self.client.post(self.path, {'action': 'send'}), '60 seconds')
            self.assertEqual(delivery.call_count, 1)
        OwnerSMSChallenge.objects.filter(user=self.owner).update(sent_at=timezone.now()-timedelta(seconds=61), sends=10)
        with patch('academy.sms_mfa.send_sms') as delivery:
            self.assertContains(self.client.post(self.path, {'action': 'send'}), 'Hourly verification-code limit')
            delivery.assert_not_called()

    def test_new_code_invalidates_old_and_phone_change_revokes_session(self):
        old = self.send()
        OwnerSMSChallenge.objects.filter(user=self.owner).update(sent_at=timezone.now()-timedelta(seconds=61))
        new = self.send()
        self.assertContains(self.client.post(self.path, {'token': old}), 'Code not accepted')
        self.client.post(self.path, {'token': new})
        with override_settings(OWNER_SMS_PHONE='+2348000000000'):
            self.assertEqual(self.client.get('/admin/').status_code, 302)

    def test_player_csrf_and_recovery_cannot_bypass_sms(self):
        client = Client(enforce_csrf_checks=True); client.force_login(self.owner)
        self.assertEqual(client.post(self.path, {'action': 'send'}).status_code, 403)
        self.assertRedirects(self.client.get('/accounts/security/recovery/'), self.path, fetch_redirect_response=False)
        player = User.objects.create_user(username='player@sms.test', email='player@sms.test', password='test-private', email_verified=True)
        self.client.force_login(player)
        self.assertEqual(self.client.get(self.path).status_code, 403)

    def test_confirmation_survives_refresh_without_claiming_delivery(self):
        self.send()
        page = self.client.get(self.path)
        self.assertContains(page, 'SMS accepted for sending')
        self.assertContains(page, 'Delivery to your phone has not yet been confirmed.')
        self.assertContains(page, 'data-cooldown=')

    def test_provider_diagnostics_do_not_echo_response_secrets(self):
        from io import BytesIO
        from urllib.error import HTTPError
        from .sms_mfa import provider_failure
        error = HTTPError('https://api.brevo.com', 403, 'Denied', {}, BytesIO(b'{"message":"unauthorized IP with private-key-123"}'))
        reason, advice = provider_failure(error)
        self.assertEqual(reason, 'server_ip_not_authorized')
        self.assertNotIn('private-key', advice)

    def test_email_uses_verified_account_and_shared_verification(self):
        with patch('academy.sms_mfa.send_mail', return_value=1) as delivery:
            self.client.post(self.path, {'action': 'send', 'channel': 'email', 'email': 'stranger@example.test'})
        self.assertEqual(delivery.call_args.args[3], [self.owner.email])
        import re
        code = re.search(r'\b\d{6}\b', delivery.call_args.args[1]).group()
        self.assertContains(self.client.get(self.path), 'Email accepted for sending')
        response = self.client.post(self.path, {'token': code})
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.client.logout(); self.client.force_login(self.owner)
        self.assertContains(self.client.post(self.path, {'token': code}), 'Code not accepted')

    def test_switching_to_email_invalidates_previous_sms(self):
        old = self.send()
        OwnerSMSChallenge.objects.filter(user=self.owner).update(sent_at=timezone.now()-timedelta(seconds=61))
        with patch('academy.sms_mfa.send_email_code') as delivery:
            self.client.post(self.path, {'action': 'send', 'channel': 'email'})
            code = delivery.call_args.args[1]
        self.assertContains(self.client.post(self.path, {'token': old}), 'Code not accepted')
        self.assertRedirects(self.client.post(self.path, {'token': code}), '/', fetch_redirect_response=False)

    def test_email_failure_does_not_activate_challenge(self):
        from .email_backend import EmailDeliveryError
        with patch('academy.sms_mfa.send_mail', side_effect=EmailDeliveryError('Email not accepted')):
            self.assertContains(self.client.post(self.path, {'action': 'send', 'channel': 'email'}), 'Email not accepted')
        self.assertFalse(OwnerSMSChallenge.objects.get(user=self.owner).accepted)
