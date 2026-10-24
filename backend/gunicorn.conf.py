"""Optional, explicitly enabled owner invitation before workers start.

Run in the master process once per start, never per request or per worker.
A provider outage must not stop the web server. Invitation records suppress
repeat sends; disable OWNER_INVITE_ON_START after the first successful attempt.
"""
import os


def on_starting(server):
    """Attempt the private invitation only when the operator enables both flags."""
    # Optional read-only readiness check: no messages, purchases or secrets in logs.
    if os.environ.get('OWNER_MFA_METHOD') == 'sms':
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        try:
            import django
            django.setup()
            from django.core.management import call_command
            call_command('check_sms_provider')
        except Exception:
            server.log.warning('SMS readiness check unavailable; web server will continue.')
    if os.environ.get('OWNER_INVITE_ON_START') != '1':
        return
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        import django
        django.setup()
        from django.conf import settings
        from django.core.management import call_command
        from academy.models import User, AuditEvent
        from django.utils.dateparse import parse_datetime
        from django.utils.timezone import is_aware
        if not settings.OWNER_ACTIVATION_ENABLED:
            server.log.warning('Owner invitation skipped: activation is disabled.')
            return
        # Never reset or promote an existing active identity during a restart.
        if User.objects.filter(email__iexact=settings.OWNER_LOGIN_EMAIL, is_active=True).exists():
            server.log.info('Owner invitation skipped: account already active.')
            return
        # An operator can request one replacement using an ISO timestamp. The
        # successful invitation audit prevents repeats on subsequent restarts.
        resend = False
        requested = os.environ.get('OWNER_INVITE_RESEND_AFTER', '')
        if requested:
            cutoff = parse_datetime(requested)
            if cutoff is None or not is_aware(cutoff):
                server.log.error('Owner invitation skipped: invalid resend timestamp.')
                return
            owner = User.objects.filter(email__iexact=settings.OWNER_LOGIN_EMAIL).first()
            if owner:
                latest = AuditEvent.objects.filter(
                    action='owner.invitation_sent', object_reference=f'user:{owner.pk}'
                ).order_by('-created_at').first()
                resend = latest is not None and latest.created_at < cutoff
        call_command('invite_owner', resend=resend)
    except Exception:
        # The transport emits a safe HTTP classification separately. No traceback
        # here: exception messages can contain credentials or activation links.
        server.log.error('Owner invitation was not completed. Web server will continue; inspect safe email diagnostics.')
    finally:
        # Never let forked workers inherit the master's database connection.
        from django.db import connections
        connections.close_all()
