from django.db import migrations


def sync_admin_access_flags(apps, schema_editor):
    User = apps.get_model('authentication', 'User')

    # Superusers should always be admin-role staff users.
    User.objects.filter(is_superuser=True).update(
        role='admin',
        status='active',
        is_staff=True,
    )

    # Role-based admins should be staff so they can access Django admin.
    User.objects.filter(role='admin').update(is_staff=True)


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0002_alter_user_options_user_created_at_user_status_and_more'),
    ]

    operations = [
        migrations.RunPython(sync_admin_access_flags, migrations.RunPython.noop),
    ]
