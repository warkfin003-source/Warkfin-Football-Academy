"""Route map for public health checks, account flows and permission-checked academy views."""
from django.urls import path, include
from django.contrib.auth import views as auth
from academy import views
from academy.admin import site
from academy.forms import EmailLoginForm
from academy.owner_activation import OwnerActivationView

urlpatterns=[
    path('',views.dashboard,name='dashboard'),
    path('health/',views.health),
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
