from datetime import date
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.utils import timezone
from .models import User, Application, Player, Squad, Availability, Attendance, Feedback

class SignUpForm(UserCreationForm):
    email = forms.EmailField()
    class Meta:
        model = User
        fields = ('email',)
    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account already exists. Use login or password recovery.')
        return email
    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email = self.cleaned_data['email']
        if commit: user.save()
        return user

class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(label='Email address')
    def clean_username(self): return self.cleaned_data['username'].strip().lower()

class ApplicationForm(forms.ModelForm):
    rules_accepted = forms.BooleanField(label='I agree to the academy participation rules.')
    privacy_accepted = forms.BooleanField(label='I have read the privacy notice.')
    class Meta:
        model = Application
        exclude = ('user','status','review_note','consent_version','submitted_at','updated_at')
        widgets = {'date_of_birth': forms.DateInput(attrs={'type':'date'})}
    def clean(self):
        data = super().clean()
        dob = data.get('date_of_birth')
        today = timezone.localdate()
        if dob and (today.year-dob.year-((today.month,today.day)<(dob.month,dob.day))) < 18:
            self.add_error('date_of_birth','This initial portal accepts adults aged 18 and above. Contact the academy for other enquiries.')
        required = {'student':['institution','faculty','department','course','level'], 'graduate':['institution','qualification','course','graduation_year']}.get(data.get('kind'), [])
        for field in required:
            if not data.get(field): self.add_error(field,'Required for your selected applicant category.')
        year=data.get('graduation_year')
        if year and not 1950 <= year <= today.year:
            self.add_error('graduation_year','Enter a completed graduation year.')
        return data

class ReviewForm(forms.Form):
    decision = forms.ChoiceField(choices=[('approved','Approve'),('correction','Request correction'),('declined','Decline')])
    squad = forms.ModelChoiceField(queryset=Squad.objects.all(), required=False)
    existing_player = forms.ModelChoiceField(queryset=Player.objects.filter(user__isnull=True), required=False, help_text='Select an existing directory record only after privately verifying the applicant’s identity.')
    review_note = forms.CharField(max_length=500, required=False, widget=forms.Textarea)
    def clean(self):
        data=super().clean()
        if data.get('decision')=='approved' and not data.get('squad'):
            self.add_error('squad','Select the squad for this player.')
        return data

class AvailabilityForm(forms.ModelForm):
    class Meta:
        model=Availability
        fields=('response','private_note')

class ContactProfileForm(forms.ModelForm):
    class Meta:
        model=Application
        fields=('phone','emergency_name','emergency_relationship','emergency_phone','media_consent')

class AttendanceForm(forms.ModelForm):
    class Meta:
        model=Attendance
        fields=('status',)

class FeedbackForm(forms.ModelForm):
    class Meta:
        model=Feedback
        fields=('goal','message','shared_with_player')
