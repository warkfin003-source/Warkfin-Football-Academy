"""Owner controls must remain private and preserve financial evidence."""
from unittest.mock import patch
from django.test import TestCase,override_settings
from .models import User,PaymentOrder,RegistrationRefund,CoachApplication,Announcement,AuditEvent
from . import payments

@override_settings(OWNER_MFA_REQUIRED=False,STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class OwnerWorkspaceTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_superuser(username='owner@test.local',email='owner@test.local',password='Test!123456',email_verified=True)
        self.member=User.objects.create_user(username='player@test.local',email='player@test.local',email_verified=True)
        self.order=PaymentOrder.objects.create(user=self.member,purpose='registration',amount_kobo=500000,status='paid',provider_reference='paid123')
        self.refund=RegistrationRefund.objects.create(payment=self.order)
    def test_owner_pages_block_members(self):
        self.client.force_login(self.member)
        for url in ['/owner/','/owner/setup/',f'/owner/refunds/{self.refund.pk}/']:
            self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get('/'),'Lead the academy')
        self.assertContains(self.client.get('/owner/setup/'),'SMS Sender ID')
    def test_refund_requires_evidence_and_does_not_change_collection(self):
        self.client.force_login(self.owner);url=f'/owner/refunds/{self.refund.pk}/'
        self.client.post(url,{'status':'refunded'})
        self.refund.refresh_from_db();self.assertEqual(self.refund.status,'requested')
        self.client.post(url,{'status':'refunded','reference':'refund123','confirmed':'on'})
        self.refund.refresh_from_db();self.assertEqual(self.refund.status,'refunded')
        self.assertEqual(self.refund.recorded_by,self.owner)
        self.client.post(url,{'status':'processing'})
        self.refund.refresh_from_db();self.assertEqual(self.refund.status,'refunded')
        self.order.refresh_from_db();self.assertEqual(self.order.status,'paid')
        self.assertFalse(payments.registration_paid(self.member))
        self.client.force_login(self.member)
        self.assertContains(self.client.get('/payments/'),'refund123')
    def test_coach_edit_preserves_access_decision(self):
        app=CoachApplication.objects.create(user=self.member,full_name='Coach',phone='08166017588',experience='Test',availability='Tuesday',conduct_accepted=True,status='approved')
        self.client.force_login(self.member)
        self.client.post('/coach/profile/edit/',{'full_name':'Coach','phone':'08166017588','experience':'Updated','availability':'Saturday','conduct_accepted':'on','status':'declined','is_superuser':'true'})
        app.refresh_from_db();self.assertEqual(app.status,'approved');self.assertEqual(app.experience,'Updated')
        self.member.refresh_from_db();self.assertFalse(self.member.is_superuser)
    def test_admin_views_and_confirmed_announcement_deletion(self):
        self.client.force_login(self.owner)
        with patch('academy.admin.owner_verified',return_value=True):
            for path in ['/admin/','/admin/academy/coachapplication/','/admin/academy/paymentorder/','/admin/academy/attendance/']:
                self.assertEqual(self.client.get(path).status_code,200,path)
            announcement=Announcement.objects.create(title='Draft',body='Text')
            url=f'/admin/academy/announcement/{announcement.pk}/delete/'
            self.assertEqual(self.client.get(url).status_code,200)
            self.assertTrue(Announcement.objects.filter(pk=announcement.pk).exists())
            self.client.post(url,{'post':'yes'})
            self.assertFalse(Announcement.objects.filter(pk=announcement.pk).exists())
            self.assertTrue(AuditEvent.objects.filter(action='announcement.deleted').exists())
            self.assertEqual(self.client.post(f'/admin/academy/paymentorder/{self.order.pk}/delete/',{'post':'yes'}).status_code,403)
