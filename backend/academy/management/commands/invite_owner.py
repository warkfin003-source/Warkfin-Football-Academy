"""Create an inactive first owner and submit a private activation email without printing the link."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from academy.models import User, AuditEvent
from academy.owner_activation import eligible, owner_token


class Command(BaseCommand):
    help = 'Email an activation link to the configured first owner; never print credentials.'

    def add_arguments(self, parser):
        parser.add_argument('--resend', action='store_true', help='Invalidate a previous pending link and send a replacement.')

    def handle(self, *args, **options):
        email = settings.OWNER_LOGIN_EMAIL
        try:
            validate_email(email)
        except ValidationError:
            raise CommandError('Configure a valid OWNER_LOGIN_EMAIL.') from None
        if not settings.OWNER_ACTIVATION_ENABLED:
            raise CommandError('Enable OWNER_ACTIVATION_ENABLED before sending an invitation.')
        if not settings.DEBUG and (not settings.EMAIL_READY or not settings.PORTAL_ORIGIN.startswith('https://') or settings.DEFAULT_FROM_EMAIL.endswith('@localhost')):
            raise CommandError('Configure a verified sender, email transport and HTTPS origin first.')
        with transaction.atomic():
            user = User.objects.select_for_update().filter(email__iexact=email).first()
            if user and not eligible(user):
                raise CommandError('This account already exists and cannot be promoted or reset by this command.')
            if User.objects.filter(is_superuser=True).exclude(email__iexact=email).exists():
                raise CommandError('An owner already exists. Do not create another through bootstrap.')
            if user is None:
                user = User(username=email, email=email, is_active=False, email_verified=False, is_staff=True, is_superuser=True)
            elif not options['resend'] and AuditEvent.objects.filter(action='owner.invitation_sent', object_reference=f'user:{user.pk}').exists():
                self.stdout.write('Invitation already submitted. Use --resend only when a replacement is needed.')
                return
            user.set_unusable_password()  # A fresh value invalidates all previous activation links.
            user.save()
            link = settings.PORTAL_ORIGIN + reverse('owner-activate', kwargs={
                'uidb64': urlsafe_base64_encode(force_bytes(user.pk)), 'token': owner_token.make_token(user)})
            try:
                sent = send_mail('Activate your Warkfin Academy owner account',
                    f'Hello Warkfin Emmanuel,\n\nSet your private owner password using this link:\n{link}\n\nThe link expires in one hour and can be used once. Do not forward it. If you did not request this, ignore this message.',
                    settings.DEFAULT_FROM_EMAIL, [email])
                if sent != 1:
                    raise RuntimeError('Email not submitted')
            except Exception:
                raise CommandError('Invitation delivery failed. Check email service settings and retry; no account was activated.') from None
            AuditEvent.objects.create(actor=None, action='owner.invitation_sent', object_reference=f'user:{user.pk}')
        self.stdout.write('Owner activation email submitted. The account remains inactive until the private link is completed.')
