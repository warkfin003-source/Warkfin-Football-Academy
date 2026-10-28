"""An acceptance letter requires admission approval and verified registration payment."""
from datetime import date
from django.test import TestCase, override_settings
from .models import User, Application, PaymentOrder

@override_settings(OWNER_MFA_REQUIRED=False, STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'}, 'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class AcceptanceLetterTests(TestCase):
    def test_letter_requires_approval_payment_and_account_ownership(self):
        user = User.objects.create_user(username='letter@test.local', email='letter@test.local', email_verified=True)
        other = User.objects.create_user(username='other-letter@test.local', email='other-letter@test.local', email_verified=True)
        app = Application.objects.create(user=user, full_name='Test Player', date_of_birth=date(2000,1,1), status='pending')
        order = PaymentOrder.objects.create(user=user, purpose='registration', amount_kobo=500000, status='paid', provider_reference='letter-payment')
        self.client.force_login(user)
        self.assertEqual(self.client.get('/acceptance/').status_code,404)
        app.status='approved';app.save()
        order.status='pending';order.save()
        self.assertEqual(self.client.get('/acceptance/').status_code,403)
        order.status='paid';order.save()
        response=self.client.get('/acceptance/')
        self.assertContains(response,'Acceptance Letter')
        self.assertContains(response,'Dear Test Player')
        self.assertContains(response,'Print / Save Acceptance Letter')
        self.client.force_login(other)
        self.assertEqual(self.client.get('/acceptance/').status_code,404)
