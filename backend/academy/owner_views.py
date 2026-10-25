"""Owner operations, private configuration checks and explicit refund reconciliation."""
from django import forms
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .models import User, Player, Squad, Application, CoachApplication, TrainingSession, PaymentOrder, RegistrationRefund, AppointmentRequest, AuditEvent
from .views import owner_required, audit
from .payments import ready

@owner_required
def workspace(request):
    # Counts come from real records. No private credentials or provider balances are exposed.
    cards=[('Active players',Player.objects.filter(active=True).count(),'/admin/academy/player/'),
           ('Squads',Squad.objects.count(),'/admin/academy/squad/'),
           ('Player applications',Application.objects.filter(status='pending').count(),'/#reviews'),
           ('Coach applications',CoachApplication.objects.filter(status='pending').count(),'/#reviews'),
           ('Upcoming sessions',TrainingSession.objects.filter(status='scheduled',starts_at__gte=timezone.now()).count(),'/admin/academy/trainingsession/'),
           ('Appointments to review',AppointmentRequest.objects.filter(status='pending').count(),'/admin/academy/appointmentrequest/')]
    total=PaymentOrder.objects.filter(status='paid').aggregate(total=Sum('amount_kobo'))['total'] or 0
    return render(request,'owner_workspace.html',{'cards':cards,'gross_paid':total/100,
        'refunds':RegistrationRefund.objects.select_related('payment__user').exclude(status='refunded').order_by('requested_at'),
        'applications':Application.objects.filter(status='pending')[:30],
        'coach_applications':CoachApplication.objects.filter(status='pending')[:30],
        'recent_actions':AuditEvent.objects.order_by('-created_at')[:12],
        'gateway_ready':ready()})

@owner_required
def setup(request):
    checks=[('Merchant App ID',bool(settings.PALMPAY_APP_ID)),('Private signing key',bool(settings.PALMPAY_PRIVATE_KEY)),
        ('Provider verification key',bool(settings.PALMPAY_PUBLIC_KEY)),('Checkout host allowlist',any(settings.PALMPAY_CHECKOUT_HOSTS)),
        ('Full checkout terms',bool(settings.PAYMENT_TERMS)),('Collection enabled',settings.PALMPAY_ENABLED)]
    return render(request,'owner_setup.html',{'checks':checks,'gateway_ready':ready()})

class RefundForm(forms.Form):
    status=forms.ChoiceField(choices=[('processing','Processing outside the portal'),('refunded','Record completed external refund')])
    reference=forms.CharField(max_length=120,required=False,label='Provider refund transaction reference')
    confirmed=forms.BooleanField(required=False,label='I checked the provider record and confirm the full registration payment has been returned.')
    def clean(self):
        data=super().clean()
        if data.get('status')=='refunded':
            if not data.get('reference'): self.add_error('reference','Enter the provider refund reference.')
            if not data.get('confirmed'): self.add_error('confirmed','Verify the refund before confirming.')
        return data

@owner_required
def refund(request,pk):
    obj=get_object_or_404(RegistrationRefund.objects.select_related('payment__user'),pk=pk)
    form=RefundForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            obj=RegistrationRefund.objects.select_for_update().get(pk=pk)
            if obj.status=='refunded':
                messages.info(request,'This completed refund record is locked.')
                return redirect('owner-workspace')
            obj.status=form.cleaned_data['status']
            if obj.status=='refunded':
                obj.refund_reference=form.cleaned_data['reference'];obj.completed_at=timezone.now();obj.recorded_by=request.user
            obj.save();audit(request.user,'refund.'+obj.status,obj)
        messages.success(request,'Refund record updated. This action does not move money.')
        return redirect('owner-workspace')
    return render(request,'owner_refund.html',{'refund':obj,'form':form})
