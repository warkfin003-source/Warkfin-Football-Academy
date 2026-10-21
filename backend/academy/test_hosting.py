"""Configuration, mocked email transport and closed-launch routing regression tests."""
import json
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase, override_settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage
from urllib.error import HTTPError
from config.database import postgres_from_url
from .email_backend import BrevoEmailBackend, EmailDeliveryError

class DatabaseConfigurationTests(SimpleTestCase):
    def test_tls_connection_parsing(self):
        db=postgres_from_url('postgresql://demo:encoded%40password@db.example.test/academy?sslmode=require')
        self.assertEqual(db['PASSWORD'],'encoded@password');self.assertEqual(db['OPTIONS']['sslmode'],'require');self.assertTrue(db['DISABLE_SERVER_SIDE_CURSORS'])
    def test_invalid_or_insecure_configuration_fails_without_leaking_secret(self):
        for url in ['https://demo:secret@db.example.test/academy','postgresql://demo:secret@db.example.test/academy?sslmode=disable','postgresql://db.example.test/academy']:
            with self.assertRaises(ImproperlyConfigured) as error:postgres_from_url(url)
            self.assertNotIn('secret',str(error.exception))

@override_settings(BREVO_API_KEY='test-key-only',EMAIL_TIMEOUT=10)
class EmailTransportTests(SimpleTestCase):
    def message(self):return EmailMessage('Verify your account','Test body','academy@example.test',['player@example.test'])
    @patch('academy.email_backend.urlopen')
    def test_api_submission(self,open_url):
        response=MagicMock();response.status=201;open_url.return_value.__enter__.return_value=response
        self.assertEqual(BrevoEmailBackend().send_messages([self.message()]),1)
        request=open_url.call_args.args[0];self.assertEqual(request.full_url,'https://api.brevo.com/v3/smtp/email')
        self.assertEqual(json.loads(request.data)['to'],[{'email':'player@example.test'}])
    @patch('academy.email_backend.urlopen')
    def test_provider_failure_not_reported_as_success(self,open_url):
        open_url.side_effect=HTTPError('https://api.brevo.com',429,'quota',{},None)
        with self.assertRaises(EmailDeliveryError):BrevoEmailBackend().send_messages([self.message()])
        self.assertEqual(BrevoEmailBackend(fail_silently=True).send_messages([self.message()]),0)


@override_settings(PORTAL_ENABLED=False, ALLOWED_HOSTS=['testserver'])
class LaunchGateTests(SimpleTestCase):
    def test_private_routes_and_posts_remain_closed_without_database_access(self):
        for path in ['/', '/accounts/register/', '/accounts/login/', '/admin/', '/profile/']:
            for method in [self.client.get, self.client.post]:
                response = method(path)
                self.assertEqual(response.status_code, 503)
                self.assertContains(response, 'sign-in are not open yet', status_code=503)
                self.assertEqual(response['Cache-Control'], 'no-store')

    def test_health_remains_available(self):
        self.assertEqual(self.client.get('/health/').status_code, 200)


class SafeEmailDiagnosticsTests(SimpleTestCase):
    def test_provider_response_never_leaks_secrets(self):
        import io
        from .email_backend import provider_error
        error = HTTPError('https://api.brevo.com', 401, 'denied', {},
                          io.BytesIO(b'{"message":"unrecognized IP secret-api-key private-token"}'))
        message = str(provider_error(error))
        self.assertIn('IP authorization', message)
        self.assertNotIn('secret-api-key', message)
        self.assertNotIn('private-token', message)

    @override_settings(BREVO_API_KEY='Your private Brevo API key')
    @patch('academy.email_backend.urlopen')
    def test_placeholder_never_sent_to_provider(self, open_url):
        with self.assertRaises(EmailDeliveryError):
            BrevoEmailBackend().send_messages([EmailMessage('Test', 'Body', 'a@example.test', ['b@example.test'])])
        open_url.assert_not_called()

    def test_startup_is_opt_in_and_email_failure_does_not_stop_server(self):
        import importlib.util
        import os
        from pathlib import Path
        spec = importlib.util.spec_from_file_location('portal_gunicorn', Path(__file__).resolve().parents[1] / 'gunicorn.conf.py')
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        server = MagicMock()
        with patch.dict(os.environ, {'OWNER_INVITE_ON_START': '0'}), patch('django.setup') as setup:
            config.on_starting(server)
            setup.assert_not_called()
        with patch.dict(os.environ, {'OWNER_INVITE_ON_START': '1'}), patch('django.setup', side_effect=RuntimeError('private-secret')):
            config.on_starting(server)
        self.assertNotIn('private-secret', str(server.log.error.call_args))


from django.test import TestCase


@override_settings(OWNER_LOGIN_EMAIL='owner@example.test', OWNER_ACTIVATION_ENABLED=True)
class OwnerResendHookTests(TestCase):
    def test_replacement_request_is_consumed_by_success_audit(self):
        """Restarting after a successful replacement must not invalidate its link."""
        import importlib.util
        import os
        from datetime import timedelta
        from pathlib import Path
        from django.utils import timezone
        from academy.models import User, AuditEvent
        owner = User.objects.create(username='owner@example.test', email='owner@example.test', is_active=False)
        old = AuditEvent.objects.create(action='owner.invitation_sent', object_reference=f'user:{owner.pk}')
        cutoff = timezone.now()
        AuditEvent.objects.filter(pk=old.pk).update(created_at=cutoff - timedelta(hours=2))
        spec = importlib.util.spec_from_file_location('resend_gunicorn', Path(__file__).resolve().parents[1] / 'gunicorn.conf.py')
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        with patch.dict(os.environ, {'OWNER_INVITE_ON_START': '1', 'OWNER_INVITE_RESEND_AFTER': cutoff.isoformat()}), patch('django.setup'), patch('django.db.connections.close_all'), patch('django.core.management.call_command') as command:
            config.on_starting(MagicMock())
            command.assert_called_once_with('invite_owner', resend=True)
            AuditEvent.objects.create(action='owner.invitation_sent', object_reference=f'user:{owner.pk}')
            command.reset_mock()
            config.on_starting(MagicMock())
            command.assert_called_once_with('invite_owner', resend=False)
