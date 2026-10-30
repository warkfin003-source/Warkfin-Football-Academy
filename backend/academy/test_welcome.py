"""Login notices and public calendars must not disclose private member schedules."""
from datetime import timedelta
from django.test import TestCase,override_settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import User,Squad,Player,AcademyEvent,Announcement,CoachApplication
from .member_views import notification_items

@override_settings(OWNER_MFA_REQUIRED=False,STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class WelcomeTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='player@test.local',email='player@test.local',password='Secure!123456',email_verified=True)
        self.other=User.objects.create_user(username='other@test.local',email='other@test.local',email_verified=True)
        self.squad=Squad.objects.create(name='A')
        Player.objects.create(user=self.user,directory_number=1,display_name='Player One',positions='CF',squad=self.squad)
        self.now=timezone.now()+timedelta(days=1)
    def event(self,title,**extra):
        return AcademyEvent.objects.create(title=title,kind='appointment',starts_at=self.now,ends_at=self.now+timedelta(hours=1),published=True,**extra)
    def test_welcome_after_login_once_and_private_updates_filtered(self):
        self.event('MY PRIVATE',recipient=self.user)
        self.event('OTHER PRIVATE',recipient=self.other)
        Announcement.objects.create(title='Academy news',body='Training update',published=True)
        response=self.client.post('/accounts/login/',{'username':self.user.email,'password':'Secure!123456'})
        self.assertEqual(response.status_code,302)
        response=self.client.get('/')
        self.assertContains(response,'Welcome back, Player One.')
        self.assertContains(response,'Academy news');self.assertContains(response,'MY PRIVATE')
        self.assertNotContains(response,'OTHER PRIVATE')
        self.assertNotContains(self.client.get('/'),'Welcome back, Player One.')
    def test_failed_login_has_no_welcome(self):
        self.client.post('/accounts/login/',{'username':self.user.email,'password':'wrong'})
        self.assertFalse(self.client.session.get('welcome_pending',False))
    def test_public_requires_explicit_flag_and_no_restriction(self):
        self.event('Open training',public=True)
        self.event('Members event')
        self.event('Secret event',recipient=self.other,public=True)
        self.event('Squad event',squad=self.squad,public=True)
        response=self.client.get('/schedule/')
        self.assertContains(response,'Open training')
        for text in ['Members event','Secret event','Squad event']: self.assertNotContains(response,text)
        with self.assertRaises(ValidationError): AcademyEvent.objects.get(title='Secret event').full_clean()
    def test_private_filter_only_own_recipient(self):
        self.event('MY PRIVATE',recipient=self.user);self.event('OTHER PRIVATE',recipient=self.other);self.event('Shared activity')
        self.client.force_login(self.user)
        response=self.client.get('/calendar/',{'scope':'private','month':timezone.localtime(self.now).strftime('%Y-%m')})
        self.assertContains(response,'MY PRIVATE');self.assertNotContains(response,'OTHER PRIVATE');self.assertNotContains(response,'Shared activity')
    def test_coach_and_owner_do_not_get_player_fee_notice(self):
        self.squad.coaches.add(self.other)
        self.assertFalse(any(x['key'].startswith('registration-fee:') for x in notification_items(self.other)))
        owner=User.objects.create_superuser(username='owner@test.local',email='owner@test.local',email_verified=True)
        self.assertFalse(any(x['key'].startswith('registration-fee:') for x in notification_items(owner)))
