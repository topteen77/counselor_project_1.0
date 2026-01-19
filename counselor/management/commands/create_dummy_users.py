"""
Management command to create dummy users for testing
Usage: python manage.py create_dummy_users
"""
from django.core.management.base import BaseCommand
from counselor.models import CounselorUser


class Command(BaseCommand):
    help = 'Creates dummy users for testing purposes'

    def handle(self, *args, **options):
        # Demo users to create
        demo_users = [
            {
                'username': 'demo_user1',
                'email': 'demo1@test.com',
                'password': 'demo123'
            },
            {
                'username': 'demo_user2',
                'email': 'demo2@test.com',
                'password': 'demo123'
            },
            {
                'username': 'test_user',
                'email': 'test@test.com',
                'password': 'test123'
            },
            {
                'username': 'admin_demo',
                'email': 'admin@test.com',
                'password': 'admin123'
            },
        ]

        created_count = 0
        skipped_count = 0

        for user_data in demo_users:
            try:
                user, created = CounselorUser.objects.get_or_create(
                    email=user_data['email'],
                    defaults={
                        'username': user_data['username'],
                        'password': user_data['password']
                    }
                )
                if created:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ Created user: {user_data["username"]} ({user_data["email"]})'
                        )
                    )
                    created_count += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'⊘ User already exists: {user_data["username"]} ({user_data["email"]})'
                        )
                    )
                    skipped_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'✗ Error creating user {user_data["username"]}: {str(e)}'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ Created {created_count} new users'
            )
        )
        if skipped_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'⊘ Skipped {skipped_count} existing users'
                )
            )
