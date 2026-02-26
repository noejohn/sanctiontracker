from django.core.management.base import BaseCommand
from authentication.models import User


class Command(BaseCommand):
    help = 'Creates default admin and student users'

    def handle(self, *args, **options):
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                email='admin@podoffice.edu',
                password='admin123',
                role='admin',
                first_name='System',
                last_name='Administrator'
            )
            self.stdout.write(self.style.SUCCESS('Default admin user created successfully!'))
        else:
            self.stdout.write(self.style.WARNING('Admin user already exists.'))

        if not User.objects.filter(username='student').exists():
            User.objects.create_user(
                username='student',
                email='student@podoffice.edu',
                password='student123',
                role='student',
                status='active',
                first_name='Sample',
                last_name='Student'
            )
            self.stdout.write(self.style.SUCCESS('Default student user created successfully!'))
        else:
            self.stdout.write(self.style.WARNING('Student user already exists.'))
