"""Coach onboarding must not provide self-service privilege escalation."""
from django.test import TestCase, override_settings
from .models import User, Squad, CoachApplication

@override_settings(OWNER_MFA_REQUIRED=False,STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class CoachTests(TestCase):
    def setUp(self):
        self.coach=User.objects.create_user(username='coach@test.local',email='coach@test.local',email_verified=True)
        self.owner=User.objects.create_superuser(username='owner@test.local',email='owner@test.local',password='Owner!123456',email_verified=True)
        self.squad=Squad.objects.create(name='A')
        self.data={'full_name':'Smith','phone':'08166017588','experience':'Training support','availability':'Saturday morning','conduct_accepted':'on','status':'approved','is_superuser':'true'}
        self.client.force_login(self.coach)
    def test_submission_never_grants_permissions_and_is_idempotent(self):
        self.client.post('/coach/register/',self.data)
        self.client.post('/coach/register/',self.data)
        self.assertEqual(CoachApplication.objects.count(),1)
        self.assertEqual(CoachApplication.objects.get().status,'pending')
        self.coach.refresh_from_db()
        self.assertFalse(self.coach.is_superuser);self.assertFalse(self.coach.is_staff)
        self.assertFalse(self.coach.coached_squads.exists())
        self.assertContains(self.client.get('/coach/register/'),'Pending review')
    def test_owner_review_assigns_only_chosen_squad(self):
        self.client.post('/coach/register/',self.data);app=CoachApplication.objects.get()
        url=f'/owner/coaches/{app.pk}/'
        self.assertEqual(self.client.post(url,{'decision':'approved','squads':[self.squad.pk]}).status_code,403)
        self.client.force_login(self.owner)
        self.client.post(url,{'decision':'approved'})
        app.refresh_from_db();self.assertEqual(app.status,'pending')
        self.client.post(url,{'decision':'approved','squads':[self.squad.pk]})
        app.refresh_from_db();self.assertEqual(app.status,'approved')
        self.assertEqual(list(self.coach.coached_squads.all()),[self.squad])
        self.coach.refresh_from_db();self.assertFalse(self.coach.is_staff)
        self.client.force_login(self.coach)
        self.assertContains(self.client.get('/'),'Coach dashboard')
    def test_private_profile_and_email_verification(self):
        self.client.post('/coach/register/',self.data)
        other=User.objects.create_user(username='other@test.local',email='other@test.local')
        self.client.force_login(other)
        self.assertEqual(self.client.post('/coach/register/',self.data).status_code,302)
        self.assertEqual(CoachApplication.objects.count(),1)
        other.email_verified=True;other.save()
        self.assertNotContains(self.client.get('/coach/register/'),'Training support')
    def test_decline_and_correction_do_not_grant_access(self):
        self.client.post('/coach/register/',self.data);app=CoachApplication.objects.get()
        self.client.force_login(self.owner)
        self.client.post(f'/owner/coaches/{app.pk}/',{'decision':'correction','review_note':'Add details'})
        self.client.force_login(self.coach)
        self.assertContains(self.client.get('/coach/register/'),'Add details')
        self.client.post('/coach/register/',self.data)
        app.refresh_from_db();self.assertEqual(app.status,'pending')
        self.client.force_login(self.owner)
        self.client.post(f'/owner/coaches/{app.pk}/',{'decision':'declined'})
        self.assertFalse(self.coach.coached_squads.exists())
    def test_coach_signup_does_not_show_player_fee_requirement(self):
        self.client.logout()
        self.assertContains(self.client.get('/accounts/register/?role=coach'),'Create your coach login')
        self.assertNotContains(self.client.get('/accounts/register/?role=coach'),'Registration fee ·')
