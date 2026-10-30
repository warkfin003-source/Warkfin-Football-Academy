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

# Refund obligations are visible to the owner but cannot be marked paid by editing a form.
from .models import RegistrationRefund
class RefundAdmin(AuditAdmin):
    list_display=('payment','status','requested_at')
    readonly_fields=tuple(f.name for f in RegistrationRefund._meta.fields)
site.register(RegistrationRefund,RefundAdmin)

# Owner-only bulk controls preserve financial and membership history.
from .models import Attendance, Feedback, Availability, CoachApplication
from django.contrib import messages
class ActiveRecordAdmin(LoggedAdmin):
    actions=['activate_records','archive_records']
    def set_active(self,request,queryset,value):
        for obj in queryset:
            obj.active=value;obj.save(update_fields=['active'])
            AuditEvent.objects.create(actor=request.user,action='admin.activated' if value else 'admin.archived',object_reference=f'{obj._meta.model_name}:{obj.pk}')
    @admin.action(description='Activate selected records')
    def activate_records(self,request,queryset): self.set_active(request,queryset,True)
    @admin.action(description='Archive selected records (retain history)')
    def archive_records(self,request,queryset): self.set_active(request,queryset,False)
class ManagedPlayerAdmin(PlayerAdmin,ActiveRecordAdmin): pass
class CoachProfileAdmin(ActiveRecordAdmin):
    list_display=('name','nickname','active')
    search_fields=('name','nickname')
    list_filter=('active',)
class PublishingAdmin(LoggedAdmin):
    list_display=('title','published')
    search_fields=('title',)
    list_filter=('published',)
    actions=['publish_records','unpublish_records']
    def set_published(self,request,queryset,value):
        for obj in queryset:
            obj.published=value;obj.save(update_fields=['published'])
            AuditEvent.objects.create(actor=request.user,action='admin.published' if value else 'admin.unpublished',object_reference=f'{obj._meta.model_name}:{obj.pk}')
    @admin.action(description='Publish selected records')
    def publish_records(self,request,queryset): self.set_published(request,queryset,True)
    @admin.action(description='Unpublish selected records')
    def unpublish_records(self,request,queryset): self.set_published(request,queryset,False)
class AnnouncementAdmin(PublishingAdmin):
    list_display=('title','published','provisional_visible')
    list_filter=('published','provisional_visible')
    # Django presents its confirmation page; no destructive action runs from a GET.
    def has_delete_permission(self,request,obj=None): return request.user.is_superuser
    def delete_model(self,request,obj):
        AuditEvent.objects.create(actor=request.user,action='announcement.deleted',object_reference=f'announcement:{obj.pk}')
        super().delete_model(request,obj)
    def delete_queryset(self,request,queryset):
        for obj in queryset:
            AuditEvent.objects.create(actor=request.user,action='announcement.deleted',object_reference=f'announcement:{obj.pk}')
        super().delete_queryset(request,queryset)
class SessionAdmin(LoggedAdmin):
    list_display=('title','squad','starts_at','venue','status','provisional_visible')
    search_fields=('title','venue')
    list_filter=('status','squad')
    date_hierarchy='starts_at'
class SquadAdmin(LoggedAdmin):
    filter_horizontal=('coaches',)
    search_fields=('name',)
class AttendanceAdmin(LoggedAdmin):
    list_display=('player','session','status','recorded_by')
    list_filter=('status','session__squad')
    readonly_fields=('recorded_by',)
    def save_model(self,request,obj,form,change):
        obj.recorded_by=request.user;super().save_model(request,obj,form,change)
class FeedbackAdmin(LoggedAdmin):
    list_display=('player','goal','shared_with_player','created_at')
    search_fields=('player__display_name','goal')
    readonly_fields=('author',)
    def save_model(self,request,obj,form,change):
        if not obj.pk: obj.author=request.user
        super().save_model(request,obj,form,change)
class CoachApplicationAdmin(ApplicationAdmin):
    readonly_fields=tuple(f.name for f in CoachApplication._meta.fields)
    search_fields=('full_name','user__email')
    list_filter=('status',)
for model,manager in [(Player,ManagedPlayerAdmin),(CoachProfile,CoachProfileAdmin),(Announcement,AnnouncementAdmin),(AcademyEvent,PublishingAdmin),(TrainingSession,SessionAdmin),(Squad,SquadAdmin)]:
    site.unregister(model);site.register(model,manager)
site.register(Attendance,AttendanceAdmin)
site.register(Feedback,FeedbackAdmin)
site.register(CoachApplication,CoachApplicationAdmin)

# Make the public/private audience visible when the owner manages calendar events.
class EventAdmin(PublishingAdmin):
    list_display=('title','kind','starts_at','published','public','recipient','squad')
    list_filter=('published','public','kind')
    date_hierarchy='starts_at'
site.unregister(AcademyEvent)
site.register(AcademyEvent,EventAdmin)


# Completed transfer reports are retained for financial review; approval uses the dedicated owner workflow.
from .models import TransferClaim
class TransferClaimAdmin(LoggedAdmin):
    list_display=('id','sender_name','status','created_at','reviewed_at')
    list_filter=('status',)
    search_fields=('sender_name','reported_reference','verified_reference','order__user__email')
    readonly_fields=tuple(field.name for field in TransferClaim._meta.fields)
    def has_add_permission(self,request): return False
site.register(TransferClaim,TransferClaimAdmin)
