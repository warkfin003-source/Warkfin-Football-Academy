"""Notification controls must preserve privacy and surface revised information."""
from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from .models import User, Announcement, CoachProfile, AppointmentRequest, NotificationRead, CoachApplication, Squad
from .member_views import notification_items

@override_settings(OWNER_MFA_REQUIRED=False,STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class NotificationTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='coach@local.test',email='coach@local.test',email_verified=True)
        self.other=User.objects.create_user(username='other@local.test',email='other@local.test',email_verified=True)
        squad=Squad.objects.create(name='Test squad');squad.coaches.add(self.user)
        self.client.force_login(self.user)
    def test_mark_all_and_revision_are_personal(self):
        news=Announcement.objects.create(title='Training',body='First venue',published=True)
        self.client.post('/notifications/?status=unread',{'action':'mark-all'})
        self.assertTrue(all(i['read'] for i in notification_items(self.user)))
        self.assertFalse(NotificationRead.objects.filter(user=self.other).exists())
        self.assertNotContains(self.client.get('/notifications/?status=unread'),'First venue')
        news.body='Changed venue';news.save()
        response=self.client.get('/notifications/?status=unread')
        self.assertContains(response,'Changed venue');self.assertContains(response,'View academy news')
    def test_foreign_keys_and_private_appointments(self):
        coach=CoachProfile.objects.create(name='Coach',nickname='Test')
        AppointmentRequest.objects.create(user=self.other,coach=coach,requested_at=timezone.now()+timedelta(days=1),topic='Private',reply='OTHER PRIVATE REPLY')
        self.client.post('/notifications/',{'key':'forged-foreign-key'})
        self.assertFalse(NotificationRead.objects.filter(key='forged-foreign-key').exists())
        self.assertNotContains(self.client.get('/notifications/'),'OTHER PRIVATE REPLY')
    def test_declined_is_not_described_as_pending(self):
        coach=CoachProfile.objects.create(name='Coach',nickname='Test')
        AppointmentRequest.objects.create(user=self.user,coach=coach,requested_at=timezone.now()+timedelta(days=1),topic='Training',status='declined')
        response=self.client.get('/notifications/')
        self.assertContains(response,'This appointment request was declined.')
        self.assertNotContains(response,'Your request is awaiting review.')
    def test_coach_decision_and_changed_note(self):
        app=CoachApplication.objects.create(user=self.user,full_name='Coach',phone='08000000000',experience='Experience',availability='Tuesday',conduct_accepted=True,status='correction',review_note='Please update availability.')
        self.client.post('/notifications/',{'action':'mark-all'})
        app.review_note='Please clarify your experience.';app.save()
        response=self.client.get('/notifications/?status=unread')
        self.assertContains(response,'Please clarify your experience.')
        self.assertContains(response,'View coach profile')
