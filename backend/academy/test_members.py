"""Payment integrity and isolation regression tests; all provider calls are mocked."""
from datetime import date, timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone
from .models import User, Player, Squad, Application, PaymentOrder, DuesMonth, AcademyEvent, NotificationRead
from . import payments

@override_settings(OWNER_MFA_REQUIRED=False, PALMPAY_ENABLED=False,
 STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class MemberTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='member@test.local',email='member@test.local',email_verified=True)
        self.other=User.objects.create_user(username='other@test.local',email='other@test.local',email_verified=True)
        self.client.force_login(self.user)
    def paid_data(self,order,**changes):
        data={'orderId':order.reference.hex,'currency':'NGN','amount':order.amount_kobo,'orderNo':'provider-123','orderStatus':2}
        data.update(changes);return data
    def test_registration_price_and_pending_reuse(self):
        order=payments.make_order(self.user,'registration')
        self.assertEqual(order.amount_kobo,500000)
        self.assertEqual(payments.make_order(self.user,'registration').pk,order.pk)
    def test_disabled_gateway_cannot_charge(self):
        response=self.client.post('/payments/checkout/',{'purpose':'registration','amount':1,'terms':'yes'})
        self.assertEqual(response.status_code,302);self.assertFalse(PaymentOrder.objects.exists())
    def test_amount_currency_reference_mismatches_never_settle(self):
        order=payments.make_order(self.user,'registration')
        for change in [{'amount':1},{'currency':'USD'},{'orderId':'someone-else'},{'amount':True},{'orderNo':''}]:
            with self.assertRaises(ValueError):payments.settle(order,self.paid_data(order,**change))
        order.refresh_from_db();self.assertEqual(order.status,'pending')
    def test_duplicate_success_idempotent_and_receipt_private(self):
        order=payments.make_order(self.user,'registration')
        payments.settle(order,self.paid_data(order));payments.settle(order,self.paid_data(order))
        self.assertTrue(payments.registration_paid(self.user))
        self.assertEqual(self.client.get(f'/payments/{order.pk}/receipt/').status_code,200)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f'/payments/{order.pk}/receipt/').status_code,404)
        self.assertEqual(self.client.post(f'/payments/{order.pk}/check/').status_code,404)
    def test_pending_receipt_unavailable_and_no_fake_acceptance(self):
        order=payments.make_order(self.user,'registration')
        self.assertEqual(self.client.get(f'/payments/{order.pk}/receipt/').status_code,404)
        self.assertEqual(self.client.get('/acceptance/').status_code,404)
    def test_dues_cross_year_and_overlap(self):
        order=payments.make_order(self.user,'dues',date(2026,11,1),3)
        self.assertEqual(order.amount_kobo,900000)
        payments.settle(order,self.paid_data(order));payments.settle(order,self.paid_data(order))
        self.assertEqual(list(DuesMonth.objects.values_list('month',flat=True)),[date(2026,11,1),date(2026,12,1),date(2027,1,1)])
        with self.assertRaises(ValueError):payments.make_order(self.user,'dues',date(2027,1,1),1)
    def test_invalid_dues_period(self):
        for months in [0,-1,2,13,999]:
            with self.assertRaises(ValueError):payments.make_order(self.user,'dues',date(2026,11,1),months)
    def test_monthly_slip_scoped_to_payment(self):
        order=payments.make_order(self.user,'dues',date(2026,11,1),1)
        payments.settle(order,self.paid_data(order));month=DuesMonth.objects.get()
        self.assertContains(self.client.get(f'/payments/{order.pk}/receipt/?month={month.pk}'),'November 2026')
        self.assertEqual(self.client.get(f'/payments/{order.pk}/receipt/?month=999').status_code,404)
    def test_webhook_invalid_signature_rejected(self):
        with patch('academy.payments.ready',return_value=True):
            with override_settings(PALMPAY_APP_ID='academy'):
                response=self.client.post('/payments/palmpay/notify/',data='{"appId":"academy","sign":"forged"}',content_type='application/json')
        self.assertEqual(response.status_code,403)
    def test_webhook_requeries_after_signature(self):
        order=payments.make_order(self.user,'registration')
        with patch('academy.payments.ready',return_value=True),patch('academy.payments.verify_signature',return_value=True),patch('academy.payments.provider_request',return_value=self.paid_data(order)) as query:
            with override_settings(PALMPAY_APP_ID='academy'):
                response=self.client.post('/payments/palmpay/notify/',data={'appId':'academy','orderId':order.reference.hex},content_type='application/json')
        self.assertEqual(response.content,b'success');query.assert_called_once();self.assertTrue(payments.registration_paid(self.user))
    def test_private_calendar_and_notifications(self):
        now=timezone.now()+timedelta(days=2)
        event=AcademyEvent.objects.create(title='PRIVATE COACH MEETING',kind='appointment',starts_at=now,ends_at=now+timedelta(hours=1),recipient=self.other,published=True)
        self.assertNotContains(self.client.get('/notifications/'),'PRIVATE COACH MEETING')
        self.assertEqual(self.client.get(f'/calendar/event/{event.pk}.ics').status_code,404)
        self.client.post('/notifications/',{'key':f'event:{event.pk}'})
        self.assertFalse(NotificationRead.objects.exists())
    def test_calendar_escape_and_alarm(self):
        now=timezone.now()+timedelta(days=2)
        event=AcademyEvent.objects.create(title='Test\nATTENDEE:bad',kind='appointment',starts_at=now,ends_at=now+timedelta(hours=1),recipient=self.user,published=True)
        content=self.client.get(f'/calendar/event/{event.pk}.ics').content.decode()
        self.assertIn('TRIGGER:-PT1H',content);self.assertNotIn('\r\nATTENDEE:',content)
    def test_member_pages_render(self):
        for path in ['/payments/','/calendar/','/notifications/','/coaches/']:
            self.assertEqual(self.client.get(path).status_code,200,path)
    def test_registration_and_owner_approval_require_payment(self):
        data=dict(full_name='New applicant',phone='08166017588',date_of_birth='2000-01-01',kind='adult',preferred_position='CF',emergency_name='Contact',emergency_relationship='Sibling',emergency_phone='08000000001',rules_accepted=True,privacy_accepted=True)
        self.client.post('/application/',data)
        self.assertFalse(Application.objects.filter(user=self.user).exists())
        app=Application.objects.create(user=self.user,**data)
        owner=User.objects.create_superuser(username='owner@test.local',email='owner@test.local',password='Test!178273',email_verified=True)
        squad=Squad.objects.create(name='Test A');self.client.force_login(owner)
        self.client.post(f'/owner/applications/{app.pk}/',{'decision':'approved','squad':squad.pk})
        app.refresh_from_db();self.assertEqual(app.status,'pending');self.assertFalse(Player.objects.filter(user=self.user).exists())
    def test_signature_reference_vector(self):
        data={'requestTime':1546857549088,'version':'V2.0','nonceStr':'tXIUBaQUUip97xhymcgvndYo6oSAvQXP','orderId':'e7c3784d5e2242fc00afe89ac12399'}
        self.assertEqual(payments.signature_payload(data),b'B43F98EC214118A136077FD49CD70804')

    def test_signature_rejects_tampering(self):
        import base64
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa, padding
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        data={'appId':'academy','amount':500000,'orderId':'abc'}
        data['sign']=base64.b64encode(key.sign(payments.signature_payload(data),padding.PKCS1v15(),hashes.SHA1())).decode()
        with override_settings(PALMPAY_PUBLIC_KEY=public):
            self.assertTrue(payments.verify_signature(data))
            data['amount']=1
            self.assertFalse(payments.verify_signature(data))
    def test_monthly_slip_bad_identifier(self):
        order=payments.make_order(self.user,'registration')
        payments.settle(order,self.paid_data(order))
        self.assertEqual(self.client.get(f'/payments/{order.pk}/receipt/?month=invalid').status_code,404)

    def test_declined_registration_refund_is_idempotent_private_and_blocks_reuse(self):
        from .models import RegistrationRefund
        order=payments.make_order(self.user,'registration')
        payments.settle(order,self.paid_data(order))
        payments.request_registration_refund(self.user)
        payments.request_registration_refund(self.user)
        self.assertEqual(RegistrationRefund.objects.count(),1)
        self.assertFalse(payments.registration_paid(self.user))
        with self.assertRaises(ValueError): payments.make_order(self.user,'registration')
        self.assertContains(self.client.get('/payments/'),'Refund pending')
        self.assertContains(self.client.get(f'/payments/{order.pk}/receipt/'),'Refund pending')
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get('/payments/'),'application declined. Funds')
        self.assertEqual(self.client.get(f'/payments/{order.pk}/receipt/').status_code,404)

    def test_unpaid_application_has_no_refund_obligation(self):
        from .models import RegistrationRefund
        payments.make_order(self.user,'registration')
        payments.request_registration_refund(self.user)
        self.assertFalse(RegistrationRefund.objects.exists())

    def test_owner_decline_creates_refund_and_cannot_later_approve_same_payment(self):
        from .models import RegistrationRefund
        app=Application.objects.create(user=self.user,full_name='Applicant',phone='08166017588',date_of_birth='2000-01-01',kind='adult',preferred_position='CF',emergency_name='Contact',emergency_relationship='Sibling',emergency_phone='08000000001',rules_accepted=True,privacy_accepted=True)
        order=payments.make_order(self.user,'registration')
        payments.settle(order,self.paid_data(order))
        owner=User.objects.create_superuser(username='reviewer@test.local',email='reviewer@test.local',password='Test!178273',email_verified=True)
        self.client.force_login(owner)
        url=f'/owner/applications/{app.pk}/'
        self.client.post(url,{'decision':'declined'})
        self.client.post(url,{'decision':'declined'})
        app.refresh_from_db()
        self.assertEqual(app.status,'declined')
        self.assertEqual(RegistrationRefund.objects.filter(payment=order).count(),1)
        squad=Squad.objects.create(name='Review A')
        self.client.post(url,{'decision':'approved','squad':squad.pk})
        app.refresh_from_db();self.assertEqual(app.status,'declined')
        self.assertFalse(Player.objects.filter(user=self.user).exists())
