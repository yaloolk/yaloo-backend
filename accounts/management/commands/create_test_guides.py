# accounts/management/commands/create_test_guides.py
#
# Usage:
#   python manage.py create_test_guides
#
# Uses Supabase ADMIN API (service role key) to create users with
# email_confirm=True — works even if email confirmation is ENABLED
# in Supabase dashboard. No fake emails, no confirmation needed.

from django.core.management.base import BaseCommand
from accounts.models import UserProfile, GuideProfile, City, UserLanguage, Language
from accounts.supabase_utils import get_supabase_client


GUIDES = [
    {
        "email": "guide1@yaloo.test",
        "password": "Test@1234",
        "first_name": "Ashan",
        "last_name": "Perera",
        "phone": "+94771000001",
        "city_name": "Colombo",
        "experience_years": 5,
        "rate_per_hour": 1500.0,
        "education": "Tourism Diploma",
        "bio": "Experienced guide in Colombo region.",
    },
    {
        "email": "guide2@yaloo.test",
        "password": "Test@1234",
        "first_name": "Nimal",
        "last_name": "Silva",
        "phone": "+94771000002",
        "city_name": "Kandy",
        "experience_years": 3,
        "rate_per_hour": 1200.0,
        "education": "BA History",
        "bio": "Cultural tour specialist in the hill country.",
    },
    {
        "email": "guide3@yaloo.test",
        "password": "Test@1234",
        "first_name": "Kasun",
        "last_name": "Fernando",
        "phone": "+94771000003",
        "city_name": "Galle",
        "experience_years": 7,
        "rate_per_hour": 1800.0,
        "education": "Hospitality Management",
        "bio": "Southern coast specialist with SLTDA certification.",
    },
    {
        "email": "guide4@yaloo.test",
        "password": "Test@1234",
        "first_name": "Dilshan",
        "last_name": "Jayawardena",
        "phone": "+94771000004",
        "city_name": "Sigiriya",
        "experience_years": 4,
        "rate_per_hour": 1400.0,
        "education": "Archaeology Degree",
        "bio": "Ancient city and heritage tour guide.",
    },
    {
        "email": "guide5@yaloo.test",
        "password": "Test@1234",
        "first_name": "Chamara",
        "last_name": "Bandara",
        "phone": "+94771000005",
        "city_name": "Ella",
        "experience_years": 2,
        "rate_per_hour": 1000.0,
        "education": "Tourism Certificate",
        "bio": "Hiking and nature tours in Ella.",
    },
    {
        "email": "guide6@yaloo.test",
        "password": "Test@1234",
        "first_name": "Rukshan",
        "last_name": "Dissanayake",
        "phone": "+94771000006",
        "city_name": "Colombo",
        "experience_years": 6,
        "rate_per_hour": 1600.0,
        "education": "Tourism Management",
        "bio": "City and food tour expert.",
    },
    {
        "email": "guide7@yaloo.test",
        "password": "Test@1234",
        "first_name": "Thilina",
        "last_name": "Rajapaksa",
        "phone": "+94771000007",
        "city_name": "Kandy",
        "experience_years": 8,
        "rate_per_hour": 2000.0,
        "education": "MA Tourism",
        "bio": "Senior guide with expertise in cultural heritage.",
    },
    {
        "email": "guide8@yaloo.test",
        "password": "Test@1234",
        "first_name": "Saman",
        "last_name": "Kumara",
        "phone": "+94771000008",
        "city_name": "Galle",
        "experience_years": 3,
        "rate_per_hour": 1100.0,
        "education": "Tourism Diploma",
        "bio": "Fort and coastal tours around Galle.",
    },
    {
        "email": "guide9@yaloo.test",
        "password": "Test@1234",
        "first_name": "Pradeep",
        "last_name": "Wickramasinghe",
        "phone": "+94771000009",
        "city_name": "Sigiriya",
        "experience_years": 5,
        "rate_per_hour": 1500.0,
        "education": "History Degree",
        "bio": "Rock fortress and Dambulla cave temple specialist.",
    },
    {
        "email": "guide10@yaloo.test",
        "password": "Test@1234",
        "first_name": "Nuwan",
        "last_name": "Senanayake",
        "phone": "+94771000010",
        "city_name": "Ella",
        "experience_years": 1,
        "rate_per_hour": 900.0,
        "education": "Tourism Certificate",
        "bio": "Adventure and trekking guide in Ella.",
    },
]


class Command(BaseCommand):
    help = 'Create 10 test guide users via Supabase admin API (no email confirmation needed)'

    def handle(self, *args, **options):
        # MUST use service role key — only service role can call admin.create_user
        supabase = get_supabase_client(use_service_role=True)

        if not supabase:
            self.stderr.write(self.style.ERROR(
                '❌ Supabase client not initialized. '
                'Make sure SUPABASE_SERVICE_ROLE_KEY is set in your settings/env.'
            ))
            return

        # Pre-fetch cities once
        cities = {c.name: c for c in City.objects.filter(is_active=True)}
        if not cities:
            self.stderr.write(self.style.ERROR(
                '❌ No cities found in DB. Please add cities first via admin or fixtures.'
            ))
            return

        self.stdout.write(f"Found cities: {', '.join(cities.keys())}\n")

        # Try to get English language for default assignment
        try:
            english = Language.objects.get(code='en')
        except Language.DoesNotExist:
            english = None
            self.stdout.write(self.style.WARNING(
                "⚠️  English language (code='en') not found, skipping language assignment."
            ))

        created = 0
        skipped = 0

        for g in GUIDES:
            self.stdout.write(f"─── Processing {g['email']} ───")

            # ── 1. Skip if phone already exists ─────────────────────────────
            if UserProfile.objects.filter(phone_number=g['phone']).exists():
                self.stdout.write(self.style.WARNING(
                    f"  ⚠️  Skipped — phone {g['phone']} already exists in DB"
                ))
                skipped += 1
                continue

            # ── 2. Create Supabase auth user via ADMIN API ───────────────────
            # The key here is email_confirm=True in the payload.
            # When called with the SERVICE ROLE key, Supabase marks the user
            # as confirmed immediately — no confirmation email is sent and
            # no dashboard setting needs to be changed.
            try:
                res = supabase.auth.admin.create_user({
                    "email": g['email'],
                    "password": g['password'],
                    "email_confirm": True,
                    "user_metadata": {
                        "role": "guide",
                        "first_name": g['first_name'],
                        "last_name": g['last_name'],
                    }
                })
                auth_user_id = res.user.id
                self.stdout.write(f"  ✅ Auth user created: {auth_user_id}")

            except Exception as e:
                err = str(e).lower()
                if any(x in err for x in ['already been registered', 'already exists', 'duplicate']):
                    self.stdout.write(self.style.WARNING(
                        f"  ⚠️  Skipped — {g['email']} already exists in Supabase"
                    ))
                else:
                    self.stderr.write(self.style.ERROR(f"  ❌ Supabase error: {e}"))
                skipped += 1
                continue

            # ── 3. Create UserProfile ────────────────────────────────────────
            try:
                user_profile = UserProfile.objects.create(
                    auth_user_id=auth_user_id,
                    first_name=g['first_name'],
                    last_name=g['last_name'],
                    phone_number=g['phone'],
                    gender='male',
                    country='Sri Lanka',
                    profile_bio=g['bio'],
                    user_role='guide',
                    is_complete=True,
                    profile_status='active',
                )
                self.stdout.write(f"  ✅ UserProfile created: {user_profile.id}")
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  ❌ UserProfile error: {e}"))
                # Roll back the Supabase auth user to keep things clean
                try:
                    supabase.auth.admin.delete_user(str(auth_user_id))
                    self.stdout.write("  🧹 Rolled back Supabase auth user")
                except Exception:
                    pass
                skipped += 1
                continue

            # ── 4. Resolve city (exact → partial → first available) ──────────
            city = cities.get(g['city_name'])
            if not city:
                city = next(
                    (c for name, c in cities.items() if g['city_name'].lower() in name.lower()),
                    None
                )
            if not city:
                city = next(iter(cities.values()))
                self.stdout.write(self.style.WARNING(
                    f"  ⚠️  City '{g['city_name']}' not found — using '{city.name}' as fallback"
                ))

            # ── 5. Create GuideProfile ───────────────────────────────────────
            try:
                GuideProfile.objects.create(
                    user_profile=user_profile,
                    city_id=city.id,
                    experience_years=g['experience_years'],
                    education=g['education'],
                    rate_per_hour=g['rate_per_hour'],
                    verification_status='verified',
                    is_available=True,
                    is_SLTDA_verified=False,
                    avg_rating=0.0,
                )
                self.stdout.write(f"  ✅ GuideProfile created (city: {city.name})")
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  ❌ GuideProfile error: {e}"))
                skipped += 1
                continue

            # ── 6. Assign English language ───────────────────────────────────
            if english:
                try:
                    UserLanguage.objects.create(
                        user_profile=user_profile,
                        language=english,
                        proficiency='native',
                        is_native=True,
                    )
                    self.stdout.write("  ✅ Language assigned (English/native)")
                except Exception:
                    pass  # non-critical, don't fail the whole guide for this

            created += 1
            self.stdout.write(self.style.SUCCESS(
                f"  🎉 '{g['first_name']} {g['last_name']}' created successfully\n"
            ))

        # ── Summary ──────────────────────────────────────────────────────────
        self.stdout.write('═' * 50)
        self.stdout.write(self.style.SUCCESS(f'✅ Created : {created}'))
        if skipped:
            self.stdout.write(self.style.WARNING(f'⚠️  Skipped : {skipped}'))
        self.stdout.write('')
        self.stdout.write('Login credentials for all created guides:')
        self.stdout.write('  Password : Test@1234')
        self.stdout.write('  Emails   : guide1@yaloo.test → guide10@yaloo.test')
        self.stdout.write(self.style.SUCCESS('Done!'))