"""Declined users cannot reuse sessions; only verified gateway evidence credits orders."""
import hashlib
import hmac
import json
from unittest.mock import patch
from django.conf import settings
from django.test import TestCase, override_settings, Client
from django.utils import timezone
from .models import User, Application, Player, PaymentOrder, TransferClaim
from . import payments, paystack

STORAGE={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}}

@override_settings(OWNER_MFA_REQUIRED=False, STORAGES=STORAGE)
class AccessTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='closed@test.local',email='closed@test.local',password='Testing!123456',email_verified=True)
        self.application=Application.objects.create(user=self.user,full_name='Closed User',date_of_birth='2000-01-01',status='pending')
    def test_old_decline_closes_existing_session_and_fresh_login(self):
        self.client.force_login(self.user)
        self.application.status='declined';self.application.save()
        response=self.client.get('/')
        self.assertEqual(response.status_code,403)
        self.assertContains(response,'Portal access closed',status_code=403)
        self.assertNotIn('_auth_user_id',self.client.session)
        response=self.client.post('/accounts/login/',{'username':self.user.email,'password':'Testing!123456'})
        self.assertContains(response,'Portal access is closed')
        self.assertNotIn('_auth_user_id',self.client.session)
    def test_suspended_player_blocked_and_owner_exempt(self):
        Player.objects.create(user=self.user,directory_number=1,display_name='Closed',positions='CM',active=False)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post('/payments/checkout/',{'purpose':'registration'}).status_code,403)
        self.user.is_superuser=True;self.user.is_staff=True;self.user.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/').status_code,200)
    def test_pending_and_correction_not_blocked_and_refunds_preserved(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/').status_code,200)
        self.application.status='correction';self.application.save()
        self.assertEqual(self.client.get('/').status_code,200)
        owner=User.objects.create_superuser(username='owner@test.local',email='owner@test.local',email_verified=True)
        order=PaymentOrder.objects.create(user=self.user,purpose='registration',amount_kobo=500000,status='paid')
        self.client.force_login(owner)
        self.client.post(f'/owner/applications/{self.application.pk}/',{'decision':'declined'})
        self.assertTrue(hasattr(PaymentOrder.objects.get(pk=order.pk),'refund'))
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/payments/').status_code,403)

@override_settings(OWNER_MFA_REQUIRED=False,STORAGES=STORAGE,PAYSTACK_ENABLED=True,PAYSTACK_MODE='live',PAYSTACK_SECRET_KEY='sk_live_isolated_test_secret_123456',PAYMENT_TERMS='Test terms',PALMPAY_ENABLED=False)
class PaystackTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='payer@test.local',email='payer@test.local',email_verified=True)
        self.client.force_login(self.user)
        self.order=payments.make_order(self.user,'registration')
    def result(self,**changes):
        return dict(reference=self.order.reference.hex,currency='NGN',amount=500000,domain='live',customer={'email':self.user.email},status='success',id=12345,**changes)
    def initialized(self):
        self.order.checkout_url='https://checkout.paystack.com/test-code';self.order.save()
    def test_buttons_and_server_pricing_verified_host(self):
        self.assertContains(self.client.get('/payments/'),'Pay registration online with Paystack')
        with patch('academy.paystack.api',return_value={'reference':self.order.reference.hex,'authorization_url':'https://checkout.paystack.com/test-code'}) as api:
            r=self.client.post('/payments/checkout/',{'purpose':'registration','terms':'yes','amount':1})
            self.assertEqual(r.status_code,302)
            self.assertEqual(r['Location'],'https://checkout.paystack.com/test-code')
            self.assertEqual(api.call_args.args[1]['amount'],500000)
            self.assertIn('https://checkout.paystack.com',r['Content-Security-Policy'])
        self.order.refresh_from_db();self.assertFalse(payments.registration_paid(self.user))
    def test_initialize_rejects_untrusted_host(self):
        with patch('academy.paystack.api',return_value={'reference':self.order.reference.hex,'authorization_url':'https://evil.test/checkout'}):
            with self.assertRaises(payments.PaymentUnavailable): payments.start_checkout(self.order)
    def test_success_idempotency_mismatches_and_pending(self):
        self.initialized()
        data=self.result()
        for key,value in [('amount',1),('currency','USD'),('domain','test'),('reference','wrong'),('customer',{'email':'other@test.local'})]:
            with patch('academy.paystack.api',return_value={**data,key:value}):
                with self.assertRaises(ValueError): paystack.reconcile(self.order)
        with patch('academy.paystack.api',return_value={**data,'status':'pending'}): paystack.reconcile(self.order)
        self.order.refresh_from_db();self.assertEqual(self.order.status,'pending')
        with patch('academy.paystack.api',return_value=data):
            payments.reconcile(self.order);payments.reconcile(self.order)
        self.order.refresh_from_db();self.assertEqual(self.order.provider_reference,'paystack:12345')
        self.assertTrue(payments.registration_paid(self.user))
    def test_webhook_signature_independent_verify_and_replay(self):
        self.initialized();body=json.dumps({'event':'charge.success','data':{'reference':self.order.reference.hex}}).encode()
        client=Client(enforce_csrf_checks=True)
        with patch('academy.paystack.api',return_value=self.result()) as api:
            self.assertEqual(client.post('/payments/paystack/notify/',body,content_type='application/json').status_code,403)
            api.assert_not_called()
            signature=hmac.new(settings.PAYSTACK_SECRET_KEY.encode(),body,hashlib.sha512).hexdigest()
            for _ in range(2): self.assertEqual(client.post('/payments/paystack/notify/',body,content_type='application/json',HTTP_X_PAYSTACK_SIGNATURE=signature).status_code,200)
        self.order.refresh_from_db();self.assertEqual(self.order.status,'paid')
    def test_manual_report_and_unsigned_return_do_not_credit(self):
        TransferClaim.objects.create(order=self.order,sender_name='Sender',reported_reference='report',transfer_date=timezone.localdate(),destination='Test',accepted_terms='Test')
        with patch('academy.paystack.api') as api:
            with self.assertRaises(payments.PaymentUnavailable):payments.start_checkout(self.order)
            self.client.get('/payments/paystack/return/?reference='+self.order.reference.hex)
            api.assert_not_called()
        self.order.refresh_from_db();self.assertEqual(self.order.status,'pending')
    @override_settings(PAYSTACK_SECRET_KEY='')
    def test_missing_secret_is_visible_and_never_calls_api(self):
        self.assertContains(self.client.get('/payments/'),'Pay online with Paystack — activation pending')
        with patch('academy.paystack.api') as api:
            self.client.post('/payments/checkout/',{'purpose':'registration','terms':'yes'})
            api.assert_not_called()

    @override_settings(DEBUG=False,PAYSTACK_MODE='test',PAYSTACK_SECRET_KEY='sk_test_isolated_test_secret_123456')
    def test_test_key_cannot_activate_production_collections(self):
        self.assertFalse(paystack.ready())

    def test_late_confirmed_payment_after_decline_retains_refund_obligation(self):
        self.initialized()
        Application.objects.create(user=self.user,full_name='Declined',date_of_birth='2000-01-01',status='declined')
        with patch('academy.paystack.api',return_value=self.result()): paystack.reconcile(self.order)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status,'paid')
        self.assertTrue(hasattr(self.order,'refund'))

    def test_online_checkout_remains_csrf_protected(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        with patch('academy.paystack.api') as api:
            self.assertEqual(client.post('/payments/checkout/',{'purpose':'registration','terms':'yes'}).status_code,403)
            api.assert_not_called()
