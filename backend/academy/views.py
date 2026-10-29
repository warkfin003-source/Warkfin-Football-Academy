"""Academy workflows with owner, assigned-coach and individual-player access boundaries."""
import logging
from functools import wraps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q, Max
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from .models import User, Application, Player, Squad, TrainingSession, Availability, Attendance, Feedback, Announcement, AuditEvent
from .forms import SignUpForm, ApplicationForm, ReviewForm, AvailabilityForm, AttendanceForm, FeedbackForm, ContactProfileForm

# Record identifiers only; never copy passwords, tokens or private form values into the audit trail.
def audit(actor,action,obj):
    AuditEvent.objects.create(actor=actor,action=action,object_reference=f'{obj._meta.model_name}:{obj.pk}')

# Authentication alone is insufficient: every owner endpoint requires the owner privilege.
def owner_required(view):
    @login_required
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        if not request.user.is_superuser: return HttpResponseForbidden('Owner access required.')
        return view(request,*args,**kwargs)
    return wrapped

# Email verification and an active linked directory record are both required.
def approved_player(user):
    if not user.email_verified: return None
    return Player.objects.filter(user=user,active=True).first()

# Coach access is restricted to explicit squad assignments; owner access covers all squads.
def may_coach(user,squad_id):
    return user.is_superuser or (user.email_verified and user.coached_squads.filter(pk=squad_id).exists())

# Bind a signed, expiring verification link to both the user ID and current email.
def send_verification(user):
    token=signing.dumps({'uid':user.pk,'email':user.email},salt='academy-email')
    link=settings.PORTAL_ORIGIN+reverse('verify',args=[token])
    send_mail('Verify your Warkfin Academy account',f'Confirm your email to continue your application:\n{link}\nThis link expires in 24 hours. Verification does not approve academy membership.',settings.DEFAULT_FROM_EMAIL,[user.email])

# Save the account before email submission so delivery failures can be retried safely.
def signup(request):
    if request.user.is_authenticated: return redirect('dashboard')
    coach_signup=request.GET.get('role')=='coach'
    form=SignUpForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        user=form.save(commit=False)
        user.onboarding_role="coach" if coach_signup else "player"
        user.save()
        login(request,user)
        try:
            send_verification(user)
            messages.success(request,'Account created. Check your email for the verification link.')
        except Exception:
            logging.getLogger(__name__).error('Verification delivery failed for user id %s',user.pk)
            messages.warning(request,'Account created, but email delivery failed. Use Resend verification or contact the academy.')
        return redirect('dashboard')
    from .payments import ready
    from .transfers import configuration
    return render(request,'form.html',{'form':form,'title':'Create your account','button':'Create account','registration_notice':not coach_signup,'coach_notice':coach_signup,'payment_ready':ready() or bool(configuration())})

# Require a CSRF-protected POST; middleware rate-limits account endpoints.
@login_required
@require_POST
def resend_verification(request):
    if not request.user.email_verified:
        try: send_verification(request.user); messages.success(request,'Verification email sent.')
        except Exception: messages.error(request,'Email could not be sent. Please try later or contact the academy.')
    return redirect('dashboard')

# A GET only displays confirmation. A matching signed-in user must POST to verify.
@login_required
def verify(request,token):
    try:
        payload=signing.loads(token,salt='academy-email',max_age=86400)
        if payload!={'uid':request.user.pk,'email':request.user.email}: raise signing.BadSignature()
    except signing.BadSignature:
        return render(request,'notice.html',{'title':'Verification link unavailable','text':'Sign into the correct account or request a new verification email.'},status=400)
    if request.method=='POST':
        request.user.email_verified=True;request.user.save(update_fields=['email_verified'])
        # Verification confirms identity only; payment and admission have separate checks.
        messages.success(request,'Email verified. Your dashboard shows the next step for your account.')
        return redirect('dashboard')
    return render(request,'form.html',{'title':'Confirm your email address','button':'Verify my email'})

# Only verified applicants can submit; reviewed records cannot silently re-enter approval.
@login_required
def application(request):
    if not request.user.email_verified: return HttpResponseForbidden('Verify your email first.')
    existing=Application.objects.filter(user=request.user).first()
    if existing and existing.status in ('approved','declined'):
        return render(request,'application_status.html',{'application':existing})
    from .payments import registration_paid, ready
    from .transfers import configuration
    submission_blocked=not registration_paid(request.user) and not ready() and not configuration()
    form=ApplicationForm(request.POST or None,instance=existing)
    if request.method=='POST' and form.is_valid():
        from .payments import registration_paid
        if not registration_paid(request.user):
            messages.warning(request,'Pay the ₦5,000 registration fee before submitting your application. Your account remains available.')
            return redirect('billing')
        obj=form.save(commit=False);obj.user=request.user;obj.status='pending';obj.review_note='';obj.save()
        audit(request.user,'application.submitted',obj)
        messages.success(request,'Application submitted for owner review.')
        return redirect('dashboard')
    return render(request,'form.html',{'title':'Academy application','form':form,'button':'Submit application','application_form':True,'submission_blocked':submission_blocked})

# Filter every queryset on the server. Hiding a template section is not an access-control mechanism.
@login_required
def dashboard(request):
    user=request.user
    if user.is_superuser:
        from .owner_views import workspace
        return workspace(request)
    from .payments import registration_paid
    from .models import CoachApplication
    context={'coach_application':CoachApplication.objects.filter(user=user).first(),'application':Application.objects.filter(user=user).first(), 'registration_paid':registration_paid(user)}
    if user.email_verified and user.coached_squads.exists():
        context.update(role='Coach',players=Player.objects.filter(squad__coaches=user,active=True).distinct())
    else:
        player=approved_player(user)
        context.update(role='Player' if player else 'Applicant',player=player)
        if player:
            context.update(attendance=Attendance.objects.filter(player=player).select_related('session').order_by('-session__starts_at')[:30],feedback=Feedback.objects.filter(player=player,shared_with_player=True).order_by('-created_at')[:20],availability=Availability.objects.filter(player=player).select_related('session').order_by('-session__starts_at')[:20])
    context['coach_onboarding']=bool(not context.get('player') and (user.onboarding_role=='coach' or context['coach_application']))
    if context['role']!='Applicant':
        # Reuse authorization filters before paginating either upcoming or past sessions.
        from .member_views import visible_sessions
        scope='history' if request.GET.get('sessions')=='history' else 'upcoming'
        sessions=visible_sessions(user)
        sessions=sessions.filter(starts_at__lt=timezone.now()).order_by('-starts_at','-pk') if scope=='history' else sessions.filter(starts_at__gte=timezone.now()).order_by('starts_at','pk')
        page=Paginator(sessions,10).get_page(request.GET.get('page'))
        context.update(sessions=page,session_scope=scope,session_page=page)
        allowed=Q(squad__isnull=True)
        if user.is_superuser: allowed=Q()
        elif context['role']=='Coach': allowed|=Q(squad__coaches=user)
        else: allowed|=Q(squad_id=context['player'].squad_id)
        context['announcements']=Announcement.objects.filter(allowed,published=True).distinct().order_by('-created_at')[:20]
    return render(request,'dashboard.html',context)

# Lock relevant records while approving to prevent duplicate links and directory-number races.
@owner_required
def review(request,pk):
    obj=get_object_or_404(Application,pk=pk)
    form=ReviewForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            obj=Application.objects.select_for_update().select_related('user').get(pk=pk)
            if obj.status=='approved' or Player.objects.filter(user=obj.user).exists():
                messages.error(request,'This account is already approved. Manage its player record instead.')
                return redirect('dashboard')
            if not obj.user.email_verified: return HttpResponseForbidden('Applicant must verify their email first.')
            decision=form.cleaned_data['decision']
            if decision=='approved':
                from .payments import registration_paid
                if not registration_paid(obj.user):
                    messages.error(request,'Registration payment has not been verified. Approval is blocked.')
                    return redirect('review',pk=pk)
                squad=Squad.objects.select_for_update().get(pk=form.cleaned_data['squad'].pk)
                chosen=form.cleaned_data['existing_player']
                if chosen:
                    player=Player.objects.select_for_update().get(pk=chosen.pk)
                    if player.user_id:
                        messages.error(request,'That player record has already been linked. Choose another record.')
                        return redirect('review',pk=pk)
                    player.user=obj.user;player.squad=squad;player.active=True;player.save()
                else:
                    # Lock the owner account to serialize new directory-number allocation.
                    User.objects.select_for_update().filter(is_superuser=True).order_by('pk').first()
                    number=(Player.objects.aggregate(n=Max('directory_number'))['n'] or 0)+1
                    player=Player.objects.create(directory_number=number,display_name=obj.full_name,positions=obj.preferred_position,user=obj.user,squad=squad)
                audit(request.user,'player.approved',player)
            obj.status=decision;obj.review_note=form.cleaned_data['review_note'];obj.save()
            if decision=='declined':
                from .payments import request_registration_refund
                request_registration_refund(obj.user)
            audit(request.user,'application.'+decision,obj)
        messages.success(request,'Application review saved. The applicant can see the decision in their dashboard.')
        return redirect('dashboard')
    return render(request,'review.html',{'application':obj,'form':form,'title':'Review application'})

# Accept responses only for the player’s own future, scheduled squad session.
@login_required
def availability(request,pk):
    player=approved_player(request.user)
    if not player: return HttpResponseForbidden('Approved player access required.')
    session=get_object_or_404(TrainingSession,pk=pk,squad_id=player.squad_id,status='scheduled',starts_at__gt=timezone.now())
    existing=Availability.objects.filter(player=player,session=session).first()
    form=AvailabilityForm(request.POST or None,instance=existing)
    if request.method=='POST' and form.is_valid():
        obj=form.save(commit=False);obj.player=player;obj.session=session;obj.save();audit(request.user,'availability.saved',obj)
        return redirect('dashboard')
    return render(request,'form.html',{'form':form,'title':f'Availability: {session.title}','button':'Save availability'})

# Authorize the assigned coach before reading or writing individual development notes.
@login_required
def player_detail(request,pk):
    player=get_object_or_404(Player,pk=pk,active=True)
    if not may_coach(request.user,player.squad_id): return HttpResponseForbidden('Assigned coach access required.')
    form=FeedbackForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        obj=form.save(commit=False);obj.player=player;obj.author=request.user;obj.save();audit(request.user,'feedback.created',obj)
        return redirect('player-detail',pk=pk)
    return render(request,'player.html',{'player':player,'form':form,'feedback':Feedback.objects.filter(player=player).order_by('-created_at'),'attendance':Attendance.objects.filter(player=player).select_related('session'),'availability':Availability.objects.filter(player=player).select_related('session')})

# Limit the register to the authorized session’s squad.
@login_required
def session_detail(request,pk):
    session=get_object_or_404(TrainingSession,pk=pk)
    if not may_coach(request.user,session.squad_id): return HttpResponseForbidden('Assigned coach access required.')
    players=Player.objects.filter(squad=session.squad,active=True)
    return render(request,'session.html',{'session':session,'players':players,'records':Attendance.objects.filter(session=session).select_related('player')})

# Record actual attendance only after a valid session starts; never derive it from availability.
@login_required
def record_attendance(request,session_id,player_id):
    session=get_object_or_404(TrainingSession,pk=session_id)
    if not may_coach(request.user,session.squad_id): return HttpResponseForbidden('Assigned coach access required.')
    if session.starts_at>timezone.now() or session.status in ('cancelled','postponed'):
        return HttpResponseForbidden('Attendance can be recorded only after a scheduled session starts.')
    player=get_object_or_404(Player,pk=player_id,squad_id=session.squad_id,active=True)
    form=AttendanceForm(request.POST or None,instance=Attendance.objects.filter(session=session,player=player).first())
    if request.method=='POST' and form.is_valid():
        obj=form.save(commit=False);obj.player=player;obj.session=session;obj.recorded_by=request.user;obj.full_clean();obj.save();audit(request.user,'attendance.saved',obj)
        return redirect('session-detail',pk=session.pk)
    return render(request,'form.html',{'title':f'Attendance: {player.display_name}','form':form,'button':'Save attendance'})

# A minimal process check; it does not assert email delivery or full production readiness.
@require_GET
def health(request): return JsonResponse({'status':'ok'})

# Use the linked approved application and a restricted field list to prevent identity or role changes.
@login_required
def profile(request):
    if not approved_player(request.user): return HttpResponseForbidden('Approved player access required.')
    obj=get_object_or_404(Application,user=request.user,status='approved')
    form=ContactProfileForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        form.save();audit(request.user,'profile.contact_updated',obj)
        messages.success(request,'Your contact details and publication preference have been updated.')
        return redirect('dashboard')
    return render(request,'form.html',{'form':form,'title':'My contact details','button':'Save profile'})

# Show participation and privacy guidance without exposing member records.
@require_GET
def policies(request): return render(request,'policies.html')
