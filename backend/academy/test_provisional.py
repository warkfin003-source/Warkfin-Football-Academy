"""Provisional membership permits dues and selected notices, never admission or squad access."""
from django.test import TestCase,override_settings
from django.utils import timezone
from .models import User,Application,Player,Squad,TrainingSession,Announcement,TransferSettings,TransferClaim,DuesMonth,AcademyEvent
from .member_views import visible_sessions,visible_events,visible_announcements
from . import payments

@override_settings(OWNER_MFA_REQUIRED=False,STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ProvisionalTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='provisional@test.local',email='provisional@test.local',email_verified=True)
        self.owner=User.objects.create_superuser(username='owner@test.local',email='owner@test.local',email_verified=True)
        self.client.force_login(self.user)
        self.data={'full_name':'Test Provisional','phone':'08000000000','date_of_birth':'2000-01-01','kind':'adult','preferred_position':'CM','emergency_name':'Contact','emergency_relationship':'Sibling','emergency_phone':'08000000001','rules_accepted':'on','privacy_accepted':'on'}
        TransferSettings.objects.create(bank_name='Test bank',account_name='Test academy',account_number='1234567890',payment_terms='Test only',enabled=True)
    def profile(self):
        self.assertEqual(self.client.post('/provisional-profile/',self.data).status_code,302)
        return Application.objects.get(user=self.user)
    def test_profile_dues_and_receipt_do_not_grant_admission(self):
        app=self.profile();self.assertEqual(app.status,'provisional')
        self.assertFalse(Player.objects.filter(user=self.user).exists())
        self.assertContains(self.client.get('/'),'Provisional Player Account')
        report={'purpose':'dues','start_month':timezone.localdate().strftime('%Y-%m'),'months':1,'sender_name':'Test Provisional','reported_reference':'test','transfer_date':timezone.localdate().isoformat(),'accepted':'on'}
        self.assertEqual(self.client.post('/payments/transfer/',report).status_code,302)
        claim=TransferClaim.objects.get(order__user=self.user)
        self.assertEqual(claim.order.amount_kobo,300000)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(f'/owner/transfers/{claim.pk}/',{'decision':'approved','received_amount':'3000.00','bank_reference':'TEST-PROVISIONAL','confirmed':'on'}).status_code,302)
        self.assertEqual(DuesMonth.objects.filter(user=self.user).count(),1)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(f'/payments/{claim.order_id}/receipt/'),'not an Acceptance Letter')
        self.assertEqual(self.client.get('/acceptance/').status_code,404)
        app.refresh_from_db();self.assertEqual(app.status,'provisional')
        self.assertFalse(payments.registration_paid(self.user))
        self.assertFalse(Player.objects.filter(user=self.user).exists())
    def test_private_scope_and_registers_remain_blocked(self):
        self.profile();squad=Squad.objects.create(name='Private squad')
        shared=TrainingSession.objects.create(title='Shared training',squad=squad,starts_at=timezone.now(),venue='Field',provisional_visible=True)
        private=TrainingSession.objects.create(title='Private training',squad=squad,starts_at=timezone.now(),venue='Field')
        Announcement.objects.create(title='General update',body='Test',published=True,provisional_visible=True)
        Announcement.objects.create(title='Private notice',body='Secret',published=True)
        Announcement.objects.create(title='Squad notice',body='Secret',published=True,provisional_visible=True,squad=squad)
        self.assertEqual(list(visible_sessions(self.user)),[shared])
        self.assertEqual(list(visible_announcements(self.user).values_list('title',flat=True)),['General update'])
        self.assertEqual(self.client.get(f'/coach/sessions/{shared.pk}/').status_code,403)
        self.assertEqual(self.client.get(f'/calendar/session/{private.pk}.ics').status_code,404)
        self.assertEqual(self.client.get('/owner/').status_code,403)
    def test_incomplete_unverified_and_coach_accounts_cannot_use_provisional_dues(self):
        self.assertEqual(self.client.post('/provisional-profile/',{}).status_code,200)
        self.assertFalse(Application.objects.filter(user=self.user).exists())
        self.user.email_verified=False;self.user.save()
        self.assertEqual(self.client.post('/provisional-profile/',self.data).status_code,403)
        self.user.email_verified=True;self.user.onboarding_role='coach';self.user.save()
        self.assertEqual(self.client.post('/provisional-profile/',self.data).status_code,403)
    def test_formal_application_still_requires_registration_payment(self):
        app=self.profile()
        self.client.post('/application/',self.data)
        app.refresh_from_db();self.assertEqual(app.status,'provisional')
        order=payments.make_order(self.user,'registration')
        # Isolated provider simulation; no live bank or production records are touched.
        payments.settle(order,{'orderId':order.reference.hex,'currency':'NGN','amount':500000,'orderNo':'TEST-REG','orderStatus':2})
        squad=Squad.objects.create(name='A')
        self.client.force_login(self.owner)
        self.client.post(f'/owner/applications/{app.pk}/',{'decision':'approved','squad':squad.pk})
        app.refresh_from_db();self.assertEqual(app.status,'provisional')
        self.client.force_login(self.user);self.client.post('/application/',self.data)
        app.refresh_from_db();self.assertEqual(app.status,'pending')
