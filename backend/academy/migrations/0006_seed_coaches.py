"""Publish the three coach names supplied by the academy owner; create no logins."""
from django.db import migrations


def seed(apps, schema_editor):
    Coach=apps.get_model('academy','CoachProfile')
    for name,nickname in [('Mr. Uduh Chukwuagoziem A.','Smith'),('Mr. Okoro Chigozie F.','Messi'),('Mr. Out Abaju O.','Oracle')]:
        Coach.objects.get_or_create(nickname=nickname,defaults={'name':name})

class Migration(migrations.Migration):
    dependencies=[('academy','0005_coachprofile_academyevent_appointmentrequest_and_more')]
    operations=[migrations.RunPython(seed,migrations.RunPython.noop)]
