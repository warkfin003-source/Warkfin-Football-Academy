"""Admission denial and player suspension apply to fresh and existing sessions."""
from .models import Application, Player

def portal_blocked(user):
    if not user or not user.is_authenticated or user.is_superuser:
        return False
    if Application.objects.filter(user=user, status='declined').exists():
        return True
    if Player.objects.filter(user=user, active=False).exists():
        return True
    return False
