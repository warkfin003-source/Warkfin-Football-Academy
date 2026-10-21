"""Owner activation tests covering expiry, replay, CSRF, delivery failure and privilege isolation."""
import io
import re
from datetime import datetime, timedelta
from unittest.mock import patch
from django.core import mail
from django.core.management import call_command, CommandError
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from .models import User
from .owner_activation import owner_token


@override_settings(OWNER_LOGIN_EMAIL='owner@example.test', OWNER_ACTIVATION_ENABLED=True,
                   PORTAL_ENABLED=False, EMAIL_READY=True, DEFAULT_FROM_EMAIL='academy@example.test', EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   PORTAL_ORIGIN='https://testserver', ALLOWED_HOSTS=['testserver'])
class OwnerActivationTests(TestCase):
    def invite(self, **kwargs):
        output = io.StringIO()
        call_command('invite_owner', stdout=output, **kwargs)
        self.assertNotIn('https://', output.getvalue())
        return re.search(r'https://testserver(\S+)', mail.outbox[-1].body).group(1)

    def test_private_link_activates_once_without_opening_portal(self):
        url = self.invite()
        user = User.objects.get(email='owner@example.test')
        self.assertFalse(user.is_active)
        self.assertFalse(user.email_verified)
        self.assertFalse(user.has_usable_password())
        self.assertFalse(self.client.login(username=user.email, password='anything'))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        form_url = response['Location']
        self.assertTrue(form_url.endswith('/set-password/'))
        response = self.client.post(form_url, {'new_password1': 'A-private-owner-Pass!2026', 'new_password2': 'A-private-owner-Pass!2026'})
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_active and user.email_verified and user.check_password('A-private-owner-Pass!2026'))
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(self.client.get(url), 'already used')
        self.assertEqual(self.client.get('/admin/').status_code, 503)
        self.assertEqual(self.client.get('/accounts/register/').status_code, 503)

    def test_invalid_token_and_expired_token_fail(self):
        url = self.invite()
        self.assertContains(self.client.get(url.rstrip('/')+'tampered/'), 'invalid')
        with patch.object(owner_token, '_now', return_value=datetime.now()+timedelta(hours=2)):
            self.assertContains(self.client.get(url), 'expired')
        self.assertFalse(User.objects.get(email='owner@example.test').is_active)

    def test_resend_invalidates_old_link_and_no_duplicate_by_default(self):
        old = self.invite()
        self.invite()
        self.assertEqual(len(mail.outbox), 1)
        new = self.invite(resend=True)
        self.assertNotEqual(old, new)
        self.assertContains(self.client.get(old), 'invalid')
        self.assertEqual(self.client.get(new).status_code, 302)

    def test_existing_applicant_is_never_promoted(self):
        user = User.objects.create_user(username='owner@example.test', email='owner@example.test', password='Existing-private-pass!')
        with self.assertRaises(CommandError):
            call_command('invite_owner')
        user.refresh_from_db()
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password('Existing-private-pass!'))

    def test_csrf_and_password_validation(self):
        url = self.invite()
        client = Client(enforce_csrf_checks=True)
        response = client.get(url)
        form_url = response['Location']
        self.assertEqual(client.post(form_url, {'new_password1': 'test', 'new_password2': 'test'}).status_code, 403)
        self.client.get(url)
        response = self.client.post(form_url, {'new_password1': 'short', 'new_password2': 'short'})
        self.assertContains(response, 'too short')
        self.assertFalse(User.objects.get(email='owner@example.test').is_active)

    @patch('academy.management.commands.invite_owner.send_mail', side_effect=RuntimeError('provider unavailable'))
    def test_failed_delivery_does_not_leave_active_owner(self, send):
        with self.assertRaises(CommandError):
            call_command('invite_owner')
        self.assertFalse(User.objects.filter(is_active=True).exists())

    def test_regular_password_reset_token_cannot_activate_owner(self):
        from django.contrib.auth.tokens import default_token_generator
        self.invite()
        user = User.objects.get(email='owner@example.test')
        url = reverse('owner-activate', kwargs={'uidb64': urlsafe_base64_encode(force_bytes(user.pk)), 'token': default_token_generator.make_token(user)})
        self.assertContains(self.client.get(url), 'invalid')

    @override_settings(OWNER_ACTIVATION_ENABLED=False)
    def test_activation_disabled_by_default(self):
        self.assertEqual(self.client.get('/accounts/owner-activate/anything/anything/').status_code, 503)
        with self.assertRaises(CommandError):
            call_command('invite_owner')
