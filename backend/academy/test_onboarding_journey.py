"""Exercise complete HTTP journeys in a disposable test database, with email captured locally."""
import re
from urllib.parse import urlsplit
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from .models import User, Squad, TransferSettings, TransferClaim, Application, Player, CoachApplication, DuesMonth, PaymentOrder

@override_settings(PORTAL_ENABLED=True, OWNER_MFA_REQUIRED=True, OWNER_MFA_METHOD='sms', OWNER_SMS_ENABLED=False,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class OnboardingJourneyTests(TestCase):
    def setUp(self):
        self.password='Football-Journey!2026'
        self.owner=User.objects.create_superuser(username='owner@journey.test',email='owner@journey.test',password=self.password,email_verified=True)
        self.squad=Squad.objects.create(name='Journey Squad')
        TransferSettings.objects.create(bank_name='Test bank',account_name='Test academy',account_number='1234567890',payment_terms='Test-only terms',enabled=True)

    def post(self,client,path,data):
        # Real CSRF cookies and middleware stay enabled throughout the journey.
        page=client.get(path)
        self.assertEqual(page.status_code,200,path)
        return client.post(path,{**data,'csrfmiddlewaretoken':client.cookies['csrftoken'].value})

    def signup_and_verify(self,email,coach=False):
        client=Client(enforce_csrf_checks=True)
        path='/accounts/register/'+('?role=coach' if coach else '')
        self.assertEqual(self.post(client,path,{'email':email,'password1':self.password,'password2':self.password}).status_code,302)
        user=User.objects.get(email=email)
        self.assertFalse(user.email_verified)
        link=re.search(r'https?://\S+',mail.outbox[-1].body).group(0)
        path=urlsplit(link).path
        self.assertEqual(self.post(client,path,{}).status_code,302)
        user.refresh_from_db();self.assertTrue(user.email_verified)
        return client,user

    def owner_login(self):
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(self.post(client,'/accounts/login/',{'username':self.owner.email,'password':self.password}).status_code,302)
        self.assertRedirects(client.get('/owner/'),'/accounts/security/',fetch_redirect_response=False)
        self.assertEqual(self.post(client,'/accounts/security/',{'action':'send','channel':'email'}).status_code,200)
        self.assertEqual(mail.outbox[-1].to,[self.owner.email])
        code=re.search(r'code is (\d{6})',mail.outbox[-1].body).group(1)
        self.assertEqual(self.post(client,'/accounts/security/',{'token':code}).status_code,302)
        self.assertEqual(client.get('/owner/').status_code,200)
        return client

    def test_player_signup_to_acceptance_and_monthly_receipt(self):
        player,user=self.signup_and_verify('player@journey.test')
        report={'purpose':'registration','months':'1','sender_name':'Test Player','reported_reference':'test-report','transfer_date':timezone.localdate().isoformat(),'accepted':'on'}
        self.assertEqual(self.post(player,'/payments/transfer/',report).status_code,302)
        claim=TransferClaim.objects.get(order__user=user)
        self.assertEqual(claim.status,'pending')
        self.assertEqual(player.get(f'/payments/{claim.order_id}/receipt/').status_code,404)
        owner=self.owner_login()
        self.assertEqual(self.post(owner,f'/owner/transfers/{claim.pk}/',{'decision':'approved','received_amount':'5000.00','bank_reference':'JOURNEY-REG','confirmed':'on'}).status_code,302)
        self.assertContains(player.get(f'/payments/{claim.order_id}/receipt/'),'Transfer verified by owner')
        self.assertEqual(player.get('/acceptance/').status_code,404)
        form={'full_name':'Test Player','phone':'08000000000','date_of_birth':'2000-01-01','kind':'adult','occupation':'Test role','preferred_position':'CM','emergency_name':'Test Contact','emergency_relationship':'Sibling','emergency_phone':'08000000001','rules_accepted':'on','privacy_accepted':'on'}
        self.assertEqual(self.post(player,'/application/',form).status_code,302)
        app=Application.objects.get(user=user);self.assertEqual(app.status,'pending')
        self.assertEqual(self.post(owner,f'/owner/applications/{app.pk}/',{'decision':'approved','squad':self.squad.pk,'review_note':'Test review'}).status_code,302)
        self.assertTrue(Player.objects.filter(user=user,squad=self.squad).exists())
        self.assertContains(player.get('/acceptance/'),'Dear Test Player')
        self.assertContains(player.get('/'),'Acceptance Letter')
        dues={**report,'purpose':'dues','months':'3','start_month':timezone.localdate().strftime('%Y-%m')}
        self.assertEqual(self.post(player,'/payments/transfer/',dues).status_code,302)
        claim=TransferClaim.objects.filter(order__user=user,order__purpose='dues').get()
        self.assertEqual(self.post(owner,f'/owner/transfers/{claim.pk}/',{'decision':'approved','received_amount':'9000.00','bank_reference':'JOURNEY-DUES','confirmed':'on'}).status_code,302)
        months=DuesMonth.objects.filter(user=user)
        self.assertEqual(months.count(),3)
        for month in months:
            self.assertContains(player.get(f'/payments/{claim.order_id}/receipt/?month={month.pk}'),'Monthly dues receipt')
        # A different signed-in member cannot see this player's letter or receipts.
        other,_=self.signup_and_verify('other@journey.test')
        self.assertEqual(other.get('/acceptance/').status_code,404)
        self.assertEqual(other.get(f'/payments/{claim.order_id}/receipt/').status_code,404)

    def test_coach_signup_to_assigned_access_without_payment(self):
        coach,user=self.signup_and_verify('coach@journey.test',coach=True)
        self.assertEqual(self.post(coach,'/coach/register/',{'full_name':'Test Coach','phone':'08000000002','experience':'Test training experience','availability':'Saturday','conduct_accepted':'on'}).status_code,302)
        app=CoachApplication.objects.get(user=user)
        self.assertFalse(user.coached_squads.exists())
        owner=self.owner_login()
        self.assertEqual(self.post(owner,f'/owner/coaches/{app.pk}/',{'decision':'approved','squads':[self.squad.pk]}).status_code,302)
        self.assertContains(coach.get('/'),'Coach dashboard')
        self.assertEqual(list(user.coached_squads.all()),[self.squad])
        self.assertFalse(PaymentOrder.objects.filter(user=user).exists())
        self.assertEqual(coach.get('/owner/').status_code,403)
