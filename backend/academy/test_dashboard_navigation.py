"""Dashboard navigation retains squad isolation and read-only review decisions."""
from datetime import timedelta
from django.test import TestCase,override_settings
from django.utils import timezone
from .models import User,Squad,Player,TrainingSession,Application

@override_settings(OWNER_MFA_REQUIRED=False,STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class DashboardNavigationTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='player@test.local',email='player@test.local',email_verified=True)
        self.squad=Squad.objects.create(name='A')
        self.other=Squad.objects.create(name='B')
        Player.objects.create(user=self.user,directory_number=1,display_name='Player',positions='CM',squad=self.squad)
        self.client.force_login(self.user)
    def session(self,title,days,squad=None):
        return TrainingSession.objects.create(title=title,squad=squad or self.squad,starts_at=timezone.now()+timedelta(days=days),venue='Field')
    def test_upcoming_and_history_are_separate_and_scoped(self):
        self.session('Future session',2);self.session('Past session',-2)
        self.session('Foreign past',-2,self.other)
        response=self.client.get('/')
        self.assertContains(response,'Future session');self.assertNotContains(response,'Past session</h3>')
        response=self.client.get('/?sessions=history')
        self.assertContains(response,'Past session');self.assertNotContains(response,'Future session')
        self.assertNotContains(response,'Foreign past');self.assertNotContains(response,'Update my availability')
    def test_coach_sees_nearest_upcoming_and_can_paginate(self):
        self.squad.coaches.add(self.user)
        for day in range(1,13): self.session(f'Session number {day:02}',day)
        response=self.client.get('/')
        self.assertContains(response,'Session number 01');self.assertNotContains(response,'Session number 12')
        self.assertContains(response,'Page 1 of 2')
        self.assertContains(self.client.get('/?page=2'),'Session number 12')
    def test_declined_application_blocks_access_and_cannot_be_changed(self):
        app=Application.objects.create(user=self.user,full_name='Player',phone='08000000000',date_of_birth='2000-01-01',kind='adult',preferred_position='CM',status='declined',review_note='Contact the coordinator about eligibility.')
        response=self.client.get('/application/')
        self.assertContains(response,'Portal access closed',status_code=403)
        self.client.force_login(self.user)
        self.client.post('/application/',{'status':'approved','full_name':'Changed'})
        app.refresh_from_db();self.assertEqual(app.status,'declined');self.assertEqual(app.full_name,'Player')
