# accounts/management/commands/test_auth.py

from django.core.management.base import BaseCommand
from accounts.supabase_utils import verify_supabase_token, get_supabase_client


class Command(BaseCommand):
    help = 'Test Supabase authentication'

    def add_arguments(self, parser):
        parser.add_argument('token', type=str, help='Supabase JWT token to test')

    def handle(self, *args, **options):
        token = options['token']
        
        self.stdout.write('Testing Supabase authentication...\n')
        
        # Test token verification
        user = verify_supabase_token(token)
        
        if user:
            self.stdout.write(self.style.SUCCESS('✅ Token is valid!'))
            self.stdout.write(f'\nUser Details:')
            self.stdout.write(f'  - ID: {user.id}')
            self.stdout.write(f'  - Email: {user.email}')
            self.stdout.write(f'  - Email Confirmed: {user.email_confirmed_at is not None}')
            self.stdout.write(f'  - Created: {user.created_at}')
            
            if user.user_metadata:
                self.stdout.write(f'\nUser Metadata:')
                for key, value in user.user_metadata.items():
                    self.stdout.write(f'  - {key}: {value}')
        else:
            self.stdout.write(self.style.ERROR('❌ Invalid or expired token'))


# accounts/management/commands/create_test_profiles.py

from django.core.management.base import BaseCommand
from accounts.models import UserProfile, TouristProfile, GuideProfile, HostProfile
import uuid


class Command(BaseCommand):
    help = 'Create test user profiles for development'

    def handle(self, *args, **options):
        self.stdout.write('Creating test profiles...\n')
        
        # Create test tourist
        tourist_user = UserProfile.objects.create(
            auth_user_id=uuid.uuid4(),
            first_name="John",
            last_name="Doe",
            user_role="tourist",
            phone_number="+13001234567",
            country="USA",
            profile_status="active",
            is_complete=True
        )
        
        TouristProfile.objects.create(
            user_profile=tourist_user,
            travel_style="adventure",
            total_bookings=0,
            trust_score=5.0
        )
        
        self.stdout.write(self.style.SUCCESS(f'✅ Created tourist: {tourist_user.full_name}'))
        
        # Create test guide
        guide_user = UserProfile.objects.create(
            auth_user_id=uuid.uuid4(),
            first_name="Jhon",
            last_name="Perera",
            user_role="guide",
            phone_number="+943009876543",
            country="Sri Lanka",
            profile_status="active",
            is_complete=True
        )
        
        GuideProfile.objects.create(
            user_profile=guide_user,
            verification_status="verified",
            total_completed_bookings=25,
            avg_rating=4.8,
            total_earned=50000.00
        )
        
        self.stdout.write(self.style.SUCCESS(f'✅ Created guide: {guide_user.full_name}'))
        
        # Create test host
        host_user = UserProfile.objects.create(
            auth_user_id=uuid.uuid4(),
            first_name="Silva",
            last_name="Fernando",
            user_role="host",
            phone_number="+943007654321",
            country="Sri Lanka",
            profile_status="active",
            is_complete=True
        )
        
        HostProfile.objects.create(
            user_profile=host_user,
            verification_status="verified",
            no_of_stays_owned=2,
            total_completed_bookings=15,
            avg_rating=4.9,
            total_earned=75000.00
        )
        
        self.stdout.write(self.style.SUCCESS(f'✅ Created host: {host_user.full_name}'))
        
        self.stdout.write(self.style.SUCCESS('\n✅ All test profiles created successfully!'))