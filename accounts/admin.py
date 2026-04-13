# accounts/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Language, UserLanguage, City, Facilities,
    UserProfile, TouristProfile, GuideProfile, HostProfile,
    Stay, StayPic, StayDocument, StayFacility, StayAvailability,
    ProfileDocument, Interest, UserInterest,
    Media, GuideAvailabilityPattern, GuideAvailability,
    Review, Activity, LocalActivity, Booking,
)


# ══════════════════════════════════════════════════════════
# INLINES
# ══════════════════════════════════════════════════════════

class ProfileDocumentInline(admin.TabularInline):
    model = ProfileDocument
    extra = 0
    readonly_fields = ['view_document', 'created_at']
    fields = ['document_type', 'document_url', 'view_document', 'verification_status', 'created_at']

    def view_document(self, obj):
        if obj.document_url:
            return format_html('<a href="{}" target="_blank">View Document</a>', obj.document_url)
        return "-"
    view_document.short_description = "Document Link"


class UserInterestInline(admin.TabularInline):
    model = UserInterest
    extra = 1
    autocomplete_fields = ['interest']


class UserLanguageInline(admin.TabularInline):
    model = UserLanguage
    extra = 1
    autocomplete_fields = ['language']


class StayPicInline(admin.TabularInline):
    model = StayPic
    extra = 1
    fields = ['photo_url', 'preview_photo', 'position', 'is_cover']
    readonly_fields = ['preview_photo', 'created_at']

    def preview_photo(self, obj):
        if obj.photo_url:
            return format_html('<img src="{}" style="height: 100px; border-radius: 5px;" />', obj.photo_url)
        return "-"
    preview_photo.short_description = "Preview"


class StayDocumentInline(admin.TabularInline):
    model = StayDocument
    extra = 0
    fields = ['document_type', 'document_url', 'view_document', 'verification_status']
    readonly_fields = ['view_document', 'created_at']

    def view_document(self, obj):
        if obj.document_url:
            return format_html('<a href="{}" target="_blank">Open File</a>', obj.document_url)
        return "-"
    view_document.short_description = "View"


class StayFacilityInline(admin.TabularInline):
    model = StayFacility
    extra = 0
    fields = ('facility', 'special_note')
    raw_id_fields = ('facility',)


class HostStayInline(admin.TabularInline):
    model = Stay
    extra = 0
    can_delete = False
    readonly_fields = [
        'name', 'type', 'town', 'city_id',
        'room_count', 'price_per_night',
        'verification_status', 'is_active', 'created_at',
        'view_stay',
    ]
    fields = [
        'name', 'type', 'town', 'city_id',
        'room_count', 'price_per_night',
        'verification_status', 'is_active', 'created_at',
        'view_stay',
    ]

    def view_stay(self, obj):
        from django.urls import reverse
        url = reverse('admin:accounts_stay_change', args=[obj.pk])
        return format_html('<a href="{}" target="_blank">Open Stay →</a>', url)
    view_stay.short_description = "Details"


# ══════════════════════════════════════════════════════════
# REFERENCE DATA
# ══════════════════════════════════════════════════════════

@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active']
    search_fields = ['name', 'code']
    list_editable = ['is_active']
    ordering = ['name']


@admin.register(UserLanguage)
class UserLanguageAdmin(admin.ModelAdmin):
    list_display = ['get_user_name', 'get_language_name', 'proficiency', 'is_native']
    list_filter = ['proficiency', 'is_native', 'language__name']
    search_fields = ['user_profile__first_name', 'user_profile__last_name', 'language__name']

    def get_user_name(self, obj):
        return obj.user_profile.full_name
    get_user_name.short_description = 'User'

    def get_language_name(self, obj):
        return obj.language.name
    get_language_name.short_description = 'Language'


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ['name', 'country', 'is_active', 'updated_at']
    search_fields = ['name']
    list_filter = ['is_active', 'country']
    list_editable = ['is_active']
    ordering = ['name']


@admin.register(Facilities)
class FacilitiesAdmin(admin.ModelAdmin):
    list_display = ['name', 'addon_price', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    list_editable = ['is_active', 'addon_price']


@admin.register(Interest)
class InterestAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'is_active', 'created_at']
    list_filter = ['category', 'is_active']
    search_fields = ['name']
    ordering = ['category', 'name']
    list_editable = ['is_active']


# ══════════════════════════════════════════════════════════
# USER PROFILES
# ══════════════════════════════════════════════════════════

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = [
        'full_name', 'user_role', 'profile_status',
        'is_complete', 'created_at'
    ]
    list_filter = ['user_role', 'profile_status', 'is_complete', 'gender']
    search_fields = ['first_name', 'last_name', 'phone_number', 'auth_user_id']
    readonly_fields = ['auth_user_id', 'created_at', 'updated_at']
    inlines = [UserInterestInline, UserLanguageInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('auth_user_id', 'first_name', 'last_name', 'user_role')
        }),
        ('Contact Information', {
            'fields': ('phone_number', 'country')
        }),
        ('Personal Details', {
            'fields': ('date_of_birth', 'gender', 'profile_pic', 'profile_bio')
        }),
        ('Status', {
            'fields': ('profile_status', 'is_complete')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TouristProfile)
class TouristProfileAdmin(admin.ModelAdmin):
    list_display = [
        'get_full_name', 'travel_style', 'get_preferred_language',
        'total_bookings', 'trust_score', 'created_at'
    ]
    list_filter = ['travel_style']
    search_fields = [
        'user_profile__first_name',
        'user_profile__last_name',
        'passport_number'
    ]
    readonly_fields = ['created_at', 'updated_at', 'trust_score']

    def get_full_name(self, obj):
        return obj.user_profile.full_name
    get_full_name.short_description = 'Name'

    def get_preferred_language(self, obj):
        if obj.preferred_language and obj.preferred_language.language:
            return obj.preferred_language.language.name
        return "-"
    get_preferred_language.short_description = 'Language'

    fieldsets = (
        ('User Profile', {'fields': ('user_profile',)}),
        ('Travel Preferences', {
            'fields': ('travel_style', 'preferred_language', 'dietery_preferences', 'other_preferences')
        }),
        ('Documents', {'fields': ('passport_number',)}),
        ('Emergency Contact', {
            'fields': (
                'emergency_contact_name',
                'emergency_contact_relation',
                'emergency_contact_number'
            )
        }),
        ('Statistics', {
            'fields': ('total_bookings', 'total_cancelled_bookings', 'trust_score')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(GuideProfile)
class GuideProfileAdmin(admin.ModelAdmin):
    list_display = [
        'get_full_name', 'verification_status', 'avg_rating',
        'total_completed_bookings', 'booking_response_rate', 'total_earned'
    ]
    list_filter = ['verification_status', 'is_available', 'is_SLTDA_verified']
    search_fields = ['user_profile__first_name', 'user_profile__last_name']
    readonly_fields = [
        'total_completed_bookings', 'total_rejected_bookings',
        'total_cancelled_bookings', 'booking_response_rate', 'avg_rating',
        'total_tip_earned', 'total_earned', 'created_at', 'updated_at'
    ]
    inlines = [ProfileDocumentInline]
    actions = ['approve_guides', 'reject_guides']

    def get_full_name(self, obj):
        return obj.user_profile.full_name
    get_full_name.short_description = 'Name'

    def approve_guides(self, request, queryset):
        queryset.update(verification_status='verified')
        for guide in queryset:
            ProfileDocument.objects.filter(guide=guide).update(verification_status='verified')
        self.message_user(request, f"{queryset.count()} guide(s) approved.")
    approve_guides.short_description = "Approve selected guides"

    def reject_guides(self, request, queryset):
        queryset.update(verification_status='rejected')
        for guide in queryset:
            ProfileDocument.objects.filter(guide=guide).update(verification_status='rejected')
        self.message_user(request, f"{queryset.count()} guide(s) rejected.")
    reject_guides.short_description = "Reject selected guides"

    fieldsets = (
        ('Profile', {'fields': ('user_profile', 'city_id', 'experience_years', 'education')}),
        ('Status', {'fields': ('verification_status', 'is_available', 'is_SLTDA_verified')}),
        ('Financials', {'fields': ('rate_per_hour', 'total_earned', 'total_tip_earned')}),
        ('Stats', {
            'fields': (
                'avg_rating', 'booking_response_rate',
                'total_completed_bookings', 'total_rejected_bookings', 'total_cancelled_bookings'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(HostProfile)
class HostProfileAdmin(admin.ModelAdmin):
    list_display = [
        'get_full_name', 'get_phone', 'get_gender',
        'verification_status', 'no_of_stays_owned',
        'avg_rating', 'total_completed_bookings', 'total_earned',
    ]
    list_filter = ['verification_status']
    search_fields = [
        'user_profile__first_name',
        'user_profile__last_name',
        'user_profile__phone_number',
    ]
    readonly_fields = [
        'user_profile', 'no_of_stays_owned',
        'total_completed_bookings', 'total_rejected_bookings',
        'total_cancelled_bookings', 'response_rate', 'avg_rating',
        'total_tip_earned', 'total_earned', 'created_at', 'updated_at',
    ]
    inlines = [ProfileDocumentInline, HostStayInline]
    actions = ['approve_hosts', 'reject_hosts']

    fieldsets = (
        ('User Profile', {'fields': ('user_profile',)}),
        ('Verification', {'fields': ('verification_status',)}),
        ('Stays & Bookings', {
            'fields': (
                'no_of_stays_owned',
                'total_completed_bookings', 'total_rejected_bookings',
                'total_cancelled_bookings', 'response_rate',
            )
        }),
        ('Earnings & Rating', {
            'fields': ('avg_rating', 'total_tip_earned', 'total_earned')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_full_name(self, obj):
        return obj.user_profile.full_name
    get_full_name.short_description = 'Name'
    get_full_name.admin_order_field = 'user_profile__first_name'

    def get_phone(self, obj):
        return obj.user_profile.phone_number or '—'
    get_phone.short_description = 'Phone'

    def get_gender(self, obj):
        return (obj.user_profile.gender or '—').capitalize()
    get_gender.short_description = 'Gender'

    def approve_hosts(self, request, queryset):
        queryset.update(verification_status='verified')
        for host in queryset:
            ProfileDocument.objects.filter(host=host).update(verification_status='verified')
        self.message_user(request, f"{queryset.count()} host(s) approved.")
    approve_hosts.short_description = "Approve selected hosts"

    def reject_hosts(self, request, queryset):
        queryset.update(verification_status='rejected')
        for host in queryset:
            ProfileDocument.objects.filter(host=host).update(verification_status='rejected')
        self.message_user(request, f"{queryset.count()} host(s) rejected.")
    reject_hosts.short_description = "Reject selected hosts"


# ══════════════════════════════════════════════════════════
# STAYS
# ══════════════════════════════════════════════════════════

@admin.register(Stay)
class StayAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'get_host_name', 'type', 'price_per_night',
        'verification_status', 'is_active', 'created_at'
    ]
    list_filter = ['type', 'verification_status', 'is_active', 'room_available',
                   'halfday_available', 'entire_place_is_available']
    search_fields = ['name', 'description', 'host__user_profile__first_name']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [StayPicInline, StayDocumentInline, StayFacilityInline]
    actions = ['mark_verified', 'mark_rejected', 'activate', 'deactivate']

    def get_host_name(self, obj):
        return obj.host.user_profile.full_name
    get_host_name.short_description = 'Host'

    fieldsets = (
        ('Basic Information', {
            'fields': ('host', 'name', 'type', 'description')
        }),
        ('Location', {
            'fields': ('house_no', 'street', 'town', 'city_id', 'postal_code', 'latitude', 'longitude')
        }),
        ('Stay Details', {
            'fields': ('room_count', 'room_available', 'max_guests', 'bathroom_count', 'shared_bathrooms')
        }),
        ('Pricing', {
            'fields': (
                'price_per_night', 'price_per_extra_guest',
                'entire_place_is_available', 'price_entire_place',
                'halfday_available', 'price_per_halfday',
            )
        }),
        ('Check-in/out', {
            'fields': ('standard_checkin_time', 'standard_checkout_time', 'standard_halfday_checkout')
        }),
        ('Status', {'fields': ('is_active', 'verification_status')}),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.action(description='Mark selected stays as Verified')
    def mark_verified(self, request, queryset):
        queryset.update(verification_status='verified')

    @admin.action(description='Mark selected stays as Rejected')
    def mark_rejected(self, request, queryset):
        queryset.update(verification_status='rejected')

    @admin.action(description='Activate selected stays')
    def activate(self, request, queryset):
        queryset.filter(verification_status='verified').update(is_active=True)

    @admin.action(description='Deactivate selected stays')
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(StayAvailability)
class StayAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('stay', 'date', 'total_room', 'occupied_room', 'is_available')
    list_filter = ('is_available',)
    search_fields = ('stay__name',)
    ordering = ('stay', 'date')
    raw_id_fields = ('stay',)


@admin.register(StayDocument)
class StayDocumentAdmin(admin.ModelAdmin):
    list_display = ['document_type', 'get_stay_name', 'verification_status', 'created_at']
    list_filter = ['verification_status', 'document_type']
    search_fields = ['stay__name']

    def get_stay_name(self, obj):
        return obj.stay.name
    get_stay_name.short_description = "Stay"


@admin.register(ProfileDocument)
class ProfileDocumentAdmin(admin.ModelAdmin):
    list_display = ['document_type', 'get_owner', 'verification_status', 'created_at']
    list_filter = ['verification_status', 'document_type']

    def get_owner(self, obj):
        if obj.guide:
            return f"Guide: {obj.guide.user_profile.full_name}"
        if obj.host:
            return f"Host: {obj.host.user_profile.full_name}"
        return "-"
    get_owner.short_description = "Owner"


# ══════════════════════════════════════════════════════════
# INTERESTS & USER INTERESTS
# ══════════════════════════════════════════════════════════

@admin.register(UserInterest)
class UserInterestAdmin(admin.ModelAdmin):
    list_display = ['get_user_name', 'get_interest_name', 'created_at']
    list_filter = ['interest__category', 'created_at']
    search_fields = ['user_profile__first_name', 'user_profile__last_name', 'interest__name']

    def get_user_name(self, obj):
        return obj.user_profile.full_name
    get_user_name.short_description = 'User'

    def get_interest_name(self, obj):
        return obj.interest.name
    get_interest_name.short_description = 'Interest'


# ══════════════════════════════════════════════════════════
# GUIDE AVAILABILITY
# ══════════════════════════════════════════════════════════

@admin.register(GuideAvailabilityPattern)
class GuideAvailabilityPatternAdmin(admin.ModelAdmin):
    list_display = ('guide_profile', 'reccuring_type', 'start_time', 'end_time', 'active_from', 'active_until')
    list_filter = ('reccuring_type',)
    search_fields = ('guide_profile__user_profile__first_name',)
    raw_id_fields = ('guide_profile',)
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(GuideAvailability)
class GuideAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('guide_profile', 'date', 'start_time', 'end_time', 'is_booked')
    list_filter = ('is_booked', 'date')
    search_fields = ('guide_profile__user_profile__first_name',)
    ordering = ('date', 'start_time')
    raw_id_fields = ('guide_profile',)
    readonly_fields = ('id', 'created_at', 'updated_at')


# ══════════════════════════════════════════════════════════
# REVIEWS & MEDIA
# ══════════════════════════════════════════════════════════

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('tourist', 'guide', 'stay', 'rating', 'created_at')
    list_filter = ('rating',)
    search_fields = (
        'tourist__user_profile__first_name',
        'guide__user_profile__first_name',
        'stay__name',
    )
    readonly_fields = ('id', 'created_at', 'updated_at')
    raw_id_fields = ('tourist', 'guide', 'stay')


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    list_display = ('uploader', 'entity_type', 'entity_id', 'file_type', 'is_official', 'order_index', 'created_at')
    list_filter = ('entity_type', 'file_type', 'is_official')
    search_fields = ('uploader__first_name', 'uploader__last_name')
    readonly_fields = ('id', 'created_at')
    raw_id_fields = ('uploader',)


# ══════════════════════════════════════════════════════════
# ACTIVITIES & BOOKINGS
# ══════════════════════════════════════════════════════════

@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    readonly_fields = ('id', 'created_at')


@admin.register(LocalActivity)
class LocalActivityAdmin(admin.ModelAdmin):
    list_display = ('id', 'activity_id', 'host', 'guide', 'set_price', 'created_at')
    search_fields = ('host__user_profile__first_name', 'guide__user_profile__first_name')
    readonly_fields = ('id', 'created_at')
    raw_id_fields = ('host', 'guide')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'tourist_profile', 'stay', 'booking_type',
        'booking_status', 'total_amount', 'guest_count', 'arrival_time', 'created_at'
    )
    list_filter = ('booking_type', 'booking_status')
    search_fields = ('tourist_profile__first_name', 'tourist_profile__last_name', 'stay__name')
    readonly_fields = ('id', 'created_at', 'updated_at')
    raw_id_fields = ('tourist_profile', 'stay')
    actions = ['mark_confirmed', 'mark_cancelled', 'mark_completed']

    @admin.action(description='Mark selected bookings as Confirmed')
    def mark_confirmed(self, request, queryset):
        queryset.update(booking_status='confirmed')

    @admin.action(description='Mark selected bookings as Cancelled')
    def mark_cancelled(self, request, queryset):
        queryset.update(booking_status='cancelled')

    @admin.action(description='Mark selected bookings as Completed')
    def mark_completed(self, request, queryset):
        queryset.update(booking_status='completed')