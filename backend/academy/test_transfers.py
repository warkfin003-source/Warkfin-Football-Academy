"""Owner-confirmed transfers must not create self-approved or duplicate financial credits."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase,override_settings
from django.utils import timezone
from .models import User,TransferSettings,TransferClaim,PaymentOrder,Player,DuesMonth
from . import payments

@override_settings(OWNER_MFA_REQUIRED=False,STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class TransferTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='p@test.local',email='p@test.local',email_verified=True)
        self.other=User.objects.create_user(username='q@test.local',email='q@test.local',email_verified=True)
        self.owner=User.objects.create_superuser(username='o@test.local',email='o@test.local',email_verified=True)
        self.config=TransferSettings.objects.create(bank_name='Test bank',account_name='Test academy',account_number='1234567890',payment_terms='Test payment terms',enabled=True)
        self.data={'purpose':'registration','months':1,'sender_name':'Player Sender','reported_reference':'reported-1','transfer_date':timezone.localdate().isoformat(),'accepted':'on','amount':1,'status':'paid'}
        self.client.force_login(self.user)
    def report(self,**changes):
        self.client.post('/payments/transfer/',{**self.data,**changes})
        return TransferClaim.objects.filter(order__user=self.user).latest('pk')
    def approve(self,claim,reference='bank-001',amount='5000.00'):
        self.client.force_login(self.owner)
        return self.client.post(f'/owner/transfers/{claim.pk}/',{'decision':'approved','received_amount':amount,'bank_reference':reference,'confirmed':'on'})
    def test_report_does_not_mark_paid_or_accept_client_amount(self):
        claim=self.report();self.assertEqual(claim.order.amount_kobo,500000)
        self.assertFalse(payments.registration_paid(self.user))
        self.assertEqual(self.client.get(f'/payments/{claim.order_id}/receipt/').status_code,404)
        self.client.post('/payments/transfer/',self.data)
        self.assertEqual(TransferClaim.objects.count(),1)
    def test_owner_approval_receipt_and_repeated_post(self):
        claim=self.report();self.approve(claim);self.approve(claim)
        claim.refresh_from_db();self.assertEqual(claim.status,'approved')
        self.assertTrue(payments.registration_paid(self.user))
        self.client.force_login(self.user)
        self.assertContains(self.client.get(f'/payments/{claim.order_id}/receipt/'),'Transfer verified by owner')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f'/payments/{claim.order_id}/receipt/').status_code,404)
    def test_member_cannot_approve_or_change_receiving_account(self):
        claim=self.report()
        for path in ['/owner/transfers/','/owner/transfers/settings/',f'/owner/transfers/{claim.pk}/']:
            self.assertEqual(self.client.post(path,{'decision':'approved'}).status_code,403)
    def test_approval_requires_confirmation_exact_amount_and_reference(self):
        claim=self.report();self.client.force_login(self.owner)
        self.client.post(f'/owner/transfers/{claim.pk}/',{'decision':'approved'})
        self.approve(claim,amount='1.00')
        claim.refresh_from_db();self.assertEqual(claim.status,'pending');self.assertFalse(payments.registration_paid(self.user))
    def test_bank_reference_cannot_be_credited_to_two_users(self):
        claim=self.report();self.approve(claim,' Ref-123 ')
        self.user=self.other;self.client.force_login(self.user)
        second=self.report();self.approve(second,'ref-123')
        second.refresh_from_db();self.assertEqual(second.status,'pending');self.assertFalse(payments.registration_paid(self.other))
    def test_report_cannot_be_verified_through_provider_path(self):
        claim=self.report()
        with self.assertRaises(ValueError):
            payments.settle(claim.order,{'orderId':claim.order.reference.hex,'currency':'NGN','amount':500000,'orderNo':'fake','orderStatus':2})
        with patch('academy.payments.provider_request') as provider:
            self.client.post(f'/payments/{claim.order_id}/check/')
            provider.assert_not_called()
    def test_dues_allocate_months_once(self):
        Player.objects.create(user=self.user,directory_number=1,display_name='Player',positions='CM')
        start=timezone.localdate().replace(day=1)
        claim=self.report(purpose='dues',months=3,start_month=start.strftime('%Y-%m'))
        self.approve(claim,amount='9000.00');self.approve(claim,amount='9000.00')
        self.assertEqual(list(DuesMonth.objects.values_list('month',flat=True)),payments.month_sequence(start,3))
    def test_decline_preserves_report_and_allows_corrected_report(self):
        claim=self.report();self.client.force_login(self.owner)
        self.client.post(f'/owner/transfers/{claim.pk}/',{'decision':'declined','note':'Reference not found. Contact the owner before paying again.'})
        claim.refresh_from_db();self.assertEqual(claim.status,'declined')
        self.client.force_login(self.user);second=self.report(reported_reference='corrected')
        self.assertNotEqual(claim.order_id,second.order_id);self.assertFalse(payments.registration_paid(self.user))
    def test_disabled_instructions_block_reports(self):
        self.config.enabled=False;self.config.save()
        self.assertEqual(self.client.post('/payments/transfer/',self.data).status_code,302)
        self.assertFalse(TransferClaim.objects.exists())
    def test_settings_validate_account_number(self):
        self.client.force_login(self.owner)
        self.client.post('/owner/transfers/settings/',{'bank_name':'Test','account_name':'Name','account_number':'bad','payment_terms':'Terms','enabled':'on','confirmed':'on'})
        self.config.refresh_from_db();self.assertEqual(self.config.account_number,'1234567890')

    def test_transfer_report_cannot_also_start_gateway_checkout(self):
        claim=self.report()
        with patch('academy.payments.provider_request') as provider:
            with self.assertRaises(payments.PaymentUnavailable): payments.start_checkout(claim.order)
            provider.assert_not_called()
    def test_completed_order_cannot_start_checkout_again(self):
        order=PaymentOrder.objects.create(user=self.user,purpose='registration',amount_kobo=500000,status='paid')
        with patch('academy.payments.provider_request') as provider:
            with self.assertRaises(payments.PaymentUnavailable): payments.start_checkout(order)
            provider.assert_not_called()
