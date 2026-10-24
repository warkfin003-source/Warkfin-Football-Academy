"""Exercise owner MFA through real views, sessions and TOTP verification."""
import time
from django.test import TestCase, override_settings, Client
from django.urls import reverse
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice
from .models import User, OwnerRecoveryCode
from .mfa import new_recovery_codes


@override_settings(PORTAL_ENABLED=True, OWNER_SETUP_ENABLED=False, OWNER_MFA_REQUIRED=True,
                   STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class OwnerMFATests(TestCase):
    def setUp(self):
        self.password = 'Owner!Private-Test938'
        self.owner = User.objects.create_superuser(username='owner@example.test', email='owner@example.test', password=self.password, email_verified=True)
        self.client.force_login(self.owner)

    def token(self, device):
        return f'{totp(device.bin_key, step=device.step, t0=device.t0, digits=device.digits):06d}'

    def test_password_only_owner_cannot_access_any_management_route(self):
        for path in ['/', '/admin/', '/owner/applications/1/', '/accounts/password_change/', '/coach/players/1/']:
            response = self.client.get(path)
            self.assertRedirects(response, reverse('owner-security'), fetch_redirect_response=False)

    def test_enrolment_requires_password_then_code_and_cannot_reset_existing_device(self):
        self.client.post(reverse('owner-security'), {'password': 'wrong'})
        self.assertFalse(TOTPDevice.objects.exists())
        self.client.post(reverse('owner-security'), {'password': self.password})
        device = TOTPDevice.objects.get(user=self.owner)
        self.assertFalse(device.confirmed)
        self.assertContains(self.client.get(reverse('owner-security')), 'data:image/svg+xml;base64,')
        response = self.client.post(reverse('owner-security'), {'token': self.token(device)})
        self.assertContains(response, 'Save these recovery codes privately')
        codes = response.context['codes']
        self.assertEqual(len(codes), 8)
        self.assertFalse(OwnerRecoveryCode.objects.filter(digest__in=codes).exists())
        device.refresh_from_db()
        self.assertTrue(device.confirmed)
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.client.logout(); self.client.force_login(self.owner)
        self.assertRedirects(self.client.post(reverse('owner-security'), {'password': self.password}), reverse('owner-otp'), fetch_redirect_response=False)
        device.refresh_from_db(); self.assertTrue(device.confirmed)

    def test_totp_cannot_be_reused_and_wrong_code_cannot_verify(self):
        device = TOTPDevice.objects.create(user=self.owner, confirmed=True)
        token = self.token(device)
        self.client.post(reverse('owner-otp'), {'token': token})
        self.assertEqual(self.client.get('/').status_code, 200)
        self.client.logout(); self.client.force_login(self.owner)
        self.client.post(reverse('owner-otp'), {'token': token})
        self.assertRedirects(self.client.get('/'), reverse('owner-otp'), fetch_redirect_response=False)

    def test_recovery_code_is_single_use_and_session_expires(self):
        TOTPDevice.objects.create(user=self.owner, confirmed=True)
        code = new_recovery_codes(self.owner)[0]
        self.client.post(reverse('owner-recovery'), {'code': code})
        self.assertEqual(self.client.get('/').status_code, 200)
        session = self.client.session; session['owner_mfa_at'] = time.time() - 7201; session.save()
        self.assertRedirects(self.client.get('/'), reverse('owner-otp'), fetch_redirect_response=False)
        self.client.post(reverse('owner-recovery'), {'code': code})
        self.assertRedirects(self.client.get('/'), reverse('owner-otp'), fetch_redirect_response=False)
        self.assertEqual(OwnerRecoveryCode.objects.count(), 7)

    def test_players_cannot_enrol_owner_devices(self):
        player = User.objects.create_user(username='player@example.test', email='player@example.test', password='Player!Private938')
        self.client.force_login(player)
        self.assertEqual(self.client.post(reverse('owner-security'), {'password': 'Player!Private938'}).status_code, 403)
        self.assertFalse(TOTPDevice.objects.exists())

    def test_enrolment_requires_csrf(self):
        client = Client(enforce_csrf_checks=True); client.force_login(self.owner)
        self.assertEqual(client.post(reverse('owner-security'), {'password': self.password}).status_code, 403)

    @override_settings(PORTAL_ENABLED=False, OWNER_SETUP_ENABLED=True)
    def test_closed_launch_allows_only_owner_setup_and_management(self):
        self.assertEqual(self.client.get(reverse('owner-security')).status_code, 200)
        anon = Client()
        self.assertEqual(anon.get(reverse('login')).status_code, 200)
        self.assertEqual(anon.post(reverse('signup'), {}).status_code, 503)
        player = User.objects.create_user(username='player2@example.test', email='player2@example.test')
        anon.force_login(player)
        self.assertEqual(anon.get('/').status_code, 503)

    def test_device_deletion_revokes_verified_session(self):
        device = TOTPDevice.objects.create(user=self.owner, confirmed=True)
        self.client.post(reverse('owner-otp'), {'token': self.token(device)})
        device.delete()
        self.assertRedirects(self.client.get('/'), reverse('owner-security'), fetch_redirect_response=False)
