"""Launch controls, account-request throttling and response privacy headers."""
from django.conf import settings
from django.shortcuts import render
import hashlib
from datetime import timedelta
from django.http import HttpResponse
from django.db.models import F
from django.utils import timezone
from .models import RateBucket

class PortalMiddleware:
    def __init__(self, get_response): self.get_response=get_response
    def __call__(self, request):
        if request.method=='POST' and (request.path.startswith('/accounts/') or request.path=='/admin/login/'):
            # REMOTE_ADDR must be set by a trusted ingress. Do not trust client X-Forwarded-For.
            now=timezone.now()
            keys=[('ip',request.META.get('REMOTE_ADDR','unknown'),30)]
            identity=request.POST.get('username',request.POST.get('email','')).strip().lower()
            if identity: keys.append(('account',identity,10))
            for kind,value,limit in keys:
                key=hashlib.sha256(f'{kind}:{request.path}:{value}:{int(now.timestamp())//900}'.encode()).hexdigest()
                RateBucket.objects.get_or_create(key=key,defaults={'expires_at':now+timedelta(minutes=30)})
                RateBucket.objects.filter(key=key).update(count=F('count')+1)
                if RateBucket.objects.get(key=key).count>limit:
                    response=HttpResponse('Too many attempts. Please wait 15 minutes and try again.',status=429)
                    response['Retry-After']='900'
                    response['Cache-Control']='no-store'
                    return response
        response=self.get_response(request)
        response['Cache-Control']='private, no-store'
        response['Content-Security-Policy']="default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
        return response


class LaunchGateMiddleware:
    """Keep all account and data routes closed during infrastructure setup."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        activation = settings.OWNER_ACTIVATION_ENABLED and request.path.startswith('/accounts/owner-activate/')
        if not settings.PORTAL_ENABLED and request.path != '/health/' and not activation:
            response = render(request, 'launch_pending.html', status=503)
            response['Cache-Control'] = 'no-store'
            response['Retry-After'] = '3600'
            response['X-Robots-Tag'] = 'noindex, nofollow'
            response['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
            return response
        return self.get_response(request)
