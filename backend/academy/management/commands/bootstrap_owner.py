from getpass import getpass
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from academy.models import User

class Command(BaseCommand):
    help='Create the first owner interactively. Never pass a password as a command argument.'
    def add_arguments(self,parser): parser.add_argument('--email',required=True)
    def handle(self,*args,**options):
        if User.objects.filter(is_superuser=True).exists(): raise CommandError('An owner already exists. Use the existing owner to manage staff.')
        email=options['email'].strip().lower()
        try: validate_email(email)
        except ValidationError as exc: raise CommandError(str(exc))
        if User.objects.filter(email__iexact=email).exists(): raise CommandError('Account already exists. Do not silently promote an applicant.')
        password=getpass('Owner password (at least 12 characters): ')
        if password!=getpass('Confirm password: '): raise CommandError('Passwords do not match.')
        user=User(username=email,email=email,email_verified=True,is_superuser=True,is_staff=True)
        try: validate_password(password,user)
        except ValidationError as exc: raise CommandError(str(exc))
        user.set_password(password);user.save()
        self.stdout.write('Owner created. Keep your credentials private.')
