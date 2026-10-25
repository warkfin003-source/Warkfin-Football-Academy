"""Coach self-registration and owner-controlled squad assignments."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from .models import CoachApplication, Squad
from .views import owner_required, audit

class CoachForm(forms.ModelForm):
    class Meta:
        model=CoachApplication
        fields=('full_name','phone','experience','availability','conduct_accepted')
        widgets={'experience':forms.Textarea,'availability':forms.Textarea}
    def clean_conduct_accepted(self):
        if not self.cleaned_data['conduct_accepted']:
            raise forms.ValidationError('Accept the coaching code of conduct to continue.')
        return True

class CoachReviewForm(forms.Form):
    decision=forms.ChoiceField(choices=[('approved','Approve'),('correction','Request correction'),('declined','Decline')])
    squads=forms.ModelMultipleChoiceField(queryset=Squad.objects.all(),required=False)
    review_note=forms.CharField(max_length=500,required=False,widget=forms.Textarea)
    def clean(self):
        data=super().clean()
        if data.get('decision')=='approved' and not data.get('squads'):
            self.add_error('squads','Assign at least one squad.')
        return data

@login_required
def apply(request):
    # An application never grants permissions. Private fields come from an explicit allowlist.
    if not request.user.email_verified:
        messages.warning(request,'Verify your email from your dashboard before coach registration.')
        return redirect('dashboard')
    existing=CoachApplication.objects.filter(user=request.user).first()
    if existing and existing.status in ('pending','approved','declined'):
        return render(request,'coach_application.html',{'application':existing})
    form=CoachForm(request.POST or None,instance=existing)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            # Serialize submissions for a single identity, including simultaneous browser tabs.
            from .models import User
            User.objects.select_for_update().get(pk=request.user.pk)
            current=CoachApplication.objects.filter(user=request.user).first()
            if current and current.status!='correction': return redirect('coach-apply')
            obj=form.save(commit=False);obj.user=request.user;obj.status='pending';obj.review_note='';obj.save()
            audit(request.user,'coach.application_submitted',obj)
        messages.success(request,'Coach profile submitted. Coaching access awaits owner approval.')
        return redirect('coach-apply')
    return render(request,'coach_application.html',{'form':form,'application':existing})

@owner_required
def review(request,pk):
    obj=get_object_or_404(CoachApplication,pk=pk)
    form=CoachReviewForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            obj=CoachApplication.objects.select_for_update().select_related('user').get(pk=pk)
            if obj.status=='approved':
                messages.info(request,'Already approved. Manage squad assignments in the owner workspace.')
                return redirect('dashboard')
            if not obj.user.email_verified: return HttpResponseForbidden('Verify coach email first.')
            obj.status=form.cleaned_data['decision'];obj.review_note=form.cleaned_data['review_note'];obj.save()
            if obj.status=='approved':
                # Grant only assigned-squad coaching; never staff, superuser or financial access.
                for squad in form.cleaned_data['squads']: squad.coaches.add(obj.user)
            audit(request.user,'coach.'+obj.status,obj)
        messages.success(request,'Coach application review saved.')
        return redirect('dashboard')
    return render(request,'coach_review.html',{'application':obj,'form':form})

@login_required
def edit_profile(request):
    # Existing coaches can update contact/experience, never approval or squad access.
    if not request.user.email_verified: return HttpResponseForbidden('Verify your email first.')
    obj=get_object_or_404(CoachApplication,user=request.user,status='approved')
    form=CoachForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        obj=form.save();audit(request.user,'coach.profile_updated',obj)
        messages.success(request,'Your private coaching profile has been updated.')
        return redirect('coach-apply')
    return render(request,'form.html',{'title':'Edit my coaching profile','form':form,'button':'Save profile'})
