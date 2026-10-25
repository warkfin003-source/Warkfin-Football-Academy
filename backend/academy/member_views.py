"""Private member payments, appointments, notifications and calendar exports."""
import calendar
import hashlib
import json
from datetime import date, datetime, timedelta, timezone as dt_timezone
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import (PaymentOrder, DuesMonth, CoachProfile, AcademyEvent, AppointmentRequest,
                     NotificationRead, TrainingSession, Announcement, Application)
from .views import approved_player
from . import payments


class DuesForm(forms.Form):
    start_month = forms.DateField(input_formats=['%Y-%m'], widget=forms.DateInput(attrs={'type':'month'},format='%Y-%m'))
    months = forms.TypedChoiceField(coerce=int, choices=[(n,f'{n} month'+('s' if n>1 else '')+f' — ₦{n*3000:,}') for n in payments.MONTH_OPTIONS])


@login_required
def billing(request):
    # Queries are always bound to the signed-in member, never a submitted user ID.
    return render(request,'billing.html',{'orders':PaymentOrder.objects.filter(user=request.user).order_by('-created_at'),
        'dues':DuesMonth.objects.filter(user=request.user).select_related('payment'),
        'paid':payments.registration_paid(request.user),'ready':payments.ready(),
        'dues_form':DuesForm(initial={'start_month':timezone.localdate().replace(day=1)}),
        'can_pay_dues':bool(approved_player(request.user)), 'terms':settings.PAYMENT_TERMS})


@login_required
@require_POST
def checkout(request):
    if not request.user.email_verified: return HttpResponseForbidden('Verify your email first.')
    if not payments.ready():
        messages.warning(request,'Online payment is awaiting activation. Do not transfer money yet.')
        return redirect('billing')
    if request.POST.get('terms')!='yes':
        messages.error(request,'Read and accept the payment terms before continuing.')
        return redirect('billing')
    purpose=request.POST.get('purpose')
    start=None; months=0
    if purpose=='dues':
        if not approved_player(request.user): return HttpResponseForbidden('Academy acceptance is required before dues payment.')
        form=DuesForm(request.POST)
        if not form.is_valid():
            messages.error(request,'Choose a valid starting month and payment period.'); return redirect('billing')
        start=form.cleaned_data['start_month'];months=form.cleaned_data['months']
        today=timezone.localdate().replace(day=1)
        if start < request.user.date_joined.date().replace(day=1) or start > payments.month_sequence(today,13)[-1]:
            messages.error(request,'Choose a month from account creation through the next 12 months.');return redirect('billing')
    try:
        order=payments.make_order(request.user,purpose,start,months)
        return redirect(payments.start_checkout(order))
    except (payments.PaymentUnavailable, ValueError) as exc:
        messages.error(request,str(exc));return redirect('billing')


@login_required
@require_POST
def refresh_payment(request,pk):
    order=get_object_or_404(PaymentOrder,pk=pk,user=request.user)
    try:
        if order.status!='paid': payments.reconcile(order)
        messages.info(request,'Payment status checked. Receipts appear only for verified successful payments.')
    except (payments.PaymentUnavailable, ValueError):
        messages.warning(request,'We could not confirm this payment yet. Do not pay again until its status is resolved.')
    return redirect('billing')


@csrf_exempt
@require_POST
def payment_callback(request):
    # CSRF is replaced here only by provider signature, app ID and independent requery.
    if not payments.ready(): return HttpResponse('unavailable',status=503)
    if len(request.body)>16384: return HttpResponse('invalid',status=400)
    try:
        data=json.loads(request.body)
        if not isinstance(data,dict) or data.get('appId')!=settings.PALMPAY_APP_ID or not payments.verify_signature(data):
            return HttpResponse('invalid',status=403)
        order=get_object_or_404(PaymentOrder,reference=data.get('orderId'))
        payments.reconcile(order)
        return HttpResponse('success',content_type='text/plain')
    except (ValueError, TypeError, ValidationError, payments.PaymentUnavailable): return HttpResponse('unconfirmed',status=400)


@login_required
def receipt(request,pk):
    # A payment receipt is never an admission letter. Both require their own evidence.
    order=get_object_or_404(PaymentOrder,pk=pk,user=request.user,status='paid')
    coverage=None
    if request.GET.get('month'):
        if not request.GET['month'].isdigit(): return HttpResponse(status=404)
        coverage=get_object_or_404(DuesMonth,pk=request.GET['month'],payment=order,user=request.user)
    return render(request,'receipt.html',{'order':order,'coverage':coverage,
        'application':Application.objects.filter(user=request.user,status='approved').first()})


@login_required
def acceptance(request):
    application=get_object_or_404(Application,user=request.user,status='approved')
    if not payments.registration_paid(request.user): return HttpResponseForbidden('A verified registration payment is required for this slip.')
    return render(request,'acceptance.html',{'application':application,'player':approved_player(request.user)})


def visible_sessions(user):
    if user.is_superuser: return TrainingSession.objects.all()
    if user.email_verified and user.coached_squads.exists(): return TrainingSession.objects.filter(squad__coaches=user).distinct()
    player=approved_player(user)
    return TrainingSession.objects.filter(squad=player.squad) if player and player.squad_id else TrainingSession.objects.none()


def visible_events(user):
    if user.is_superuser: return AcademyEvent.objects.filter(published=True)
    if not user.email_verified: return AcademyEvent.objects.none()
    personal=Q(recipient=user)
    player=approved_player(user)
    if player or user.coached_squads.exists():
        squads=list(user.coached_squads.values_list('id',flat=True))
        if player and player.squad_id: squads.append(player.squad_id)
        personal |= Q(recipient__isnull=True) & (Q(squad__isnull=True)|Q(squad_id__in=squads))
    return AcademyEvent.objects.filter(personal,published=True).distinct()


def visible_announcements(user):
    if user.is_superuser: return Announcement.objects.filter(published=True)
    player=approved_player(user)
    if not user.email_verified or (not player and not user.coached_squads.exists()): return Announcement.objects.none()
    squads=list(user.coached_squads.values_list('id',flat=True))
    if player and player.squad_id: squads.append(player.squad_id)
    return Announcement.objects.filter(Q(squad__isnull=True)|Q(squad_id__in=squads),published=True)


@login_required
def calendar_page(request):
    try: month=datetime.strptime(request.GET.get('month',''),'%Y-%m').date().replace(day=1)
    except ValueError: month=timezone.localdate().replace(day=1)
    if month.year<2000 or month.year>2099: month=timezone.localdate().replace(day=1)
    scope=request.GET.get('scope','all')
    if scope not in ('all','private','shared'): scope='all'
    event_query=visible_events(request.user)
    if scope=='private': event_query=event_query.filter(recipient=request.user)
    elif scope=='shared': event_query=event_query.filter(recipient__isnull=True)
    events=list(event_query.filter(starts_at__year=month.year,starts_at__month=month.month).order_by('starts_at'))
    sessions=[] if scope=='private' else list(visible_sessions(request.user).filter(starts_at__year=month.year,starts_at__month=month.month).order_by('starts_at'))
    cells=[]
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(month.year,month.month):
        cells.append([{'date':d,'current':d.month==month.month,
            'items':[{'title':e.title,'time':e.starts_at} for e in events+sessions if timezone.localtime(e.starts_at).date()==d]} for d in week])
    return render(request,'calendar.html',{'scope':scope,'month':month,'weeks':cells,'events':events,'sessions':sessions,
        'previous':(month-timedelta(days=1)).strftime('%Y-%m'), 'next':payments.month_sequence(month,2)[-1].strftime('%Y-%m')})


def ics_text(value):
    # Escape user-editable text so it cannot inject calendar properties.
    return str(value).replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')


@login_required
def calendar_export(request,kind,pk):
    if kind=='session':
        item=get_object_or_404(visible_sessions(request.user),pk=pk)
        end=item.starts_at+timedelta(hours=2)
        location=item.venue+(' (unconfirmed)' if not item.venue_confirmed else '')
        details=item.instructions+'\nEnd time is an estimated two-hour calendar block. Check latest updates.'
        cancelled=item.status in ('cancelled','postponed')
    elif kind=='event':
        item=get_object_or_404(visible_events(request.user),pk=pk)
        end=item.ends_at;location=item.location;details=item.details;cancelled=False
    else: return HttpResponse(status=404)
    stamp=lambda d:d.astimezone(dt_timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Warkfin Academy//Member Calendar//EN','BEGIN:VEVENT',
        f'UID:{kind}-{pk}@warkfin-academy',f'DTSTAMP:{stamp(timezone.now())}',f'DTSTART:{stamp(item.starts_at)}',f'DTEND:{stamp(end)}',
        'SUMMARY:'+ics_text(item.title),'LOCATION:'+ics_text(location),'DESCRIPTION:'+ics_text(details),
        'STATUS:'+('CANCELLED' if cancelled else 'CONFIRMED'),'BEGIN:VALARM','TRIGGER:-PT1H','ACTION:DISPLAY',
        'DESCRIPTION:Academy event reminder','END:VALARM','END:VEVENT','END:VCALENDAR']
    # RFC 5545 lines are folded on UTF-8 byte boundaries, not Python character counts.
    folded=[]
    for line in lines:
        chunk=''
        for char in line:
            if len((chunk+char).encode())>73: folded.append(chunk);chunk=' '
            chunk+=char
        folded.append(chunk)
    response=HttpResponse('\r\n'.join(folded)+'\r\n',content_type='text/calendar; charset=utf-8')
    response['Content-Disposition']='attachment; filename="warkfin-event.ics"'
    return response


def notification_items(user):
    items=[]
    for a in visible_announcements(user).order_by('-created_at')[:30]:
        items.append({'key':f'news:{a.pk}','title':a.title,'body':a.body})
    for e in visible_events(user).filter(ends_at__gte=timezone.now()).order_by('starts_at')[:30]:
        items.append({'key':f'event:{e.pk}:{int(e.updated_at.timestamp())}','title':e.title,'body':f'{timezone.localtime(e.starts_at):%d %b %Y, %H:%M} WAT · {e.location}'})
    for s in visible_sessions(user).filter(starts_at__gte=timezone.now()).order_by('starts_at')[:20]:
        items.append({'key':f'training:{s.pk}:{s.status}:{int(s.starts_at.timestamp())}','title':s.title,
            'body':f'{timezone.localtime(s.starts_at):%d %b %Y, %H:%M} WAT · {s.venue} · {s.get_status_display()}'})
    for a in AppointmentRequest.objects.filter(user=user).order_by('-created_at')[:20]:
        items.append({'key':f'appointment:{a.pk}:{a.status}','title':f'Appointment with {a.coach.nickname}: {a.get_status_display()}', 'body':a.reply or {'pending':'Your request is awaiting review. This is not a confirmed appointment.', 'confirmed':'Your appointment is confirmed. Check your private calendar for the agreed details.', 'declined':'This appointment request was declined. You can request another suitable time.'}[a.status]})
    coach_app=getattr(user,'coach_application',None)
    if user.email_verified and not user.is_superuser and not user.coached_squads.exists() and not coach_app and not payments.registration_paid(user):
        items.append({'key':'registration-fee','title':'Registration fee: ₦5,000','body':'Registration cannot be completed until payment is verified. Online payments are awaiting activation.' if not payments.ready() else 'Open Payments & receipts to complete your registration fee.'})
    if approved_player(user) and not DuesMonth.objects.filter(user=user,month=timezone.localdate().replace(day=1)).exists():
        items.append({'key':'dues:'+timezone.localdate().strftime('%Y-%m'),'title':'Monthly dues: ₦3,000','body':'No verified payment is recorded for this month. Check Payments & receipts.'})
    # Review decisions are private, actionable updates, never public announcements.
    if coach_app:
        items.append({'key':f'coach-review:{coach_app.pk}:{coach_app.status}',
            'title':f'Coach profile: {coach_app.get_status_display()}',
            'body':coach_app.review_note or 'Open your coach profile to view its review status and next steps.'})
    application=Application.objects.filter(user=user).first()
    if application:
        items.append({'key':f'player-review:{application.pk}:{application.status}',
            'title':f'Player application: {application.get_status_display()}',
            'body':'Open your application to view the decision and any corrections requested.'})
    destinations={'news':('dashboard','View academy news'), 'event':('calendar','Open my calendar'),
        'training':('calendar','View training schedule'), 'appointment':('coaches','View appointment'),
        'coach-review':('coach-apply','View coach profile'), 'player-review':('application','View application'),
        'registration-fee':('billing','View payment status'), 'dues':('billing','View dues & receipts')}
    for item in items:
        # A changed message becomes unread again, including edits that keep its status.
        revision=hashlib.sha256((item['title']+'\n'+item['body']).encode()).hexdigest()[:16]
        kind=item['key'].split(':')[0]
        item['key']+=':'+revision
        route,item['action']=destinations[kind]
        item['url']=reverse(route)
    seen=set(NotificationRead.objects.filter(user=user).values_list('key',flat=True))
    for item in items: item['read']=item['key'] in seen
    return items


@login_required
def notifications(request):
    items=notification_items(request.user)
    scope=request.GET.get('status','all')
    if scope not in ('all','unread','read'): scope='all'
    if request.method=='POST':
        # Only currently authorized items can be marked; ignore supplied foreign keys.
        if request.POST.get('action')=='mark-all':
            NotificationRead.objects.bulk_create([
                NotificationRead(user=request.user,key=item['key']) for item in items if not item['read']
            ],ignore_conflicts=True)
            messages.success(request,'Your current notifications are marked as read.')
        else:
            key=request.POST.get('key')
            if key in {i['key'] for i in items}: NotificationRead.objects.get_or_create(user=request.user,key=key)
        return redirect(reverse('notifications')+'?status='+scope)
    unread=sum(not item['read'] for item in items)
    displayed=[i for i in items if scope=='all' or i['read']==(scope=='read')]
    return render(request,'notifications.html',{'items':displayed,'scope':scope,'unread':unread,'total':len(items)})


class AppointmentForm(forms.ModelForm):
    class Meta:
        model=AppointmentRequest
        fields=['coach','requested_at','topic']
        widgets={'requested_at':forms.DateTimeInput(attrs={'type':'datetime-local'})}
    def clean_requested_at(self):
        value=self.cleaned_data['requested_at']
        if value<=timezone.now(): raise forms.ValidationError('Choose a future date and time (WAT).')
        return value


@login_required
def coaches(request):
    player=approved_player(request.user)
    form=AppointmentForm(request.POST or None)
    form.fields['coach'].queryset=CoachProfile.objects.filter(active=True)
    if request.method=='POST':
        if not player: return HttpResponseForbidden('Approved player access required.')
        if AppointmentRequest.objects.filter(user=request.user,status='pending').count()>=3:
            messages.warning(request,'You already have three requests awaiting review.')
        elif form.is_valid():
            obj=form.save(commit=False);obj.user=request.user;obj.save()
            messages.success(request,'Appointment requested. Please wait for confirmation.');return redirect('coaches')
    return render(request,'coaches.html',{'coaches':CoachProfile.objects.filter(active=True),'form':form,'player':player,
        'appointments':AppointmentRequest.objects.filter(user=request.user).select_related('coach').order_by('-created_at')[:20]})
