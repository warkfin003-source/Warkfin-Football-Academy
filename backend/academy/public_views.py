"""Anonymous schedule exposes only explicitly public, unrestricted event records."""
from django.shortcuts import render
from django.utils import timezone
from .models import AcademyEvent

def schedule(request):
    events=AcademyEvent.objects.filter(public=True,published=True,recipient__isnull=True,squad__isnull=True,ends_at__gte=timezone.now()).order_by('starts_at')[:50]
    return render(request,'public_schedule.html',{'events':events})
