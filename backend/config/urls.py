"""Route map for public health checks, account flows and permission-checked academy views."""
from django.urls import path, include
from django.contrib.auth import views as auth
from academy import views, mfa, member_views, coach_views, owner_views
from academy.admin import site
from academy.forms import EmailLoginForm
from academy.owner_activation import OwnerActivationView

urlpatterns=[
    path('coach/profile/edit/',coach_views.edit_profile,name='coach-profile-edit'),
    path('owner/',owner_views.workspace,name='owner-workspace'),
    path('owner/setup/',owner_views.setup,name='owner-setup'),
    path('owner/refunds/<int:pk>/',owner_views.refund,name='owner-refund'),
    path('payments/',member_views.billing,name='billing'),
    path('payments/checkout/',member_views.checkout,name='checkout'),
    path('payments/palmpay/notify/',member_views.payment_callback,name='payment-callback'),
    path('payments/<int:pk>/check/',member_views.refresh_payment,name='payment-check'),
    path('payments/<int:pk>/receipt/',member_views.receipt,name='receipt'),
    path('acceptance/',member_views.acceptance,name='acceptance'),
    path('coach/register/',coach_views.apply,name='coach-apply'),
    path('owner/coaches/<int:pk>/',coach_views.review,name='coach-review'),
    path('calendar/',member_views.calendar_page,name='calendar'),
    path('calendar/<str:kind>/<int:pk>.ics',member_views.calendar_export,name='calendar-export'),
    path('notifications/',member_views.notifications,name='notifications'),
    path('coaches/',member_views.coaches,name='coaches'),
    path('',views.dashboard,name='dashboard'),
    path('health/',views.health),
    path('accounts/security/',mfa.security,name='owner-security'),
    path('accounts/security/verify/',mfa.verify,name='owner-otp'),
    path('accounts/security/recovery/',mfa.recovery,name='owner-recovery'),
    path('policies/',views.policies,name='policies'),
    path('admin/',site.urls),
    path('accounts/owner-activate/<uidb64>/<token>/', OwnerActivationView.as_view(), name='owner-activate'),
    path('accounts/register/',views.signup,name='signup'),
    path('accounts/resend/',views.resend_verification,name='resend'),
    path('accounts/verify/<str:token>/',views.verify,name='verify'),
    path('accounts/login/',auth.LoginView.as_view(authentication_form=EmailLoginForm),name='login'),
    path('accounts/',include('django.contrib.auth.urls')),
    path('application/',views.application,name='application'),
    path('profile/',views.profile,name='profile'),
    path('owner/applications/<int:pk>/',views.review,name='review'),
    path('sessions/<int:pk>/availability/',views.availability,name='availability'),
    path('coach/players/<int:pk>/',views.player_detail,name='player-detail'),
    path('coach/sessions/<int:pk>/',views.session_detail,name='session-detail'),
    path('coach/sessions/<int:session_id>/players/<int:player_id>/attendance/',views.record_attendance,name='attendance'),
]
