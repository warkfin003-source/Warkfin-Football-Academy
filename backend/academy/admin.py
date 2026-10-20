from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Squad, Player, Application, TrainingSession, Announcement, AuditEvent

class OwnerAdminSite(admin.AdminSite):
    site_header='Warkfin Academy · Owner administration'
    site_title='Warkfin Academy'
    index_title='Academy management'
    def has_permission(self,request): return request.user.is_active and request.user.is_superuser

site=OwnerAdminSite(name='owner_admin')
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

class ApplicationAdmin(admin.ModelAdmin):
    list_display=('full_name','status','submitted_at')
    readonly_fields=tuple(f.name for f in Application._meta.fields)
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
    def has_change_permission(self,request,obj=None): return False

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
