"""Welcome content is filtered by the same access rules as the member workspace."""
from django.contrib.auth.views import LoginView
from django.utils import timezone
from .forms import EmailLoginForm

class AcademyLoginView(LoginView):
    authentication_form=EmailLoginForm
    def form_valid(self,form):
        response=super().form_valid(form)
        # Keep this pending until owner MFA is completed and a member page is rendered.
        self.request.session['welcome_pending']=True
        return response

def welcome_context(request):
    if not request.user.is_authenticated or request.path.startswith(('/accounts/','/admin/')):
        return {}
    from .mfa import owner_verified
    if request.user.is_superuser and not owner_verified(request): return {}
    from .views import approved_player
    from .member_views import visible_announcements,visible_events,visible_sessions,provisional_player
    user=request.user;player=approved_player(user)
    if user.is_superuser: role='Owner / Admin';name='Warkfin Emmanuel'
    elif user.email_verified and user.coached_squads.exists():
        role='Coach';profile=getattr(user,'coach_application',None);name=profile.full_name if profile else user.get_short_name() or 'Coach'
    else: role='Player' if player else ('Provisional player' if provisional_player(user) else 'Applicant');name=player.display_name if player else user.get_short_name() or 'Academy member'
    fresh=request.method=='GET' and request.session.pop('welcome_pending',False)
    if not fresh: return {}
    now=timezone.now()
    # Owner oversight remains in management screens; welcome shows only own private events.
    events=visible_events(user).filter(ends_at__gte=now).order_by('starts_at')
    return {'login_welcome':{'name':name,'role':role,
        'news':visible_announcements(user).order_by('-created_at')[:2],
        'private':events.filter(recipient=user)[:2],
        'shared':events.filter(recipient__isnull=True)[:2],
        'training':visible_sessions(user).filter(starts_at__gte=now,status='scheduled').order_by('starts_at')[:2]}}
