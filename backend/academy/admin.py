"""Owner-only administration with audit events and restricted deletion/review operations."""
from django.contrib import admin
from django.shortcuts import redirect
from .mfa import owner_verified
from django.contrib.auth.admin import UserAdmin
from .models import User, Squad, Player, Application, TrainingSession, Announcement, AuditEvent

# Staff status alone must never grant entry to the owner administration site.
class OwnerAdminSite(admin.AdminSite):
    site_header='Warkfin Academy · Owner administration'
    site_title='Warkfin Academy'
    index_title='Academy management'
    def has_permission(self,request): return request.user.is_active and request.user.is_superuser and owner_verified(request)
    def login(self, request, extra_context=None):
        return redirect('/accounts/login/?next=/admin/')

site=OwnerAdminSite(name='owner_admin')
# Record permitted changes and disable routine deletion to preserve relationships.
class LoggedAdmin(admin.ModelAdmin):
    def save_model(self,request,obj,form,change):
        super().save_model(request,obj,form,change)
        AuditEvent.objects.create(actor=request.user,action='admin.updated' if change else 'admin.created',object_reference=f'{obj._meta.model_name}:{obj.pk}')
    def has_delete_permission(self,request,obj=None): return False

class AcademyUserAdmin(UserAdmin):
    fieldsets=UserAdmin.fieldsets+(("Email verification",{'fields':('email_verified',)}),)
    add_fieldsets=UserAdmin.add_fieldsets+(("Email",{'fields':('email',)}),)
    def save_model(self,request,obj,form,change):
        obj.email=obj.email.strip().lower();obj.username=obj.email
        super().save_model(request,obj,form,change)
        AuditEvent.objects.create(actor=request.user,action='account.updated',object_reference=f'user:{obj.pk}')
    def has_delete_permission(self,request,obj=None): return False

class PlayerAdmin(LoggedAdmin):
    list_display=('directory_number','display_name','positions','squad','active')
    search_fields=('display_name',)
    list_filter=('squad','active')

# Approval belongs in the transactional review workflow, not unrestricted admin editing.
class ApplicationAdmin(admin.ModelAdmin):
    list_display=('full_name','status','submitted_at')
    readonly_fields=tuple(f.name for f in Application._meta.fields)
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
    def has_change_permission(self,request,obj=None): return False

# Audit records are read-only in the admin interface.
class AuditAdmin(admin.ModelAdmin):
    list_display=('created_at','actor','action','object_reference')
    readonly_fields=('created_at','actor','action','object_reference')
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False

site.register(User,AcademyUserAdmin)
site.register(Player,PlayerAdmin)
site.register(Application,ApplicationAdmin)
site.register(AuditEvent,AuditAdmin)
for model in (Squad,TrainingSession,Announcement): site.register(model,LoggedAdmin)

# Financial records are immutable in admin; the gateway owns payment status.
from .models import CoachProfile, PaymentOrder, DuesMonth, AcademyEvent, AppointmentRequest
class PaymentAdmin(AuditAdmin):
    list_display=('created_at','user','purpose','amount_kobo','status')
    readonly_fields=tuple(f.name for f in PaymentOrder._meta.fields)
    list_filter=('status','purpose')
class DuesAdmin(AuditAdmin):
    list_display=('user','month','payment')
    readonly_fields=tuple(f.name for f in DuesMonth._meta.fields)
class AppointmentAdmin(LoggedAdmin):
    list_display=('user','coach','requested_at','status')
    readonly_fields=('user','coach','requested_at','topic','created_at','event')
    def has_add_permission(self,request): return False
    def save_model(self,request,obj,form,change):
        # Confirmation publishes a private one-hour calendar event for this player only.
        from datetime import timedelta
        from django.utils import timezone
        from django.core.exceptions import ValidationError
        previous=AppointmentRequest.objects.get(pk=obj.pk)
        super().save_model(request,obj,form,change)
        if obj.status=='confirmed' and not obj.event_id:
            obj.event = AcademyEvent.objects.create(title=f'Coach appointment · {obj.coach.nickname}',kind='appointment',
                starts_at=obj.requested_at,ends_at=obj.requested_at+timedelta(hours=1),
                details='Confirm the meeting point with the academy before travelling.',recipient=obj.user,published=True)
            obj.save(update_fields=['event'])
        elif obj.event_id:
            AcademyEvent.objects.filter(pk=obj.event_id).update(published=obj.status=='confirmed')
site.register(PaymentOrder,PaymentAdmin)
site.register(DuesMonth,DuesAdmin)
site.register(CoachProfile,LoggedAdmin)
site.register(AcademyEvent,LoggedAdmin)
site.register(AppointmentRequest,AppointmentAdmin)
