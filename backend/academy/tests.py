"""Regression tests for application approval, role isolation and private player records."""
from datetime import timedelta
from io import StringIO
from django.test import TestCase, Client, override_settings
from django.core import mail, signing
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from .models import User, Player, Squad, Application, TrainingSession, Attendance, Availability, Feedback, Announcement, AuditEvent, PaymentOrder
from .forms import ApplicationForm

@override_settings(OWNER_MFA_REQUIRED=False, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PortalTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_superuser(username='owner@example.test',email='owner@example.test',password='Strong!Owner782',email_verified=True)
        self.a=Squad.objects.create(name='A');self.b=Squad.objects.create(name='B')
        self.u=User.objects.create_user(username='one@example.test',email='one@example.test',password='Player!Unique782',email_verified=True)
        self.other=User.objects.create_user(username='two@example.test',email='two@example.test',password='Player!Unique793',email_verified=True)
        self.coach=User.objects.create_user(username='coach@example.test',email='coach@example.test',password='Coach!Unique793',email_verified=True,is_staff=True)
        self.a.coaches.add(self.coach)
        self.p=Player.objects.create(directory_number=1,display_name='Player One',positions='CF',user=self.u,squad=self.a)
        self.q=Player.objects.create(directory_number=2,display_name='Player Two',positions='CM',user=self.other,squad=self.b)
        self.future=TrainingSession.objects.create(title='A upcoming',squad=self.a,starts_at=timezone.now()+timedelta(days=2),venue='Awaiting confirmation')
        self.past=TrainingSession.objects.create(title='A completed',squad=self.a,starts_at=timezone.now()-timedelta(days=2),venue='Field')
        self.foreign=TrainingSession.objects.create(title='B private',squad=self.b,starts_at=timezone.now()-timedelta(days=2),venue='Field')
    def data(self,**changes):
        data=dict(full_name='Test Applicant',phone='08000000000',date_of_birth='2000-01-01',kind='adult',preferred_position='Centre-forward',emergency_name='Emergency Person',emergency_relationship='Sibling',emergency_phone='08000000001',rules_accepted=True,privacy_accepted=True)
        data.update(changes);return data
    def applicant(self,email='applicant@example.test',verified=True):
        user=User.objects.create_user(username=email,email=email,password='Applicant!Unique765',email_verified=verified)
        PaymentOrder.objects.create(user=user,purpose='registration',amount_kobo=500000,status='paid',paid_at=timezone.now())
        return Application.objects.create(user=user,**self.data())
    def test_anonymous_cannot_access_dashboard_or_coach_records(self):
        self.assertEqual(self.client.get('/').status_code,302)
        self.assertEqual(self.client.get(reverse('player-detail',args=[self.p.pk])).status_code,302)
    def test_player_sees_only_own_attendance_and_shared_feedback(self):
        Attendance.objects.create(player=self.p,session=self.past,status='present',recorded_by=self.coach)
        Feedback.objects.create(player=self.p,author=self.coach,goal='My public goal',message='My feedback')
        Feedback.objects.create(player=self.p,author=self.coach,goal='HIDDEN STAFF NOTE',message='Hidden',shared_with_player=False)
        Feedback.objects.create(player=self.q,author=self.owner,goal='OTHER PLAYER SECRET',message='Other')
        self.client.force_login(self.u);r=self.client.get('/')
        self.assertContains(r,'My public goal');self.assertNotContains(r,'HIDDEN STAFF NOTE');self.assertNotContains(r,'OTHER PLAYER SECRET');self.assertNotContains(r,'B private')
    def test_player_cannot_open_any_coaching_record_even_own(self):
        self.client.force_login(self.u)
        for p in (self.p,self.q): self.assertEqual(self.client.get(reverse('player-detail',args=[p.pk])).status_code,403)
    def test_coach_is_scoped_to_assigned_squad(self):
        self.client.force_login(self.coach)
        self.assertEqual(self.client.get(reverse('player-detail',args=[self.p.pk])).status_code,200)
        self.assertEqual(self.client.post(reverse('player-detail',args=[self.q.pk]),{'goal':'Attack','message':'Bad access','shared_with_player':'on'}).status_code,403)
        self.assertEqual(Feedback.objects.count(),0)
        self.assertEqual(self.client.get(reverse('session-detail',args=[self.foreign.pk])).status_code,403)
    def test_staff_flag_does_not_grant_owner_admin(self):
        self.client.force_login(self.coach)
        self.assertEqual(self.client.get('/admin/').status_code,302)
    def test_revoked_coach_loses_access_immediately(self):
        self.client.force_login(self.coach);self.a.coaches.remove(self.coach)
        self.assertEqual(self.client.get(reverse('player-detail',args=[self.p.pk])).status_code,403)
    def test_inactive_player_cannot_access_private_records(self):
        self.p.active=False;self.p.save();self.client.force_login(self.u)
        self.assertContains(self.client.get('/'),'Applicant dashboard')
        self.assertEqual(self.client.post(reverse('availability',args=[self.future.pk]),{'response':'yes'}).status_code,403)
    def test_availability_cannot_spoof_another_player_or_count_as_attendance(self):
        self.client.force_login(self.u)
        r=self.client.post(reverse('availability',args=[self.future.pk]),{'response':'yes','player':self.q.pk})
        self.assertEqual(r.status_code,302);self.assertEqual(Availability.objects.get().player,self.p);self.assertEqual(Attendance.objects.count(),0)
        self.assertEqual(self.client.post(reverse('availability',args=[self.foreign.pk]),{'response':'yes'}).status_code,404)
    def test_future_and_cross_squad_attendance_rejected(self):
        self.client.force_login(self.coach)
        self.assertEqual(self.client.post(reverse('attendance',args=[self.future.pk,self.p.pk]),{'status':'present'}).status_code,403)
        self.assertEqual(self.client.post(reverse('attendance',args=[self.past.pk,self.q.pk]),{'status':'present'}).status_code,404)
        self.assertEqual(Attendance.objects.count(),0)
    def test_assigned_coach_records_attendance_and_audit(self):
        self.client.force_login(self.coach)
        self.assertEqual(self.client.post(reverse('attendance',args=[self.past.pk,self.p.pk]),{'status':'present'}).status_code,302)
        self.assertEqual(Attendance.objects.get().recorded_by,self.coach)
        self.assertTrue(AuditEvent.objects.filter(action='attendance.saved').exists())
    def test_registration_cannot_escalate_permissions(self):
        r=self.client.post('/accounts/register/',{'email':'new@example.test','password1':'NewAccount!Strong766','password2':'NewAccount!Strong766','is_superuser':'true','is_staff':'true','email_verified':'true'})
        self.assertEqual(r.status_code,302)
        u=User.objects.get(email='new@example.test');self.assertFalse(u.is_superuser);self.assertFalse(u.is_staff);self.assertFalse(u.email_verified)
        self.assertEqual(len(mail.outbox),1)
        self.assertEqual(self.client.post('/application/',self.data()).status_code,403)
    def test_verification_requires_matching_user_signed_token_and_post(self):
        app=self.applicant(verified=False);self.client.force_login(app.user)
        token=signing.dumps({'uid':app.user.pk,'email':app.user.email},salt='academy-email')
        self.client.get(reverse('verify',args=[token]));app.user.refresh_from_db();self.assertFalse(app.user.email_verified)
        self.client.post(reverse('verify',args=[token]));app.user.refresh_from_db();self.assertTrue(app.user.email_verified)
        self.client.force_login(self.other);self.assertEqual(self.client.post(reverse('verify',args=[token])).status_code,400)
        self.assertEqual(self.client.post(reverse('verify',args=[token+'tamper'])).status_code,400)
    def test_student_and_graduate_fields_validated_on_server(self):
        for kind,fields in [('student',['faculty','department','course','level','institution']),('graduate',['institution','qualification','course','graduation_year'])]:
            f=ApplicationForm(self.data(kind=kind));self.assertFalse(f.is_valid())
            for key in fields:self.assertIn(key,f.errors)
        f=ApplicationForm(self.data());self.assertTrue(f.is_valid(),f.errors)
    def test_minors_require_future_separate_flow(self):
        f=ApplicationForm(self.data(date_of_birth='2015-01-01'));self.assertFalse(f.is_valid());self.assertIn('date_of_birth',f.errors)
    def test_player_cannot_self_approve(self):
        app=self.applicant();self.client.force_login(app.user)
        self.assertEqual(self.client.post(reverse('review',args=[app.pk]),{'decision':'approved','squad':self.a.pk}).status_code,403)
        self.client.post('/application/',self.data(status='approved'))
        app.refresh_from_db();self.assertEqual(app.status,'pending')
    def test_owner_links_existing_directory_without_duplicate_player(self):
        app=self.applicant();self.p.user=None;self.p.save();self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse('review',args=[app.pk]),{'decision':'approved','squad':self.a.pk,'existing_player':self.p.pk}).status_code,302)
        self.assertEqual(Player.objects.count(),2);self.p.refresh_from_db();self.assertEqual(self.p.user,app.user)
        self.client.post(reverse('review',args=[app.pk]),{'decision':'approved','squad':self.a.pk})
        self.assertEqual(Player.objects.count(),2)
    def test_owner_can_approve_new_player_with_next_number(self):
        app=self.applicant();self.client.force_login(self.owner)
        self.client.post(reverse('review',args=[app.pk]),{'decision':'approved','squad':self.b.pk})
        p=Player.objects.get(user=app.user);self.assertEqual(p.directory_number,3);self.assertEqual(p.squad,self.b)
    def test_unverified_applicant_cannot_be_approved(self):
        app=self.applicant(verified=False);self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse('review',args=[app.pk]),{'decision':'approved','squad':self.a.pk}).status_code,403)
    def test_private_announcements_do_not_cross_squads(self):
        Announcement.objects.create(title='Everyone',body='Hi',published=True)
        Announcement.objects.create(title='B SQUAD ONLY',body='Secret',squad=self.b,published=True)
        Announcement.objects.create(title='UNPUBLISHED',body='Draft')
        self.client.force_login(self.u);r=self.client.get('/')
        self.assertContains(r,'Everyone');self.assertNotContains(r,'B SQUAD ONLY');self.assertNotContains(r,'UNPUBLISHED')
    def test_csrf_protects_writes(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.u)
        self.assertEqual(client.post(reverse('availability',args=[self.future.pk]),{'response':'yes'}).status_code,403)
    def test_login_throttled_and_responses_not_cached(self):
        for _ in range(10):self.client.post('/accounts/login/',{'username':'nobody@example.test','password':'wrong'})
        self.assertEqual(self.client.post('/accounts/login/',{'username':'nobody@example.test','password':'wrong'}).status_code,429)
        self.client.force_login(self.u);self.assertIn('no-store',self.client.get('/')['Cache-Control'])
    def test_password_reset_delivers_without_exposing_account_existence(self):
        r=self.client.post('/accounts/password_reset/',{'email':self.u.email});self.assertEqual(r.status_code,302);self.assertEqual(len(mail.outbox),1)
        self.assertIn('/accounts/reset/',mail.outbox[0].body)
        r2=self.client.post('/accounts/password_reset/',{'email':'missing@example.test'});self.assertEqual(r2.url,r.url)
    def test_seed_is_idempotent_and_does_not_create_accounts(self):
        count=User.objects.count();out=StringIO();call_command('seed_directory',stdout=out);call_command('seed_directory',stdout=out)
        self.assertEqual(Player.objects.count(),28);self.assertEqual(User.objects.count(),count)
        self.assertEqual(Player.objects.get(directory_number=28).display_name,'Nedu')
        self.assertIsNone(Player.objects.get(directory_number=28).user)
        self.assertIsNone(Player.objects.get(directory_number=28).squad)
    def test_profile_edit_is_scoped_and_cannot_change_approval_or_identity(self):
        app=Application.objects.create(user=self.u,status='approved',**self.data())
        other=Application.objects.create(user=self.other,status='approved',**self.data(phone='08000000009'))
        self.client.force_login(self.u)
        response=self.client.post('/profile/',{'phone':'08000000002','emergency_name':'Sibling','emergency_relationship':'Brother','emergency_phone':'08000000003','media_consent':'on','user':self.other.pk,'status':'declined','full_name':'Spoof'})
        self.assertEqual(response.status_code,302)
        app.refresh_from_db();other.refresh_from_db()
        self.assertEqual(app.phone,'08000000002');self.assertTrue(app.media_consent)
        self.assertEqual(app.status,'approved');self.assertEqual(app.full_name,'Test Applicant')
        self.assertEqual(other.phone,'08000000009')
