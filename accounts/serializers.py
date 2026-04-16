# accounts/serializers.py

from rest_framework import serializers
from .models import (
    UserProfile, TouristProfile, GuideProfile, HostProfile, Stay, 
    Interest, UserInterest, Language, UserLanguage, City, 
    ProfileDocument, StayPic, StayDocument, Facilities, GuideAvailability, 
    Booking, GuideAvailabilityPattern, Review, StayAvailability, StayFacility, 
    LocalActivity, Media, Specialization, GuideSpecialization, Activity
)


class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = ['id', 'name', 'code']


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ['id', 'name', 'country', 'description']


class FacilitiesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Facilities
        fields = ['id', 'name', 'description', 'addon_price']


class UserLanguageSerializer(serializers.ModelSerializer):
    language = LanguageSerializer(read_only=True)
    language_id = serializers.UUIDField(write_only=True, required=False)
    
    class Meta:
        model = UserLanguage
        fields = ['id', 'language', 'language_id', 'proficiency', 'is_native', 'created_at']
        read_only_fields = ['id', 'created_at']


class ProfileDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileDocument
        fields = ['id', 'document_url', 'document_type', 'verification_status', 'created_at']
        read_only_fields = ['id', 'verification_status', 'created_at']




class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    verification_status = serializers.CharField(read_only=True)
    has_verified_stay = serializers.SerializerMethodField()
    
    class Meta:
        model = UserProfile
        fields = [
            'id', 'auth_user_id', 'first_name', 'last_name', 'full_name',
            'phone_number', 'date_of_birth', 'gender', 'country',
            'profile_pic', 'profile_bio', 'user_role', 'profile_status',
            'is_complete', 'verification_status', 'has_verified_stay', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'auth_user_id', 'verification_status', 'created_at', 'updated_at', 'full_name']

    def get_has_verified_stay(self, obj):
        """Check if the host has at least one stay with verification_status='verified'"""
        if obj.user_role == 'host' and hasattr(obj, 'host_profile'):
            # Check the related stays for this host
            return obj.host_profile.stays.filter(verification_status='verified').exists()
        return False

class TouristProfileSerializer(serializers.ModelSerializer):
    user_profile = UserProfileSerializer(read_only=True)
    
    class Meta:
        model = TouristProfile
        fields = '__all__'
        read_only_fields = ['id', 'user_profile', 'total_bookings', 'total_cancelled_bookings', 'trust_score']


class GuideProfileSerializer(serializers.ModelSerializer):
    user_profile = UserProfileSerializer(read_only=True)
    is_verified = serializers.BooleanField(read_only=True)
    languages = UserLanguageSerializer(source='user_profile.user_languages', many=True, read_only=True)
    documents = ProfileDocumentSerializer(many=True, read_only=True)
    
    class Meta:
        model = GuideProfile
        fields = [
            'id', 'user_profile', 'city_id', 'experience_years', 'education',
            'verification_status', 'rate_per_hour', 'avg_rating', 'booking_response_rate',
            'total_completed_bookings', 'total_rejected_bookings', 'total_cancelled_bookings',
            'total_tip_earned', 'total_earned', 'is_available', 'is_SLTDA_verified',
            'is_verified', 'languages', 'documents', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user_profile', 'avg_rating', 'booking_response_rate',
            'total_completed_bookings', 'total_rejected_bookings', 'total_cancelled_bookings',
            'total_tip_earned', 'total_earned', 'is_SLTDA_verified', 'documents'
        ]


class HostProfileSerializer(serializers.ModelSerializer):
    user_profile = UserProfileSerializer(read_only=True)
    is_verified = serializers.BooleanField(read_only=True)
    documents = ProfileDocumentSerializer(many=True, read_only=True)
    
    class Meta:
        model = HostProfile
        fields = [
            'id', 'user_profile', 'verification_status', 'no_of_stays_owned',
            'total_completed_bookings', 'total_rejected_bookings', 'total_cancelled_bookings',
            'response_rate', 'avg_rating', 'total_tip_earned', 'total_earned',
            'is_verified', 'documents', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user_profile', 'no_of_stays_owned',
            'total_completed_bookings', 'total_rejected_bookings',
            'total_cancelled_bookings', 'response_rate', 'avg_rating',
            'total_tip_earned', 'total_earned', 'documents'
        ]





class InterestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Interest
        fields = ['id', 'name', 'category', 'is_active']


class UserInterestSerializer(serializers.ModelSerializer):
    interest = InterestSerializer(read_only=True)
    interest_id = serializers.UUIDField(write_only=True)
    
    class Meta:
        model = UserInterest
        fields = ['id', 'interest', 'interest_id', 'created_at']
        read_only_fields = ['id', 'created_at']

class StayPicSerializer(serializers.ModelSerializer):
    class Meta:
        model  = StayPic
        fields = ['id', 'photo_url', 'position', 'is_cover']


class StayDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = StayDocument
        fields = ['id', 'document_url', 'document_type', 'verification_status']


class GuideAvailabilityPatternSerializer(serializers.ModelSerializer):
    """Serializer for the pattern (before splitting)"""
    class Meta:
        model = GuideAvailabilityPattern
        fields = ['id', 'reccuring_type', 'start_time', 'end_time', 
                  'active_from', 'active_until', 'created_at']
        read_only_fields = ['id', 'created_at']

class GuideAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model  = GuideAvailability
        fields = ['id', 'date', 'start_time', 'end_time', 'is_booked']
        read_only_fields = ['id', 'is_booked']


class ReviewSerializer(serializers.ModelSerializer):
    tourist_name  = serializers.CharField(
        source='tourist.user_profile.full_name', read_only=True)
    tourist_photo = serializers.CharField(
        source='tourist.user_profile.profile_pic', read_only=True)

    class Meta:
        model  = Review
        fields = ['id', 'rating', 'review', 'tourist_name', 'tourist_photo', 'created_at']

class CompleteGuideProfileSerializer(serializers.ModelSerializer):
    """Returns EVERYTHING the Flutter screen needs in one response"""
    
    # Flattened user profile fields
    full_name       = serializers.CharField(source='user_profile.full_name', read_only=True)
    profile_pic     = serializers.CharField(source='user_profile.profile_pic', read_only=True)
    profile_bio     = serializers.CharField(source='user_profile.profile_bio', read_only=True)
    phone_number    = serializers.CharField(source='user_profile.phone_number', read_only=True)
    date_of_birth   = serializers.DateField(source='user_profile.date_of_birth', read_only=True)
    gender          = serializers.CharField(source='user_profile.gender', read_only=True)
    country         = serializers.CharField(source='user_profile.country', read_only=True)
    user_role       = serializers.CharField(source='user_profile.user_role', read_only=True)
    is_complete     = serializers.BooleanField(source='user_profile.is_complete', read_only=True)
    user_profile_id = serializers.UUIDField(source='user_profile.id', read_only=True)
    auth_user_id    = serializers.UUIDField(source='user_profile.auth_user_id', read_only=True)
    
    # Computed/nested fields
    member_since = serializers.SerializerMethodField()
    city         = serializers.SerializerMethodField()
    languages    = serializers.SerializerMethodField()
    interests    = serializers.SerializerMethodField()
    specializations = serializers.SerializerMethodField()
    local_activities = serializers.SerializerMethodField()
    gallery      = serializers.SerializerMethodField()
    availability = serializers.SerializerMethodField()
    reviews      = serializers.SerializerMethodField()
    stats        = serializers.SerializerMethodField()

    class Meta:
        model  = GuideProfile
        fields = [
            'id', 'user_profile_id', 'auth_user_id',
            'city_id', 'city', 'experience_years', 'education',
            'verification_status', 'is_SLTDA_verified', 'is_available',
            'rate_per_hour', 'avg_rating', 'booking_response_rate',
            'total_completed_bookings', 'total_rejected_bookings',
            'total_cancelled_bookings', 'total_tip_earned', 'total_earned',
            'created_at', 'updated_at',
            # Flattened user profile
            'full_name', 'profile_pic', 'profile_bio',
            'phone_number', 'date_of_birth', 'gender', 'country',
            'user_role', 'is_complete', 'member_since',
            # Nested/computed
            'languages', 'interests', 'specializations', 'local_activities', 'gallery', 'availability', 'reviews', 'stats',
        ]

    def get_member_since(self, obj):
        return obj.created_at.strftime('%B %Y') if obj.created_at else None

    def get_city(self, obj):
        try:
            from .models import City
            city = City.objects.get(id=obj.city_id)
            return {'id': str(city.id), 'name': city.name, 'country': city.country}
        except Exception:
            return None

    def get_languages(self, obj):
        from .models import UserLanguage
        langs = UserLanguage.objects.filter(
            user_profile=obj.user_profile).select_related('language')
        return [
            {
                'id':          str(l.id),              # ← CHANGE THIS: was str(l.language.id)
                'language_id': str(l.language.id),     # ← ADD THIS line
                'name':        l.language.name,
                'code':        l.language.code,
                'proficiency': l.proficiency,
                'is_native':   l.is_native,
            }
            for l in langs
        ]

    def get_interests(self, obj):
        """Pull Interests from the UserProfile linked to this Guide"""
        from .models import UserInterest
        ints = UserInterest.objects.filter(
            user_profile=obj.user_profile
        ).select_related('interest')
        return [
            {
                'id': str(i.interest.id), 
                'name': i.interest.name,
                'category': i.interest.category
            } for i in ints
        ]

    def get_specializations(self, obj):
        """Pull Professional Specializations linked to the GuideProfile"""
        from .models import GuideSpecialization
        specs = GuideSpecialization.objects.filter(
            guide_profile=obj
        ).select_related('specialization')
        return [
            {
                'id': str(s.specialization.id),
                'slug': s.specialization.slug,
                'label': s.specialization.label,
                'category': s.specialization.category,
            } for s in specs
        ]

    def get_local_activities(self, obj):
        from .models import LocalActivity
        las = LocalActivity.objects.filter(
            guide=obj).select_related('activity')
        result = []
        for la in las:
            if la.activity is None:
                continue
            a = la.activity
            result.append({
                'local_activity_id': str(la.id),
                'activity_id':       str(a.id),
                'name':              a.name,
                'category':          a.category,
                'description':       a.description or '',
                'instruction':       a.instruction or '',
                'duration':          a.duration,
                'base_price':        a.base_price,
                'set_price':         la.set_price,
                'budget':            a.budget or '',
                'difficulty_level':  a.difficulty_level or '',
                'special_note':      la.special_note or '',
            })
        return result

    def get_gallery(self, obj):
        from .models import Media
        photos = Media.objects.filter(
            uploader=obj.user_profile, file_type='image').order_by('-created_at')
        return [{'id': str(p.id), 'url': p.file_path,
                 'created_at': p.created_at.isoformat()} for p in photos]

    def get_availability(self, obj):
        from datetime import date, timedelta
        today = date.today()
        slots = GuideAvailability.objects.filter(
            guide_profile=obj,
            date__gte=today,
            date__lte=today + timedelta(days=60)
        ).order_by('date', 'start_time')
        return GuideAvailabilitySerializer(slots, many=True).data

    def get_reviews(self, obj):
        reviews = Review.objects.filter(guide=obj).order_by('-created_at')[:10]
        return ReviewSerializer(reviews, many=True).data

    def get_stats(self, obj):
        return {
            'total_bookings': obj.total_completed_bookings or 0,
            'total_earnings': float(obj.total_earned or 0),
            'total_tips':     float(obj.total_tip_earned or 0),
            'avg_rating':     float(obj.avg_rating or 0),
            'review_count':   Review.objects.filter(guide=obj).count(),
            'response_rate':  float(obj.booking_response_rate or 0),
        }

# ══════════════════════════════════════════════════════════
# STAY SERIALIZERS
# ══════════════════════════════════════════════════════════

class StaySerializer(serializers.ModelSerializer):
    """Basic stay info for lists"""
    city_name = serializers.CharField(source='city.name', read_only=True)
    cover_photo = serializers.SerializerMethodField()
    
    class Meta:
        model = Stay
        fields = [
            'id', 'name', 'type', 'city_name', 'cover_photo',
            'verification_status', 'is_active', 'room_count',
            'max_guests', 'price_per_night', 'created_at'
        ]
    
    def get_cover_photo(self, obj):
        cover = Media.objects.filter(
            entity_type='stay',
            entity_id=obj.id,
            file_type='image'
        ).order_by('order_index').first()
        return cover.file_path if cover else None

class StayDetailSerializer(serializers.ModelSerializer):
    """Complete stay details"""
    city_name = serializers.CharField(source='city.name', read_only=True)
    photos = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()
    facilities = serializers.SerializerMethodField()
    
    class Meta:
        model = Stay
        fields = [
            'id', 'host_id', 'name', 'type', 'description',
            'house_no', 'street', 'town', 'city_id', 'city_name', 'postal_code',
            'latitude', 'longitude', 'room_count', 'room_available', 'max_guests',
            'price_per_night', 'price_entire_place', 'entire_place_is_available',
            'price_per_extra_guest', 'bathroom_count', 'shared_bathrooms',
            'price_per_halfday', 'halfday_available', 'standard_checkin_time',
            'standard_checkout_time', 'standard_halfday_checkout',
            'is_active', 'verification_status', 'photos', 'documents',
            'facilities', 'created_at', 'updated_at'
        ]
    
    def get_photos(self, obj):
        photos = Media.objects.filter(
            entity_type='stay',
            entity_id=obj.id,
            file_type='image'
        ).order_by('order_index')
        return [{
            'id': str(p.id),
            'url': p.file_path,
            'order': p.order_index
        } for p in photos]
    
    def get_documents(self, obj):
        docs = Media.objects.filter(
            entity_type='stay',
            entity_id=obj.id,
            file_type='document'
        )
        return [{
            'id': str(d.id),
            'url': d.file_path
        } for d in docs]
    
    def get_facilities(self, obj):
        facilities = StayFacility.objects.filter(
            stay=obj
        ).select_related('facility')
        return [str(sf.facility.id) for sf in facilities]

class StayAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model         = StayAvailability
        fields        = ['id', 'date', 'total_room', 'occupied_room', 'is_available']
        read_only_fields = ['id']


class StayFacilitySerializer(serializers.ModelSerializer):
    facility = FacilitiesSerializer(read_only=True)
    facility_id = serializers.UUIDField(write_only=True, source='facility.id', required=False)

    class Meta:
        model = StayFacility
        fields = ['id', 'facility', 'facility_id', 'special_note', 'created_at']
        read_only_fields = ['id', 'created_at']


class CompleteStaySerializer(serializers.ModelSerializer):
    """Full stay details with ALL related data"""
    photos = StayPicSerializer(many=True, read_only=True)
    documents = StayDocumentSerializer(many=True, read_only=True)
    facilities = serializers.SerializerMethodField()  # ✅ Changed to method field
    facility_ids = serializers.SerializerMethodField()  # ✅ Added for Flutter
    cover_photo = serializers.SerializerMethodField()
    city_name = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    avg_rating = serializers.SerializerMethodField()

    class Meta:
        model = Stay
        fields = [
            'id', 'name', 'type', 'description',
            'house_no', 'street', 'town', 'city_id', 'city_name', 'postal_code',
            'latitude', 'longitude',
            'room_count', 'room_available', 'max_guests',
            'bathroom_count', 'shared_bathrooms',
            'price_per_night', 'price_per_halfday', 'halfday_available',
            'price_entire_place', 'entire_place_is_available',
            'price_per_extra_guest',
            'standard_checkin_time', 'standard_checkout_time', 'standard_halfday_checkout',
            'is_active', 'verification_status', 'created_at', 'updated_at',
            'photos', 'documents', 'facilities', 'facility_ids',
            'cover_photo', 'review_count', 'avg_rating',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_facilities(self, obj):
        """Return full facility objects"""
        stay_facilities = obj.stay_facilities.select_related('facility').all()
        return [{
            'id': str(sf.facility.id),
            'name': sf.facility.name,
            'description': sf.facility.description,
            'addon_price': float(sf.facility.addon_price) if sf.facility.addon_price else 0,
            'special_note': sf.special_note,
        } for sf in stay_facilities]

    def get_facility_ids(self, obj):
        """Return just facility IDs for Flutter checkboxes"""
        return [str(sf.facility.id) for sf in obj.stay_facilities.all()]

    def get_cover_photo(self, obj):
        cover = obj.photos.filter(is_cover=True).first() or obj.photos.first()
        return cover.photo_url if cover else None

    def get_city_name(self, obj):
        try:
            city = City.objects.get(id=obj.city_id)
            return city.name
        except:
            return ''

    def get_review_count(self, obj):
        return obj.stay_reviews.count()

    def get_avg_rating(self, obj):
        from django.db.models import Avg
        agg = obj.stay_reviews.aggregate(avg=Avg('rating'))
        return round(float(agg['avg'] or 0), 1)

class CompleteHostProfileSerializer(serializers.ModelSerializer):
    """
    Everything the Flutter HostProfileScreen needs — mirrors CompleteGuideProfileSerializer.
    Flattened user fields + nested stays/gallery/reviews/stats.
    """
    # Flattened user_profile fields
    full_name       = serializers.CharField(source='user_profile.full_name', read_only=True)
    first_name      = serializers.CharField(source='user_profile.first_name', read_only=True)
    last_name       = serializers.CharField(source='user_profile.last_name', read_only=True)
    profile_pic     = serializers.CharField(source='user_profile.profile_pic', read_only=True)
    profile_bio     = serializers.CharField(source='user_profile.profile_bio', read_only=True)
    phone_number    = serializers.CharField(source='user_profile.phone_number', read_only=True)
    date_of_birth   = serializers.DateField(source='user_profile.date_of_birth', read_only=True)
    gender          = serializers.CharField(source='user_profile.gender', read_only=True)
    country         = serializers.CharField(source='user_profile.country', read_only=True)
    user_role       = serializers.CharField(source='user_profile.user_role', read_only=True)
    is_complete     = serializers.BooleanField(source='user_profile.is_complete', read_only=True)
    user_profile_id = serializers.UUIDField(source='user_profile.id', read_only=True)
    auth_user_id    = serializers.UUIDField(source='user_profile.auth_user_id', read_only=True)

    # Computed fields
    member_since      = serializers.SerializerMethodField()
    stays             = serializers.SerializerMethodField()
    gallery           = serializers.SerializerMethodField()
    reviews           = serializers.SerializerMethodField()
    stats             = serializers.SerializerMethodField()
    has_verified_stay = serializers.SerializerMethodField()

    class Meta:
        model  = HostProfile
        fields = [
            'id', 'user_profile_id', 'auth_user_id',
            'verification_status', 'is_verified',
            'no_of_stays_owned', 'response_rate', 'avg_rating',
            'total_completed_bookings', 'total_rejected_bookings',
            'total_cancelled_bookings', 'total_tip_earned', 'total_earned',
            'created_at', 'updated_at',
            # Flattened user
            'full_name', 'first_name', 'last_name', 'profile_pic', 'profile_bio',
            'phone_number', 'date_of_birth', 'gender', 'country',
            'user_role', 'is_complete', 'member_since', 'has_verified_stay',
            # Nested
            'stays', 'gallery', 'reviews', 'stats',
        ]

    def get_member_since(self, obj):
        return obj.created_at.strftime('%B %Y') if obj.created_at else None

    def get_has_verified_stay(self, obj):
        return obj.stays.filter(verification_status='verified').exists()

    def get_stays(self, obj):
        stays = obj.stays.prefetch_related(
            'photos', 'documents', 'stay_facilities__facility'
        ).all()
        return CompleteStaySerializer(stays, many=True).data

    def get_gallery(self, obj):
        try:
            from .models import Media
            photos = Media.objects.filter(
                uploader=obj.user_profile, file_type='image'
            ).order_by('-created_at')
            return [
                {'id': str(p.id), 'url': p.file_path, 'created_at': p.created_at.isoformat()}
                for p in photos
            ]
        except Exception:
            return []

    def get_reviews(self, obj):
        reviews = Review.objects.filter(
            stay__host=obj
        ).select_related('tourist__user_profile').order_by('-created_at')[:10]
        return ReviewSerializer(reviews, many=True).data

    def get_stats(self, obj):
        review_count = Review.objects.filter(stay__host=obj).count()
        return {
            'total_stays':    obj.stays.count(),
            'verified_stays': obj.stays.filter(verification_status='verified').count(),
            'pending_stays':  obj.stays.filter(verification_status='pending').count(),
            'total_bookings': obj.total_completed_bookings or 0,
            'total_earnings': float(obj.total_earned or 0),
            'total_tips':     float(obj.total_tip_earned or 0),
            'avg_rating':     float(obj.avg_rating or 0),
            'review_count':   review_count,
            'response_rate':  float(obj.response_rate or 0),
        }


class MediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Media
        fields = [
            'id', 'uploader_id', 'entity_type', 'entity_id',
            'file_path', 'file_type', 'is_official', 'order_index', 'created_at'
        ]


# ══════════════════════════════════════════════════════════
# BOOKING SERIALIZERS
# ══════════════════════════════════════════════════════════

class BookingSerializer(serializers.ModelSerializer):
    tourist_name = serializers.SerializerMethodField()
    tourist_photo = serializers.SerializerMethodField()
    tourist_phone = serializers.SerializerMethodField()
    
    class Meta:
        model = Booking
        fields = [
            'id', 'tourist_profile_id', 'tourist_name', 'tourist_photo',
            'tourist_phone', 'booking_type', 'booking_status', 'total_amount',
            'guest_count', 'arrival_time', 'departure_time', 'special_note',
            'pickup_latitude', 'pickup_longitude', 'created_at', 'updated_at'
        ]
    
    def get_tourist_name(self, obj):
        user = obj.tourist_profile
        return f"{user.first_name or ''} {user.last_name or ''}".strip()
    
    def get_tourist_photo(self, obj):
        return obj.tourist_profile.profile_pic
    
    def get_tourist_phone(self, obj):
        return obj.tourist_profile.phone_number


class SpecializationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Specialization
        fields = ['id', 'slug', 'label', 'category']


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Activity
        fields = [
            'id', 'name', 'category', 'base_price', 'description',
            'instruction', 'duration', 'is_active', 'budget',
            'difficulty_level', 'created_at',
        ]
 
 
class LocalActivitySerializer(serializers.ModelSerializer):
    activity = ActivitySerializer(read_only=True)
    activity_id = serializers.UUIDField(write_only=True)
 
    class Meta:
        model  = LocalActivity
        fields = ['id', 'activity', 'activity_id', 'set_price', 'special_note', 'created_at']
        read_only_fields = ['id', 'created_at']