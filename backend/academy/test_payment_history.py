from django.test import TestCase, override_settings
from .models import User, Application, PaymentOrder

@override_settings(OWNER_MFA_REQUIRED=False,STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PaymentHistoryTests(TestCase):
    def setUp(self):
        self.player=User.objects.create_user(username='player@history.test',email='player@history.test',email_verified=True)
        self.other=User.objects.create_user(username='other@history.test',email='other@history.test',email_verified=True)
        self.owner=User.objects.create_superuser(username='owner@history.test',email='owner@history.test',email_verified=True)
        Application.objects.create(user=self.player,full_name='History Player',phone='08011112222',date_of_birth='2000-01-01',status='provisional')
        self.paid=PaymentOrder.objects.create(user=self.player,payer_name='History Player',purpose='dues',status='paid',amount_kobo=300000,start_month='2026-10-01',months=1)
        self.pending=PaymentOrder.objects.create(user=self.player,payer_name='History Player',purpose='registration',status='pending',amount_kobo=500000)
        self.foreign=PaymentOrder.objects.create(user=self.other,payer_name='Private Other',purpose='dues',status='paid',amount_kobo=900000)
    def test_player_history_is_private_and_totals_only_verified(self):
        self.client.force_login(self.player)
        for query in ('','?print=1','?q=other&status=all'):
            response=self.client.get('/payments/history/'+query)
            self.assertNotContains(response,'Private Other')
            self.assertEqual(response.context['verified_total'],3000)
            self.assertEqual(response.context['record_count'],2)
        self.assertEqual(self.client.get('/owner/payments/').status_code,403)
        self.assertEqual(self.client.get(f'/owner/payments/{self.foreign.pk}/receipt/').status_code,403)
        self.assertEqual(self.client.get(f'/payments/{self.foreign.pk}/receipt/').status_code,404)
    def test_owner_paid_default_search_and_receipts(self):
        self.client.force_login(self.owner)
        response=self.client.get('/owner/payments/')
        self.assertEqual(response.context['record_count'],2)
        self.assertEqual(response.context['verified_total'],12000)
        self.assertContains(response,'08011112222')
        response=self.client.get('/owner/payments/?q=08011112222&print=1')
        self.assertEqual(response.context['record_count'],1)
        self.assertNotContains(response,'Private Other')
        self.assertContains(response,'Print / Save as PDF')
        self.assertContains(self.client.get(f'/owner/payments/{self.paid.pk}/receipt/'),'History Player')
        self.assertEqual(self.client.get(f'/owner/payments/{self.pending.pk}/receipt/').status_code,404)
    def test_print_includes_all_filtered_pages(self):
        PaymentOrder.objects.bulk_create([PaymentOrder(user=self.player,payer_name='History Player',purpose='dues',status='paid',amount_kobo=300000) for _ in range(28)])
        self.client.force_login(self.player)
        response=self.client.get('/payments/history/?status=paid')
        self.assertEqual(len(response.context['orders']),25)
        printed=self.client.get('/payments/history/?status=paid&print=1')
        self.assertEqual(len(printed.context['orders']),29)
        self.assertEqual(printed.context['verified_total'],87000)
    def test_anonymous_history_and_print_require_login(self):
        for path in ('/payments/history/','/payments/history/?print=1','/owner/payments/?print=1'):
            self.assertEqual(self.client.get(path).status_code,302)
