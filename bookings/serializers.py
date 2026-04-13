# bookings/serializers.py

from rest_framework import serializers
from .models import GuideBooking, BookedGuide, StayBooking   


class BookedGuideSerializer(serializers.ModelSerializer):
    class Meta:
        model  = BookedGuide
        fields = ['id', 'guide_availability_id', 'price_per_slot_at_bookingtime']


class GuideBookingSerializer(serializers.ModelSerializer):
    """
    Full booking detail — used for tourist & guide detail views.
    tourist_info and guide_info are injected by the view (not DB fields).
    """
    locked_slots = BookedGuideSerializer(many=True, read_only=True)

    # Read-only enriched fields populated in the view
    tourist_name  = serializers.SerializerMethodField()
    tourist_photo = serializers.SerializerMethodField()
    tourist_phone = serializers.SerializerMethodField()
    guide_name    = serializers.SerializerMethodField()
    guide_photo   = serializers.SerializerMethodField()
    guide_phone   = serializers.SerializerMethodField()
    city_name     = serializers.SerializerMethodField()

    class Meta:
        model  = GuideBooking
        fields = [
            'id',
            'tourist_profile_id', 'tourist_name', 'tourist_photo', 'tourist_phone',
            'guide_profile_id',   'guide_name',   'guide_photo',   'guide_phone',
            'city_name',
            'booking_date', 'start_time', 'end_time', 'total_hours',
            'rate_per_hour', 'total_amount', 'tip_amount',
            'booking_status', 'payment_status',
            'guest_count',
            'pickup_latitude', 'pickup_longitude', 'pickup_address',
            'special_note', 'guide_response_note', 'responded_at',
            'locked_slots',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'total_amount', 'rate_per_hour', 'total_hours',
            'booking_status', 'payment_status', 'responded_at',
            'created_at', 'updated_at',
        ]

    def get_tourist_name(self, obj):
        req = self.context.get('request')
        if req and hasattr(req, '_tourist_map'):
            p = req._tourist_map.get(str(obj.tourist_profile_id))
            if p:
                return f"{p.first_name or ''} {p.last_name or ''}".strip()
        return ''

    def get_tourist_photo(self, obj):
        req = self.context.get('request')
        if req and hasattr(req, '_tourist_map'):
            p = req._tourist_map.get(str(obj.tourist_profile_id))
            return p.profile_pic if p else ''
        return ''

    def get_tourist_phone(self, obj):
        req = self.context.get('request')
        if req and hasattr(req, '_tourist_map'):
            p = req._tourist_map.get(str(obj.tourist_profile_id))
            return p.phone_number if p else ''
        return ''

    def get_guide_name(self, obj):
        req = self.context.get('request')
        
        # 1. Try the optimized map first
        if req and hasattr(req, '_guide_profile_map'):
            gp = req._guide_profile_map.get(str(obj.guide_profile_id))
            if gp:
                return f"{gp.user_profile.first_name or ''} {gp.user_profile.last_name or ''}".strip()
        
        # 2. Fallback to database lookup
        try:
            from accounts.models import GuideProfile 
            gp = GuideProfile.objects.get(id=obj.guide_profile_id)
            return f"{gp.user_profile.first_name or ''} {gp.user_profile.last_name or ''}".strip()
        except Exception:
            return ''

    def get_guide_photo(self, obj):
        req = self.context.get('request')
        if req and hasattr(req, '_guide_profile_map'):
            gp = req._guide_profile_map.get(str(obj.guide_profile_id))
            if gp:
                return gp.user_profile.profile_pic or ''
        
        # FALLBACK
        try:
            from accounts.models import GuideProfile
            gp = GuideProfile.objects.get(id=obj.guide_profile_id)
            return gp.user_profile.profile_pic or ''
        except Exception:
            return ''

    def get_guide_phone(self, obj):
        req = self.context.get('request')
        if req and hasattr(req, '_guide_profile_map'):
            gp = req._guide_profile_map.get(str(obj.guide_profile_id))
            if gp:
                return gp.user_profile.phone_number or ''
        return ''

    def get_city_name(self, obj):
        req = self.context.get('request')
        if req and hasattr(req, '_guide_profile_map'):
            gp = req._guide_profile_map.get(str(obj.guide_profile_id))
            if gp:
                try:
                    from accounts.models import City
                    city = City.objects.get(id=gp.city_id)
                    return city.name
                except Exception:
                    pass
        return ''


class GuideBookingListSerializer(serializers.ModelSerializer):
 
    guide_name  = serializers.SerializerMethodField()
    guide_photo = serializers.SerializerMethodField()
    city_name   = serializers.SerializerMethodField()
    tourist_name  = serializers.SerializerMethodField()
    tourist_photo = serializers.SerializerMethodField()

    class Meta:
        model  = GuideBooking
        fields = [
            'id',
            'tourist_profile_id', 'tourist_name', 'tourist_photo',
            'guide_profile_id',   'guide_name',   'guide_photo',
            'city_name',
            'booking_date', 'start_time', 'end_time', 'total_hours',
            'total_amount', 'booking_status', 'payment_status',
            'created_at',
        ]
    def get_guide_name(self, obj):
        try:
            from accounts.models import GuideProfile
            gp = GuideProfile.objects.get(id=obj.guide_profile_id)
            return gp.user_profile.full_name
        except Exception:
            return ''

    def get_guide_photo(self, obj):
        try:
            from accounts.models import GuideProfile
            gp = GuideProfile.objects.get(id=obj.guide_profile_id)
            return gp.user_profile.profile_pic or ''
        except Exception:
            return ''

    def get_city_name(self, obj):
        try:
            from accounts.models import GuideProfile, City
            gp = GuideProfile.objects.get(id=obj.guide_profile_id)
            city = City.objects.get(id=gp.city_id)
            return city.name
        except Exception:
            return ''
            
    def get_tourist_name(self, obj):
        try:
            from accounts.models import TouristProfile
            tp = TouristProfile.objects.get(id=obj.tourist_profile_id)
            return f"{tp.first_name or ''} {tp.last_name or ''}".strip()
        except Exception:
            return ''

    def get_tourist_photo(self, obj):
        try:
            from accounts.models import TouristProfile
            tp = TouristProfile.objects.get(id=obj.tourist_profile_id)
            return tp.profile_pic or ''
        except Exception:
            return ''


class CreateGuideBookingSerializer(serializers.Serializer):

    guide_profile_id = serializers.UUIDField()
    booking_date     = serializers.DateField()
    start_time       = serializers.TimeField()
    end_time         = serializers.TimeField()
    guest_count      = serializers.IntegerField(min_value=1, default=1)
    pickup_latitude  = serializers.FloatField(required=False, allow_null=True)
    pickup_longitude = serializers.FloatField(required=False, allow_null=True)
    pickup_address   = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    special_note     = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, data):
        if data['end_time'] <= data['start_time']:
            raise serializers.ValidationError('end_time must be after start_time')
        return data


class RespondBookingSerializer(serializers.Serializer):
    """Guide accepts or rejects a pending booking."""
    action             = serializers.ChoiceField(choices=['accept', 'reject'])
    guide_response_note = serializers.CharField(required=False, allow_blank=True, allow_null=True)



# Stay Booking 

class CreateStayBookingSerializer(serializers.Serializer):
    """Validates tourist's booking request payload."""
 
    stay_id          = serializers.UUIDField()
    checkin_date     = serializers.DateField()
    checkout_date    = serializers.DateField()
    booking_type     = serializers.ChoiceField(
        choices=['per_night', 'halfday', 'entire_place'],
        default='per_night'
    )
    room_count       = serializers.IntegerField(min_value=1, default=1)
    guest_count      = serializers.IntegerField(min_value=1, default=1)
    meal_preference  = serializers.ChoiceField(
        choices=['veg', 'non_veg', 'halal', 'none'], default='none'
    )
    checkin_time     = serializers.TimeField(required=False, allow_null=True)
    checkout_time    = serializers.TimeField(required=False, allow_null=True)
    special_note     = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
 
    # Tourist personal info (filled at booking step-1)
    tourist_full_name = serializers.CharField(max_length=255)
    tourist_passport  = serializers.CharField(
        max_length=100, required=False, allow_blank=True, allow_null=True
    )
    tourist_phone     = serializers.CharField(max_length=30)
    tourist_email     = serializers.EmailField()
    tourist_country   = serializers.CharField(
        max_length=100, required=False, allow_blank=True, allow_null=True
    )
    tourist_gender    = serializers.CharField(
        max_length=20, required=False, allow_blank=True, allow_null=True
    )
 
    def validate(self, data):
        if data['checkout_date'] <= data['checkin_date']:
            raise serializers.ValidationError(
                'checkout_date must be after checkin_date'
            )
        return data
 
 
class RespondStayBookingSerializer(serializers.Serializer):
    """Host accepts or rejects a stay booking request."""
    action             = serializers.ChoiceField(choices=['accept', 'reject'])
    host_response_note = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
 
 
class StayBookingSerializer(serializers.ModelSerializer):
    """
    Full booking detail returned to both tourist and host.
    Extra display fields (names, photos, stay details) are
    injected by the view via request._* maps — same pattern
    as GuideBookingSerializer.
    """
 
    # ── Tourist info ──────────────────────────────────────────────────────────
    tourist_photo    = serializers.SerializerMethodField()
 
    # ── Host / stay info ──────────────────────────────────────────────────────
    stay_name        = serializers.SerializerMethodField()
    stay_cover_photo = serializers.SerializerMethodField()
    host_name        = serializers.SerializerMethodField()
    host_photo       = serializers.SerializerMethodField()
    host_phone       = serializers.SerializerMethodField()
    city_name        = serializers.SerializerMethodField()
 
    class Meta:
        model  = StayBooking
        fields = [
            'id',
            'tourist_profile_id',
            'tourist_full_name', 'tourist_photo',
            'tourist_passport', 'tourist_phone',
            'tourist_email', 'tourist_country', 'tourist_gender',
 
            'stay_id', 'stay_name', 'stay_cover_photo',
            'host_profile_id', 'host_name', 'host_photo', 'host_phone',
            'city_name',
 
            'checkin_date', 'checkout_date', 'total_nights',
            'booking_type', 'room_count', 'guest_count', 'meal_preference',
            'checkin_time', 'checkout_time',
 
            'price_per_night', 'total_amount', 'tip_amount',
            'booking_status', 'payment_status',
 
            'special_note', 'host_response_note', 'responded_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'total_amount', 'price_per_night', 'total_nights',
            'booking_status', 'payment_status', 'responded_at',
            'created_at', 'updated_at',
        ]
 
    # ── Context helpers ───────────────────────────────────────────────────────
 
    def _stay_map(self, obj):
        req = self.context.get('request')
        if req and hasattr(req, '_stay_map'):
            return req._stay_map.get(str(obj.stay_id))
        return None
 
    def _host_map(self, obj):
        req = self.context.get('request')
        if req and hasattr(req, '_host_map'):
            return req._host_map.get(str(obj.host_profile_id))
        return None
 
    def _tourist_photo_map(self, obj):
        req = self.context.get('request')
        if req and hasattr(req, '_tourist_photo_map'):
            return req._tourist_photo_map.get(str(obj.tourist_profile_id))
        return None
 
    # ── SerializerMethodField implementations ─────────────────────────────────
 
    def get_tourist_photo(self, obj):
        pic = self._tourist_photo_map(obj)
        return pic or ''
 
    def get_stay_name(self, obj):
        stay = self._stay_map(obj)
        return stay.name if stay else ''
 
    def get_stay_cover_photo(self, obj):
        stay = self._stay_map(obj)
        if not stay:
            return ''
        try:
            from accounts.models import Media
            m = Media.objects.filter(
                entity_type='stay', entity_id=stay.id, file_type='image'
            ).order_by('order_index').first()
            return m.file_path if m else ''
        except Exception:
            return ''
 
    def get_host_name(self, obj):
        host = self._host_map(obj)
        if not host:
            return ''
        up = host.user_profile
        return f"{up.first_name or ''} {up.last_name or ''}".strip()
 
    def get_host_photo(self, obj):
        host = self._host_map(obj)
        return host.user_profile.profile_pic if host else ''
 
    def get_host_phone(self, obj):
        host = self._host_map(obj)
        return host.user_profile.phone_number if host else ''
 
    def get_city_name(self, obj):
        stay = self._stay_map(obj)
        if not stay or not stay.city_id:
            return ''
        try:
            from accounts.models import City
            return City.objects.get(id=stay.city_id).name
        except Exception:
            return ''
 
 
class StayBookingListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for lists (my-bookings, host-requests)."""
    stay_name        = serializers.SerializerMethodField()
    stay_cover_photo = serializers.SerializerMethodField()
    host_name        = serializers.SerializerMethodField()
    city_name        = serializers.SerializerMethodField()
 
    class Meta:
        model  = StayBooking
        fields = [
            'id',
            'tourist_profile_id', 'tourist_full_name', 'tourist_phone',
            'stay_id', 'stay_name', 'stay_cover_photo',
            'host_profile_id', 'host_name',
            'city_name',
            'checkin_date', 'checkout_date', 'total_nights',
            'room_count', 'guest_count', 'meal_preference',
            'total_amount', 'price_per_night',
            'booking_status', 'payment_status',
            'created_at',
        ]
 
    def _stay(self, obj):
        req = self.context.get('request')
        if req and hasattr(req, '_stay_map'):
            return req._stay_map.get(str(obj.stay_id))
        return None
 
    def _host(self, obj):
        req = self.context.get('request')
        if req and hasattr(req, '_host_map'):
            return req._host_map.get(str(obj.host_profile_id))
        return None
 
    def get_stay_name(self, obj):
        s = self._stay(obj)
        return s.name if s else ''
 
    def get_stay_cover_photo(self, obj):
        s = self._stay(obj)
        if not s:
            return ''
        try:
            from accounts.models import Media
            m = Media.objects.filter(
                entity_type='stay', entity_id=s.id, file_type='image'
            ).order_by('order_index').first()
            return m.file_path if m else ''
        except Exception:
            return ''
 
    def get_host_name(self, obj):
        h = self._host(obj)
        if not h:
            return ''
        up = h.user_profile
        return f"{up.first_name or ''} {up.last_name or ''}".strip()
 
    def get_city_name(self, obj):
        s = self._stay(obj)
        if not s or not s.city_id:
            return ''
        try:
            from accounts.models import City
            return City.objects.get(id=s.city_id).name
        except Exception:
            return ''
