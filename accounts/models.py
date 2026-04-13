# accounts/models.py

from django.db import models
import uuid
from datetime import datetime, timedelta, time, date

# 1. Define the Master Language Table
class Language(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'language'
        managed = False

    def __str__(self):
        return self.name

# 2. Define the User Language Bridge Table
class UserLanguage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_profile = models.ForeignKey(
        'UserProfile', 
        on_delete=models.CASCADE,
        db_column='user_profile_id',
        related_name='user_languages'
    )
    language = models.ForeignKey(
        Language, 
        on_delete=models.CASCADE, 
        db_column='language_id'
    )
    proficiency = models.CharField(max_length=20, default='native') 
    is_native = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_language'
        managed = False

    def __str__(self):
        return f"{self.user_profile.full_name} - {self.language.name}"

# 3. City Model (EXISTING TABLE)
class City(models.Model):
    """City reference table - EXISTING"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    country = models.TextField(default='sri lanka')
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'city'
        managed = False
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name}, {self.country}"

# 4. Facilities Model (EXISTING TABLE)
class Facilities(models.Model):
    """Facilities/Amenities for stays - EXISTING"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField(unique=True)
    description = models.TextField(null=True, blank=True)
    addon_price = models.FloatField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'facilities'
        managed = False
    
    def __str__(self):
        return self.name

class UserProfile(models.Model):
    """Base user profile - synced with Supabase auth"""
    
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ]
    
    PROFILE_STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    ]
    
    USER_ROLES = [
        ('tourist', 'Tourist'),
        ('guide', 'Guide'),
        ('host', 'Host'),
        ('admin', 'Admin'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    auth_user_id = models.UUIDField(unique=True, db_index=True)
    first_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    phone_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    profile_pic = models.URLField(max_length=500, null=True, blank=True)
    profile_bio = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    profile_status = models.CharField(
        max_length=20, 
        choices=PROFILE_STATUS_CHOICES, 
        default='active'
    )
    user_role = models.CharField(max_length=10, choices=USER_ROLES, default='tourist')
    is_complete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'user_profile'
        managed = False
        ordering = ['-created_at']
    
    def __str__(self):
        full_name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return full_name or str(self.auth_user_id)
    
    @property
    def full_name(self):
        """Get full name from first and last name"""
        return f"{self.first_name or ''} {self.last_name or ''}".strip()
    
    @property
    def verification_status(self):
        """Get verification status based on user role"""
        if self.user_role == 'tourist':
            return 'not_required'
        elif self.user_role == 'guide':
            if hasattr(self, 'guide_profile'):
                return self.guide_profile.verification_status
            return 'pending'
        elif self.user_role == 'host':
            if hasattr(self, 'host_profile'):
                return self.host_profile.verification_status
            return 'pending'
        return 'not_required'


class TouristProfile(models.Model):
    """Extended profile for tourists"""
    TRAVEL_STYLE_CHOICES = [
        ('solo', 'Solo'),
        ('couple', 'Couple'),
        ('family', 'Family'),
        ('group', 'Group'),
        ('business', 'Business'),
        ('backpacker', 'Backpacker'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='tourist_profile',
        db_column='user_profile_id'
    )

    preferred_language = models.ForeignKey(
        UserLanguage, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        db_column='preferred_language'
    )

    travel_style = models.CharField(
        max_length=20, 
        choices=TRAVEL_STYLE_CHOICES, 
        null=True, 
        blank=True
    )
    passport_number = models.CharField(max_length=50, null=True, blank=True)
    dietery_preferences = models.TextField(null=True, blank=True)
    other_preferences = models.TextField(null=True, blank=True)
    emergency_contact_name = models.CharField(max_length=255, null=True, blank=True)
    emergency_contact_relation = models.CharField(max_length=100, null=True, blank=True)
    emergency_contact_number = models.CharField(max_length=20, null=True, blank=True)
    
    total_bookings = models.IntegerField(default=0)
    total_cancelled_bookings = models.IntegerField(default=0)
    trust_score = models.FloatField(default=0.0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tourist_profile'
        managed = False
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Tourist: {self.user_profile.full_name}"


class GuideProfile(models.Model):
    """Extended profile for local guides - MATCHES YOUR SCHEMA"""
    
    VERIFICATION_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='guide_profile',
        db_column='user_profile_id'
    )
    city_id = models.UUIDField(null=False)  # Reference to city table
    
    experience_years = models.IntegerField(null=True, blank=True)
    education = models.TextField(null=True, blank=True)
    
    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUS_CHOICES,
        default='pending'
    )
    
    rate_per_hour = models.FloatField(default=0.0, null=True)
    avg_rating = models.FloatField(default=0.0, null=True)
    booking_response_rate = models.FloatField(default=0.0, null=True)
    
    total_completed_bookings = models.IntegerField(default=0, null=True)
    total_rejected_bookings = models.IntegerField(default=0, null=True)
    total_cancelled_bookings = models.IntegerField(default=0, null=True)
    total_tip_earned = models.FloatField(default=0.0, null=True)
    total_earned = models.FloatField(default=0.0, null=True)
    
    is_available = models.BooleanField(default=True)
    is_SLTDA_verified = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'guide_profile'
        managed = False
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Guide: {self.user_profile.full_name}"
    
    @property
    def is_verified(self):
        return self.verification_status == 'verified'


class HostProfile(models.Model):
    """Extended profile for stay hosts - MATCHES YOUR SCHEMA"""
    
    VERIFICATION_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='host_profile',
        db_column='user_profile_id'
    )
    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUS_CHOICES,
        default='pending'
    )
    
    no_of_stays_owned = models.IntegerField(default=0)
    total_completed_bookings = models.IntegerField(default=0, null=True)
    total_rejected_bookings = models.IntegerField(default=0, null=True)
    total_cancelled_bookings = models.IntegerField(default=0, null=True)
    response_rate = models.FloatField(default=0.0, null=True)
    avg_rating = models.FloatField(default=0.0, null=True)
    total_tip_earned = models.FloatField(default=0.0, null=True)
    total_earned = models.FloatField(default=0.0, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'host_profile'
        managed = False
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Host: {self.user_profile.full_name}"
    
    @property
    def is_verified(self):
        return self.verification_status == 'verified'


class Stay(models.Model):
    STAY_TYPE_CHOICES = [
        ('homestay',   'Homestay'),
        ('farm_stay',  'Farm Stay'),
        ('villa',      'Villa'),
        ('guesthouse', 'Guesthouse'),
        ('eco_lodge',  'Eco Lodge'),
        ('hostel',     'Hostel'),
    ]
    VERIFICATION_STATUS_CHOICES = [
        ('pending',  'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]

    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host    = models.ForeignKey(
        HostProfile, on_delete=models.CASCADE,
        related_name='stays', db_column='host_id'
    )
    name        = models.TextField(null=True, blank=True)
    type        = models.CharField(max_length=20, choices=STAY_TYPE_CHOICES, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    # Address
    house_no    = models.TextField(null=True, blank=True)
    street      = models.TextField(null=True, blank=True)
    town        = models.TextField(null=True, blank=True)
    city_id     = models.UUIDField(null=True, blank=True)
    postal_code = models.IntegerField(null=True, blank=True)
    latitude    = models.FloatField(null=True, blank=True)
    longitude   = models.FloatField(null=True, blank=True)

    # Rooms / capacity
    room_count      = models.IntegerField(null=True, blank=True)
    room_available  = models.BooleanField(default=True)
    max_guests      = models.IntegerField(null=True, blank=True)
    bathroom_count  = models.IntegerField(default=1)
    shared_bathrooms = models.BooleanField(default=False)

    # Pricing
    price_per_night        = models.FloatField(default=0.0)
    price_per_halfday      = models.FloatField(default=0.0)
    price_entire_place     = models.FloatField(default=0.0)
    entire_place_is_available = models.BooleanField(default=True)
    price_per_extra_guest  = models.FloatField(default=0.0)
    halfday_available      = models.BooleanField(default=False)

    # ── The 3 fields that caused "FieldError" in the serializer ──
    standard_checkin_time     = models.TimeField(default=time(14, 0))
    standard_checkout_time    = models.TimeField(default=time(11, 0))
    standard_halfday_checkout = models.TimeField(default=time(20, 0))

    # Status
    is_active           = models.BooleanField(default=True)
    verification_status = models.CharField(
        max_length=20, choices=VERIFICATION_STATUS_CHOICES, default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stay'
        managed  = False
        ordering = ['-created_at']

    def __str__(self):
        return self.name or f'Stay {self.id}'

    @property
    def is_verified(self):
        return self.verification_status == 'verified'


class StayPic(models.Model):
    id        = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stay      = models.ForeignKey(Stay, on_delete=models.CASCADE,
                                  related_name='photos', db_column='stay_id')
    photo_url = models.TextField()
    position  = models.IntegerField(null=True, blank=True)
    is_cover  = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stay_pic'
        managed  = False
        ordering = ['position']

    def __str__(self):
        return f'Photo for {self.stay}'


class ProfileDocument(models.Model):
    """Profile verification documents - EXISTING TABLE"""
    
    VERIFICATION_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    guide = models.ForeignKey(
        GuideProfile,
        on_delete=models.CASCADE,
        related_name='documents',
        db_column='guide_id',
        null=True,
        blank=True
    )
    host = models.ForeignKey(
        HostProfile,
        on_delete=models.CASCADE,
        related_name='documents',
        db_column='host_id',
        null=True,
        blank=True
    )
    document_url = models.TextField()
    document_type = models.TextField()  # e.g., 'government_id', 'profile_photo', 'license'
    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUS_CHOICES,
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'profile_document'
        managed = False
        ordering = ['-created_at']
    
    def __str__(self):
        owner = self.guide or self.host
        return f"{self.document_type} for {owner}"


class StayDocument(models.Model):
    VERIFICATION_STATUS_CHOICES = [
        ('pending', 'Pending'), ('verified', 'Verified'), ('rejected', 'Rejected'),
    ]
    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stay                = models.ForeignKey(Stay, on_delete=models.CASCADE,
                                            related_name='documents', db_column='stay_id')
    document_type       = models.TextField()
    document_url        = models.TextField()
    verification_status = models.CharField(max_length=20,
                                           choices=VERIFICATION_STATUS_CHOICES, default='pending')
    created_at          = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stay_document'
        managed  = False
        ordering = ['-created_at']


class Interest(models.Model):
    """Interest categories for user preferences"""
    
    CATEGORY_CHOICES = [
        ('culture', 'Culture'),
        ('adventure', 'Adventure'),
        ('nature', 'Nature'),
        ('food', 'Food'),
        ('sports', 'Sports'),
        ('learning', 'Learning'),
        ('social', 'Social'),
        ('entertainment', 'Entertainment'),
        ('other', 'Other'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'interest'
        managed = False
        ordering = ['category', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.category})"


class UserInterest(models.Model):
    """Many-to-many relationship between users and interests"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='user_interests',
        db_column='user_profile_id'
    )
    interest = models.ForeignKey(
        Interest,
        on_delete=models.CASCADE,
        db_column='interest_id'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'user_interest'
        managed = False
        unique_together = ('user_profile', 'interest')
    
    def __str__(self):
        return f"{self.user_profile.full_name} - {self.interest.name}"



# class UserGallery(models.Model):
#     """Generic gallery for all user types"""
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     user_profile = models.ForeignKey(
#         'UserProfile',
#         on_delete=models.CASCADE,
#         related_name='gallery_images',
#         db_column='user_profile_id'
#     )
#     image_url = models.TextField()
#     caption = models.TextField(null=True, blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         db_table = 'user_gallery'
#         managed = False  # Set to True if you want Django to manage migrations
#         ordering = ['-created_at']

#     def __str__(self):
#         return f"Gallery Image for {self.user_profile.full_name}"


class Media(models.Model):
    """
    Maps to the existing public.media table
    """
    # Enum choices matching your DB
    ENTITY_TYPE_CHOICES = [
        ('tourist', 'Tourist'),
        ('guide', 'Guide'),
        ('host', 'Host'),
        ('stay', 'Stay'),
        ('activity', 'Activity'),
        ('place', 'Place'),
    ]

    FILE_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # uploader_id maps to UserProfile
    uploader = models.ForeignKey(
        'UserProfile',
        on_delete=models.CASCADE,
        db_column='uploader_id',
        related_name='uploaded_media'
    )
    
    # We use CharField to interact with the Postgres ENUM
    entity_type = models.CharField(max_length=50, choices=ENTITY_TYPE_CHOICES, null=True, blank=True)
    entity_id = models.UUIDField(null=True, blank=True)
    
    file_path = models.TextField() # This stores the URL
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES, default='image')
    
    is_official = models.BooleanField(default=False)
    order_index = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'media'
        managed = False  # Django won't try to create/change this table
        ordering = ['-created_at']

    def __str__(self):
        return f"Media {self.id} by {self.uploader.full_name}"


class GuideAvailabilityPattern(models.Model):
    """Stores the original availability pattern before splitting into hourly slots"""
    
    RECURRING_TYPE_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    guide_profile = models.ForeignKey(
        'GuideProfile',
        on_delete=models.CASCADE,
        related_name='availability_patterns',
        db_column='guide_profile_id'
    )
    reccuring_type = models.CharField(
        max_length=20,
        choices=RECURRING_TYPE_CHOICES,
        default='daily',
        null=True
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    active_from = models.DateField()
    active_until = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'guide_availability_pattern'
        managed = False
        ordering = ['active_from', 'start_time']

    def __str__(self):
        return f"{self.guide_profile_id} | {self.active_from} to {self.active_until}"


class GuideAvailability(models.Model):
    """Individual hourly slots - auto-generated from patterns"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    guide_profile = models.ForeignKey(
        'GuideProfile',
        on_delete=models.CASCADE,
        related_name='availability_slots',
        db_column='guide_profile_id'
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_booked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'guide_availability'
        managed = False
        ordering = ['date', 'start_time']

    def __str__(self):
        return f"{self.date} {self.start_time}-{self.end_time}"


class Review(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking_id = models.UUIDField()
    tourist    = models.ForeignKey(
        'TouristProfile',
        on_delete=models.CASCADE,
        related_name='reviews_given',
        db_column='tourist_id'
    )
    stay  = models.ForeignKey(
        'Stay',
        on_delete=models.CASCADE,
        related_name='stay_reviews',
        db_column='stay_id',
        null=True,
        blank=True
    )
    guide = models.ForeignKey(
        'GuideProfile',
        on_delete=models.CASCADE,
        related_name='reviews',
        db_column='guide_id',
        null=True,
        blank=True
    )
    rating     = models.FloatField()
    review     = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'review'
        managed  = False
        ordering = ['-created_at']

    def __str__(self):
        return f"Review {self.rating}★"


class StayFacility(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stay = models.ForeignKey(
        Stay, 
        on_delete=models.CASCADE,
        related_name='stay_facilities',  # ✅ Changed from 'stay_facilities' 
        db_column='stay_id'
    )
    facility = models.ForeignKey(
        Facilities, 
        on_delete=models.CASCADE, 
        db_column='facilities_id'  
    )
    special_note = models.TextField(null=True, blank=True) 
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stay_facilities'  
        managed = False
        unique_together = ('stay', 'facility')

    def __str__(self):
        return f'{self.stay} – {self.facility}'


class StayAvailability(models.Model):
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stay          = models.ForeignKey(Stay, on_delete=models.CASCADE,
                                      related_name='availability', db_column='stay_id')
    date          = models.DateField()
    total_room    = models.IntegerField(default=1)
    occupied_room = models.IntegerField(default=0)
    is_available  = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table      = 'stay_availability'
        managed       = False
        ordering      = ['date']
        unique_together = ('stay', 'date')

    def __str__(self):
        return f'{self.stay} – {self.date}'

class Activity(models.Model):
    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name             = models.TextField()
    category         = models.TextField()
    base_price       = models.IntegerField(null=True, blank=True)
    description      = models.TextField(null=True, blank=True)
    instruction      = models.TextField(null=True, blank=True)
    duration         = models.IntegerField(null=True, blank=True)
    is_active        = models.BooleanField(default=True)
    created_by       = models.TextField(default='system')
    budget           = models.TextField(null=True, blank=True)
    difficulty_level = models.TextField(null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)
 
    class Meta:
        db_table = 'activity'
        managed  = False
        ordering = ['category', 'name']
 
    def __str__(self):
        return self.name

# LocalActivity model
class LocalActivity(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity     = models.ForeignKey(
        Activity,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column='activity_id',
        related_name='local_activities'
    )
    host         = models.ForeignKey(
        HostProfile, on_delete=models.CASCADE,
        null=True, blank=True,
        db_column='host_id', related_name='local_activities'
    )
    guide        = models.ForeignKey(
        'GuideProfile', on_delete=models.CASCADE,
        null=True, blank=True,
        db_column='guide_id', related_name='guide_local_activities'
    )
    set_price    = models.FloatField(null=True, blank=True)
    special_note = models.TextField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'local_activity'
        managed  = False
 
    def __str__(self):
        return f'LocalActivity {self.id}'


class Booking(models.Model):
    BOOKING_TYPE_CHOICES = [
        ('per_night', 'Per Night'),
        ('halfday', 'Half Day'),
        ('entire_place', 'Entire Place'),
    ]
    
    BOOKING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tourist_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='bookings',
        db_column='tourist_profile_id'
    )
    stay = models.ForeignKey(
        Stay,
        on_delete=models.CASCADE,
        related_name='bookings',
        db_column='stay_id',
        null=True,
        blank=True
    )
    booking_type = models.CharField(max_length=20, choices=BOOKING_TYPE_CHOICES, null=True, blank=True)
    booking_status = models.CharField(max_length=20, choices=BOOKING_STATUS_CHOICES, default='pending')
    total_amount = models.FloatField(default=0.0)
    guest_count = models.IntegerField(default=1)
    arrival_time = models.DateTimeField(null=True, blank=True)
    departure_time = models.DateTimeField(null=True, blank=True)
    special_note = models.TextField(null=True, blank=True)
    pickup_latitude = models.FloatField(null=True, blank=True)
    pickup_longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'booking'
        managed = False
        ordering = ['-created_at']

    def __str__(self):
        return f"Booking {self.id} - {self.booking_status}"


class TouristLocation(models.Model):
    """
    A named pickup/drop-off location selectable by tourists.
 
    Two kinds of rows:
      is_system=True  → seeded by admin (e.g. Galle Fort, Sigiriya, airports)
      is_system=False → saved by a specific tourist (their private favourites)
    """
 
    CATEGORY_CHOICES = [
        ('City',     'City'),
        ('Heritage', 'Heritage'),
        ('Beach',    'Beach'),
        ('Nature',   'Nature'),
        ('Airport',  'Airport'),
        ('Hotel',    'Hotel'),
        ('Other',    'Other'),
    ]
 
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name        = models.TextField()                      # "Galle Fort"
    region      = models.TextField(default='')            # "Southern"
    category    = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default='Other')
    latitude    = models.FloatField()
    longitude   = models.FloatField()
    is_system   = models.BooleanField(default=True)       # True = visible to all
    is_active   = models.BooleanField(default=True)
    created_by  = models.ForeignKey(                      # NULL for system rows
        'UserProfile',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column='created_by',
        related_name='saved_locations',
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
 
    class Meta:
        db_table = 'tourist_location'
        managed  = False          # table is created via raw SQL / migration below
        ordering = ['category', 'name']
 
    def __str__(self):
        return f'{self.name} ({self.category})'


# ── Specialization (master table) ──────────────────────────────────────────
class Specialization(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug       = models.TextField(unique=True)
    label      = models.TextField()
    category   = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'specialization'
        managed  = False
        ordering = ['category', 'label']

    def __str__(self):
        return self.label


# ── GuideSpecialization (bridge table) ─────────────────────────────────────
class GuideSpecialization(models.Model):
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    guide_profile = models.ForeignKey(
        GuideProfile,
        on_delete=models.CASCADE,
        db_column='guide_profile_id',
        related_name='guide_specializations',
    )
    specialization = models.ForeignKey(
        Specialization,
        on_delete=models.CASCADE,
        db_column='specialization_id',
        related_name='guide_specializations',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'guide_specialization'
        managed         = False
        unique_together = ('guide_profile', 'specialization')

    def __str__(self):
        return f"{self.guide_profile} – {self.specialization.label}"