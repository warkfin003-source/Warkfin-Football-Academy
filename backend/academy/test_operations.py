"""Maintenance cannot erase live sessions or bypass owner/CSRF protections."""
from datetime import timedelta
from django.contrib.sessions.models import Session
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from .models import User, RateBucket, PaymentOrder, AuditEvent

@override_settings(OWNER_MFA_REQUIRED=False, STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class OperationsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser(username='owner@test.local', email='owner@test.local', password='Testing!123456', email_verified=True)
        self.member = User.objects.create_user(username='member@test.local', email='member@test.local', email_verified=True)
        now = timezone.now()
        for key, expires in [('expired', now-timedelta(days=1)), ('active', now+timedelta(days=1))]:
            RateBucket.objects.create(key=key, count=1, expires_at=expires)
            Session.objects.create(session_key=key, session_data='', expire_date=expires)
        self.payment = PaymentOrder.objects.create(user=self.member, purpose='registration', amount_kobo=500000, status='paid', provider_reference='preserve-payment')

    def test_owner_only_and_get_never_cleans(self):
        self.assertEqual(self.client.get('/owner/operations/').status_code, 302)
        self.client.force_login(self.member)
        for method in [self.client.get, self.client.post]:
            self.assertEqual(method('/owner/operations/').status_code, 403)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get('/owner/operations/'), 'Recurring durable backups are not configured')
        self.assertTrue(Session.objects.filter(pk='expired').exists())

    def test_cleanup_preserves_active_and_financial_records(self):
        self.client.force_login(self.owner)
        self.client.post('/owner/operations/', {'action': 'cleanup'})
        self.assertTrue(RateBucket.objects.filter(pk='expired').exists())
        response = self.client.post('/owner/operations/', {'action': 'cleanup', 'confirmed': 'yes'}, follow=True)
        self.assertContains(response, 'Cleanup complete: 1 expired counters and 1 expired sessions removed.')
        self.assertFalse(Session.objects.filter(pk='expired').exists())
        self.assertFalse(RateBucket.objects.filter(pk='expired').exists())
        self.assertTrue(Session.objects.filter(pk='active').exists())
        self.assertTrue(RateBucket.objects.filter(pk='active').exists())
        self.assertTrue(PaymentOrder.objects.filter(pk=self.payment.pk, status='paid').exists())
        self.assertTrue(AuditEvent.objects.filter(actor=self.owner, action='maintenance.expired_records_removed').exists())

    def test_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post('/owner/operations/', {'action':'cleanup','confirmed':'yes'}).status_code, 403)
        self.assertTrue(Session.objects.filter(pk='expired').exists())
