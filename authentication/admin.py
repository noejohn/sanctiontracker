from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group
from django.contrib.admin.sites import AlreadyRegistered
from authentication.models import Concern, Sanction, SanctionType, ServiceHourSubmission, User


class CustomAdminSite(admin.AdminSite):
    """Custom admin site with navigation to custom pages"""
    site_header = "Site administration"
    site_title = "Django site admin"
    index_title = "Site administration"
    index_template = "custom_admin/index.html"

    def has_permission(self, request):
        user = request.user
        return user.is_active and (
            user.is_superuser or user.is_staff or getattr(user, 'role', None) == 'admin'
        )
    
    def index(self, request, extra_context=None):
        """Override admin index to add custom navigation"""
        if extra_context is None:
            extra_context = {}
        
        # Add custom admin links
        extra_context['custom_admin_pages'] = [
            {'name': 'Dashboard', 'url': '/admin-dashboard/', 'description': 'View admin dashboard'},
            {'name': 'Student Management', 'url': '/student-management/', 'description': 'Manage students'},
            {'name': 'Sanctions Management', 'url': '/sanctions/', 'description': 'Manage sanctions'},
            {'name': 'Service Hours', 'url': '/servicehours/', 'description': 'Manage service hours'},
            {'name': 'Reports', 'url': '/reports/', 'description': 'View reports'},
            {'name': 'Django Admin', 'url': '/admin/', 'description': 'Open default Django admin'},
        ]
        
        return super().index(request, extra_context)


# Create custom admin site instance
custom_admin_site = CustomAdminSite(name='custom_admin')


class CustomUserAdmin(UserAdmin):
    """Custom User admin with role and status fields"""
    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'role',
        'student_code',
        'status',
        'is_active',
    )
    list_filter = ('role', 'status', 'department', 'is_active', 'created_at')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'student_code')
    ordering = ('-created_at',)
    
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {
            'fields': (
                'role',
                'status',
                'student_code',
                'department',
                'course_year',
                'created_at',
                'updated_at',
            )
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SanctionType)
class SanctionTypeAdmin(admin.ModelAdmin):
    list_display = ('description', 'hours', 'gravity', 'updated_at')
    search_fields = ('description',)
    list_filter = ('gravity',)
    ordering = ('description',)


@admin.register(Sanction)
class SanctionAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'violation',
        'required_hours',
        'completed_hours',
        'status',
        'date_issued',
        'due_date',
    )
    list_filter = ('status', 'department', 'date_issued', 'due_date')
    search_fields = ('student__username', 'student__first_name', 'student__last_name', 'violation_snapshot')
    autocomplete_fields = ('student', 'sanction_type')
    ordering = ('-date_issued', '-created_at')


@admin.register(ServiceHourSubmission)
class ServiceHourSubmissionAdmin(admin.ModelAdmin):
    list_display = ('student', 'date', 'hours', 'status', 'reviewed_by')
    list_filter = ('status', 'date')
    search_fields = ('student__username', 'student__first_name', 'student__last_name', 'description')
    autocomplete_fields = ('student', 'sanction', 'reviewed_by')
    ordering = ('-date', '-created_at')


@admin.register(Concern)
class ConcernAdmin(admin.ModelAdmin):
    list_display = ('student', 'subject', 'status', 'created_at')
    list_filter = ('status', 'subject', 'created_at')
    search_fields = ('student__username', 'student__first_name', 'student__last_name', 'message')
    autocomplete_fields = ('student',)
    ordering = ('-created_at',)


def register_admin_models(site):
    """Register auth models for a specific admin site instance."""
    for model, model_admin in ((User, CustomUserAdmin), (Group, GroupAdmin)):
        try:
            site.register(model, model_admin)
        except AlreadyRegistered:
            pass


# Register models only on default Django admin site.
# Custom admin (/admin/) is kept for app navigation pages.
register_admin_models(admin.site)
