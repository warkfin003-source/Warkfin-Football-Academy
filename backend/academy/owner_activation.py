"""Email-confirmed first-owner activation, using Django's password token flow."""
from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib.auth.views import PasswordResetConfirmView, INTERNAL_RESET_SESSION_TOKEN
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import render
from .models import User, AuditEvent


class OwnerActivationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = 'academy.owner-activation'

    def _make_hash_value(self, user, timestamp):
        return super()._make_hash_value(user, timestamp) + str(user.is_active) + str(user.email_verified)


owner_token = OwnerActivationTokenGenerator()


def eligible(user):
    return bool(user and settings.OWNER_LOGIN_EMAIL and
                user.email.lower() == settings.OWNER_LOGIN_EMAIL and
                user.is_superuser and user.is_staff and not user.is_active and
                not user.email_verified and not user.has_usable_password())


class OwnerActivationView(PasswordResetConfirmView):
    token_generator = owner_token
    template_name = 'registration/owner_activate.html'
    title = 'Activate your owner account'

    def get_user(self, uidb64):
        user = super().get_user(uidb64)
        return user if eligible(user) else None

    def form_valid(self, form):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=self.user.pk)
            token = self.request.session.get(INTERNAL_RESET_SESSION_TOKEN)
            if not eligible(user) or not owner_token.check_token(user, token):
                return HttpResponseForbidden('This activation link is no longer valid.')
            form.user = user
            user = form.save(commit=False)
            user.is_active = True
            user.email_verified = True
            user.save()
            AuditEvent.objects.create(actor=user, action='owner.activated', object_reference=f'user:{user.pk}')
        self.request.session.pop(INTERNAL_RESET_SESSION_TOKEN, None)
        self.request.session.cycle_key()
        return render(self.request, 'notice.html', {
            'title': 'Your owner account is activated',
            'text': 'Your password is set and your email is verified. The portal remains closed until its remaining launch checks are complete. Keep your password private.'})
