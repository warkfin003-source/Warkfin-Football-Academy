"""Release checks for disabled collections and role-appropriate billing."""
from unittest.mock import patch
from django.test import TestCase,override_settings
from .models import User,Player

@override_settings(OWNER_MFA_REQUIRED=False,STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ReleaseTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='coach@test.local',email='coach@test.local',email_verified=True,onboarding_role='coach')
        self.client.force_login(self.user)
    def test_coach_billing_has_no_player_checkout_even_if_gateway_ready(self):
        with patch('academy.payments.ready',return_value=True),patch('academy.payments.make_order') as order:
            response=self.client.get('/payments/')
            self.assertContains(response,'No player registration fee required')
            self.assertNotContains(response,'Pay registration fee')
            self.assertEqual(self.client.post('/payments/checkout/',{'purpose':'registration','terms':'yes'}).status_code,403)
            order.assert_not_called()
    def test_dual_role_player_retains_billing(self):
        Player.objects.create(user=self.user,directory_number=1,display_name='Dual role',positions='CM')
        self.assertContains(self.client.get('/payments/'),'₦5,000')
    def test_unpaid_applicant_sees_blocker_before_filling_form(self):
        self.user.onboarding_role='player';self.user.save()
        with patch('academy.payments.ready',return_value=False):
            self.assertContains(self.client.get('/application/'),'Application submission is currently unavailable.')
