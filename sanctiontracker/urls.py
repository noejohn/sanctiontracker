"""
URL configuration for sanctiontracker project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from authentication import views as auth_views
from authentication.admin import custom_admin_site

urlpatterns = [
    path('', auth_views.login_view, name='home'),
    path('admin/', admin.site.urls),
    path('admin-panel/', custom_admin_site.urls),
    path('login/', auth_views.login_view, name='login'),
    path('dashboard/', auth_views.dashboard_view, name='dashboard'),
    path('admin-dashboard/', auth_views.admin_dashboard_view, name='admin_dashboard'),
    path('student-dashboard/', auth_views.student_dashboard_view, name='student_dashboard'),
    path('student-sanctions/', auth_views.student_sanctions_view, name='student_sanctions'),
    path('student-service-hours/', auth_views.student_service_hours_view, name='student_service_hours'),
    path('student-records/', auth_views.student_records_view, name='student_records'),
    path('student-help-center/', auth_views.student_help_center_view, name='student_help_center'),
    path('student-settings/', auth_views.student_settings_view, name='student_settings'),
    path('student-management/', auth_views.student_management_view, name='student_management'),
    path('student/<int:student_id>/', auth_views.student_detail_view, name='student_detail'),
    path('logout/', auth_views.logout_view, name='logout'),
    path('sanctions/', auth_views.sanction_management_view, name='sanction_management'),
    path('sanctions/add/', auth_views.add_sanction_view, name='add_sanction'),
    path('sanctions/add-new-student/', auth_views.add_new_student_with_sanction_view,
        name='add_new_student_with_sanction'),
    path('sanctions/types/add/', auth_views.add_sanction_type_view, name='add_sanction_type'),
    path('sanctions/types/<int:sanction_type_id>/edit/', auth_views.edit_sanction_type_view, name='edit_sanction_type'),
    path('sanctions/types/<int:sanction_type_id>/delete/', auth_views.delete_sanction_type_view, name='delete_sanction_type'),
    path('sanctions/<int:sanction_id>/edit/', auth_views.edit_sanction_view, name='edit_sanction'),
    path('sanctions/<int:sanction_id>/delete/', auth_views.delete_sanction_view, name='delete_sanction'),
    path('servicehours/', auth_views.service_hours_management_view, name='servicehours_management'),
    path('servicehours/submission/<int:submission_id>/status/', auth_views.update_service_submission_status,
        name='service_submission_status'),
    path('reports/', auth_views.reports_management_view, name='reports_management'),
    path('concerns/<int:concern_id>/status/', auth_views.update_concern_status, name='concern_status'),
    path('concerns/', auth_views.concerns_management_view, name='concerns_management'),
    path('create-student/', auth_views.create_student_view, name='create_student'),
    path('create-admin/', auth_views.create_admin_view, name='create_admin'),
]


# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
