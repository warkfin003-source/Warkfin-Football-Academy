"""Manual transfer reports and owner verification; no payment is moved by these views."""
import hashlib
from decimal import Decimal
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError
from django.shortcuts import render,redirect,get_object_or_404
from django.http import HttpResponseForbidden
from django.utils import timezone
from .models import TransferSettings,TransferClaim,PaymentOrder,User
from .views import owner_required,approved_player,audit
from . import payments


def configuration():
    return TransferSettings.objects.filter(pk=1,enabled=True).exclude(account_name='').exclude(account_number='').exclude(payment_terms='').first()

class SettingsForm(forms.ModelForm):
    account_number=forms.RegexField(regex=r'^[0-9]{10}$',label='Receiving account number',max_length=10)
    confirmed=forms.BooleanField(label='I checked these receiving account details in my banking app.')
    class Meta:
        model=TransferSettings
        fields=['bank_name','account_name','account_number','payment_terms','enabled']

@owner_required
def settings_page(request):
    form=SettingsForm(request.POST or None,instance=TransferSettings.objects.filter(pk=1).first())
    if request.method=='POST' and form.is_valid():
        obj=form.save();audit(request.user,'transfer.settings_updated',obj)
        messages.success(request,'Transfer instructions saved. No money has been moved.')
        return redirect('owner-transfers')
    return render(request,'form.html',{'form':form,'title':'Receiving account & transfer instructions','button':'Save transfer instructions'})

class ReportForm(forms.Form):
    purpose=forms.ChoiceField(choices=[('registration','Registration — ₦5,000'),('dues','Monthly dues — ₦3,000 per month')])
    start_month=forms.DateField(required=False,input_formats=['%Y-%m'],widget=forms.DateInput(attrs={'type':'month'},format='%Y-%m'))
    months=forms.TypedChoiceField(coerce=int,choices=[(n,f'{n} month(s) — ₦{n*3000:,}') for n in payments.MONTH_OPTIONS])
    sender_name=forms.CharField(max_length=160)
    reported_reference=forms.CharField(max_length=120,label='Transaction reference shown on your transfer')
    transfer_date=forms.DateField(widget=forms.DateInput(attrs={'type':'date'}))
    accepted=forms.BooleanField(label='I have read the payment terms and understand this report is not a confirmed payment.')
    def clean_transfer_date(self):
        value=self.cleaned_data['transfer_date']
        if value>timezone.localdate(): raise forms.ValidationError('A transfer date cannot be in the future.')
        return value
    def clean(self):
        data=super().clean()
        if data.get('purpose')=='dues' and not data.get('start_month'): self.add_error('start_month','Select the first dues month.')
        return data

@login_required
def report(request):
    from .member_views import player_fees_apply
    if not request.user.email_verified or not player_fees_apply(request.user):
        return HttpResponseForbidden('A verified player/applicant account is required.')
    config=configuration()
    if not config:
        messages.warning(request,'Receiving account instructions are not available yet. Do not transfer money.')
        return redirect('billing')
    form=ReportForm(request.POST or None,initial={'months':1,'transfer_date':timezone.localdate(),'start_month':timezone.localdate().replace(day=1)})
    if request.method=='POST' and form.is_valid():
        data=form.cleaned_data
        if data['purpose']=='dues' and not approved_player(request.user): return HttpResponseForbidden('Academy acceptance is required for monthly dues.')
        try:
            with transaction.atomic():
                # Serialize reports with all other per-member payment and allocation work.
                User.objects.select_for_update().get(pk=request.user.pk)
                start=data.get('start_month') if data['purpose']=='dues' else None
                if start and (start<request.user.date_joined.date().replace(day=1) or start>payments.month_sequence(timezone.localdate().replace(day=1),13)[-1]):
                    raise ValueError('Choose a month from account creation through the next 12 months.')
                order=payments.make_order(request.user,data['purpose'],start,data['months'] if start else 0)
                if order.purpose!=data['purpose'] or (start and (order.start_month!=start or order.months!=data['months'])):
                    raise ValueError('You already have a different pending payment. Resolve it before reporting another transfer.')
                if order.checkout_url: raise ValueError('An online checkout is pending. Ask the owner to resolve it before reporting a transfer.')
                if TransferClaim.objects.filter(order=order).exists(): raise ValueError('This payment already has a report. Wait for owner review; do not pay again.')
                claim=TransferClaim.objects.create(order=order,sender_name=data['sender_name'],reported_reference=data['reported_reference'],transfer_date=data['transfer_date'],destination=f'{config.bank_name} · {config.account_number} · {config.account_name}',accepted_terms=config.payment_terms)
                audit(request.user,'transfer.reported',claim)
            messages.success(request,'Transfer reported. It remains pending until the owner verifies receipt of funds. Do not pay again.')
            return redirect('billing')
        except ValueError as exc: form.add_error(None,str(exc))
    return render(request,'transfer_report.html',{'form':form,'config':config})

class ReviewForm(forms.Form):
    decision=forms.ChoiceField(choices=[('approved','Confirm funds received'),('declined','Could not verify this transfer')])
    received_amount=forms.DecimalField(required=False,max_digits=12,decimal_places=2,min_value=Decimal('0.01'),label='Amount received (NGN)')
    bank_reference=forms.CharField(required=False,max_length=120,label='Transaction reference from your receiving account')
    note=forms.CharField(required=False,max_length=500,widget=forms.Textarea)
    confirmed=forms.BooleanField(required=False,label='I checked my receiving account and verified the sender, transaction reference and full amount. I am not relying only on a screenshot.')
    def clean(self):
        data=super().clean()
        if data.get('decision')=='approved':
            for key in ['received_amount','bank_reference','confirmed']:
                if not data.get(key): self.add_error(key,'Required to confirm a received payment.')
        elif not data.get('note'): self.add_error('note','Explain why the transfer could not be verified.')
        return data

@owner_required
def queue(request):
    return render(request,'transfer_queue.html',{'claims':TransferClaim.objects.filter(status='pending').select_related('order__user').order_by('created_at'),'configured':bool(configuration())})

@owner_required
def review(request,pk):
    claim=get_object_or_404(TransferClaim.objects.select_related('order__user'),pk=pk)
    form=ReviewForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        try:
            with transaction.atomic():
                User.objects.select_for_update().get(pk=claim.order.user_id)
                claim=TransferClaim.objects.select_for_update().select_related('order').get(pk=pk)
                if claim.status!='pending':
                    messages.info(request,'This report has already been reviewed.');return redirect('owner-transfers')
                data=form.cleaned_data
                if data['decision']=='approved':
                    if data['received_amount']*100!=claim.order.amount_kobo: raise ValueError('The received amount must match this payment in full. Resolve any difference before approving.')
                    reference=data['bank_reference'].strip().upper()
                    # A normalized digest reserves the bank reference across all members.
                    key='manual:'+hashlib.sha256(reference.encode()).hexdigest()
                    if PaymentOrder.objects.filter(provider_reference=key).exclude(pk=claim.order_id).exists(): raise ValueError('That bank transaction has already been credited.')
                    payments.settle(claim.order,{'orderId':claim.order.reference.hex,'currency':'NGN','amount':claim.order.amount_kobo,'orderNo':key,'orderStatus':2},manual_actor=request.user)
                    claim.verified_reference=reference
                else:
                    PaymentOrder.objects.filter(pk=claim.order_id,status='pending').update(status='closed')
                claim.status=data['decision'];claim.review_note=data['note'];claim.reviewed_by=request.user;claim.reviewed_at=timezone.now();claim.save()
                audit(request.user,'transfer.'+claim.status,claim)
            messages.success(request,'Review saved. Verified payments now appear in the member’s receipts.')
            return redirect('owner-transfers')
        except (ValueError,IntegrityError) as exc:
            form.add_error(None,str(exc) if isinstance(exc,ValueError) else 'This transaction or dues period has already been credited. Recheck the records.')
    return render(request,'transfer_review.html',{'claim':claim,'form':form})
