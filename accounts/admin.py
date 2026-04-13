# accounts/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Avg, Count
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
        return "—"
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
            return format_html('<img src="{}" style="height:100px;border-radius:5px;" />', obj.photo_url)
        return "—"
    preview_photo.short_description = "Preview"


class StayDocumentInline(admin.TabularInline):
    model = StayDocument
    extra = 0
    fields = ['document_type', 'document_url', 'view_document', 'verification_status']
    readonly_fields = ['view_document', 'created_at']

    def view_document(self, obj):
        if obj.document_url:
            return format_html('<a href="{}" target="_blank">Open File</a>', obj.document_url)
        return "—"
    view_document.short_description = "View"


class StayFacilityInline(admin.TabularInline):
    model = StayFacility
    extra = 0
    fields = ('facility', 'special_note')
    raw_id_fields = ('facility',)


class StayAvailabilityInline(admin.TabularInline):
    model = StayAvailability
    extra = 0
    fields = ['date', 'total_room', 'occupied_room', 'is_available']
    readonly_fields = ['occupied_room']
    ordering = ['date']

    def get_queryset(self, request):
        from datetime import date
        qs = super().get_queryset(request)
        return qs.filter(date__gte=date.today()).order_by('date')[:30]


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


class LocalActivityInline(admin.TabularInline):
    model = LocalActivity
    extra = 0
    fields = ['activity', 'set_price', 'special_note']
    raw_id_fields = ['activity']


class ReviewInline(admin.TabularInline):
    model = Review
    extra = 0
    can_delete = False
    readonly_fields = ['tourist', 'rating', 'review', 'created_at']
    fields = ['tourist', 'rating', 'review', 'created_at']

    def get_queryset(self, request):
        return super().get_queryset(request).order_by('-created_at')[:10]


class GuideAvailabilityInline(admin.TabularInline):
    model = GuideAvailability
    extra = 0
    fields = ['date', 'start_time', 'end_time', 'is_booked']
    readonly_fields = ['is_booked']
    ordering = ['date', 'start_time']

    def get_queryset(self, request):
        from datetime import date
        return super().get_queryset(request).filter(date__gte=date.today()).order_by('date', 'start_time')[:20]


# ══════════════════════════════════════════════════════════
# REFERENCE DATA
# ══════════════════════════════════════════════════════════

@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'user_count']
    search_fields = ['name', 'code']
    list_editable = ['is_active']
    ordering = ['name']

    def user_count(self, obj):
        return UserLanguage.objects.filter(language=obj).count()
    user_count.short_description = 'Users'


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
    list_display = ['name', 'country', 'is_active', 'stay_count', 'guide_count', 'updated_at']
    search_fields = ['name']
    list_filter = ['is_active', 'country']
    list_editable = ['is_active']
    ordering = ['name']

    def stay_count(self, obj):
        return Stay.objects.filter(city_id=obj.id).count()
    stay_count.short_description = 'Stays'

    def guide_count(self, obj):
        return GuideProfile.objects.filter(city_id=obj.id).count()
    guide_count.short_description = 'Guides'


@admin.register(Facilities)
class FacilitiesAdmin(admin.ModelAdmin):
    list_display = ['name', 'addon_price', 'is_active', 'usage_count', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    list_editable = ['is_active', 'addon_price']

    def usage_count(self, obj):
        return StayFacility.objects.filter(facility=obj).count()
    usage_count.short_description = 'Used in Stays'


@admin.register(Interest)
class InterestAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'is_active', 'user_count', 'created_at']
    list_filter = ['category', 'is_active']
    search_fields = ['name']
    ordering = ['category', 'name']
    list_editable = ['is_active']

    def user_count(self, obj):
        return UserInterest.objects.filter(interest=obj).count()
    user_count.short_description = 'Users'


# ══════════════════════════════════════════════════════════
# USER PROFILES
# ══════════════════════════════════════════════════════════

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = [
        'full_name', 'user_role', 'profile_status',
        'is_complete', 'phone_number', 'country', 'created_at'
    ]
    list_filter = ['user_role', 'profile_status', 'is_complete', 'gender', 'country']
    search_fields = ['first_name', 'last_name', 'phone_number', 'auth_user_id']
    readonly_fields = ['auth_user_id', 'created_at', 'updated_at', 'profile_pic_preview']
    inlines = [UserInterestInline, UserLanguageInline]
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Basic Information', {
            'fields': ('auth_user_id', 'first_name', 'last_name', 'user_role')
        }),
        ('Contact Information', {
            'fields': ('phone_number', 'country')
        }),
        ('Personal Details', {
            'fields': ('date_of_birth', 'gender', 'profile_pic_preview', 'profile_pic', 'profile_bio')
        }),
        ('Status', {
            'fields': ('profile_status', 'is_complete')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def profile_pic_preview(self, obj):
        if obj.profile_pic:
            return format_html(
                '<img src="{}" style="height:80px;width:80px;object-fit:cover;border-radius:50%;" />',
                obj.profile_pic
            )
        return "—"
    profile_pic_preview.short_description = "Photo"


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
        return "—"
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
        'get_full_name', 'verification_status', 'get_city', 'avg_rating',
        'rate_per_hour', 'total_completed_bookings', 'booking_response_rate',
        'is_available', 'is_SLTDA_verified', 'total_earned'
    ]
    list_filter = [
        'verification_status', 'is_available', 'is_SLTDA_verified',
        'experience_years'
    ]
    search_fields = ['user_profile__first_name', 'user_profile__last_name', 'user_profile__phone_number']
    readonly_fields = [
        'total_completed_bookings', 'total_rejected_bookings',
        'total_cancelled_bookings', 'booking_response_rate', 'avg_rating',
        'total_tip_earned', 'total_earned', 'created_at', 'updated_at'
    ]
    inlines = [ProfileDocumentInline, GuideAvailabilityInline, LocalActivityInline, ReviewInline]
    actions = ['approve_guides', 'reject_guides', 'set_sltda_verified', 'toggle_availability']
    date_hierarchy = 'created_at'

    def get_full_name(self, obj):
        return obj.user_profile.full_name
    get_full_name.short_description = 'Name'
    get_full_name.admin_order_field = 'user_profile__first_name'

    def get_city(self, obj):
        try:
            city = City.objects.get(id=obj.city_id)
            return city.name
        except City.DoesNotExist:
            return "—"
    get_city.short_description = 'City'

    def approve_guides(self, request, queryset):
        queryset.update(verification_status='verified')
        for guide in queryset:
            ProfileDocument.objects.filter(guide=guide).update(verification_status='verified')
        self.message_user(request, f"{queryset.count()} guide(s) approved.")
    approve_guides.short_description = "✅ Approve selected guides"

    def reject_guides(self, request, queryset):
        queryset.update(verification_status='rejected')
        for guide in queryset:
            ProfileDocument.objects.filter(guide=guide).update(verification_status='rejected')
        self.message_user(request, f"{queryset.count()} guide(s) rejected.")
    reject_guides.short_description = "❌ Reject selected guides"

    def set_sltda_verified(self, request, queryset):
        queryset.update(is_SLTDA_verified=True)
        self.message_user(request, f"{queryset.count()} guide(s) marked as SLTDA verified.")
    set_sltda_verified.short_description = "🏅 Mark as SLTDA Verified"

    def toggle_availability(self, request, queryset):
        for guide in queryset:
            guide.is_available = not guide.is_available
            guide.save(update_fields=['is_available'])
        self.message_user(request, f"Toggled availability for {queryset.count()} guide(s).")
    toggle_availability.short_description = "🔄 Toggle availability"

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
    date_hierarchy = 'created_at'

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
    approve_hosts.short_description = "✅ Approve selected hosts"

    def reject_hosts(self, request, queryset):
        queryset.update(verification_status='rejected')
        for host in queryset:
            ProfileDocument.objects.filter(host=host).update(verification_status='rejected')
        self.message_user(request, f"{queryset.count()} host(s) rejected.")
    reject_hosts.short_description = "❌ Reject selected hosts"


# ══════════════════════════════════════════════════════════
# STAYS
# ══════════════════════════════════════════════════════════

@admin.register(Stay)
class StayAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'get_host_name', 'type', 'get_city_name', 'price_per_night',
        'room_count', 'max_guests', 'verification_status', 'is_active',
        'review_count', 'avg_rating_display', 'created_at'
    ]
    list_filter = [
        'type', 'verification_status', 'is_active', 'room_available',
        'halfday_available', 'entire_place_is_available'
    ]
    search_fields = ['name', 'description', 'host__user_profile__first_name', 'town']
    readonly_fields = ['created_at', 'updated_at', 'review_count', 'avg_rating_display']
    inlines = [StayPicInline, StayDocumentInline, StayFacilityInline, StayAvailabilityInline]
    actions = ['mark_verified', 'mark_rejected', 'activate', 'deactivate']
    date_hierarchy = 'created_at'

    def get_host_name(self, obj):
        return obj.host.user_profile.full_name
    get_host_name.short_description = 'Host'
    get_host_name.admin_order_field = 'host__user_profile__first_name'

    def get_city_name(self, obj):
        try:
            return City.objects.get(id=obj.city_id).name
        except City.DoesNotExist:
            return '—'
    get_city_name.short_description = 'City'

    def review_count(self, obj):
        return Review.objects.filter(stay=obj).count()
    review_count.short_description = 'Reviews'

    def avg_rating_display(self, obj):
        agg = Review.objects.filter(stay=obj).aggregate(avg=Avg('rating'))
        val = agg['avg']
        return f"{round(val, 1)} ⭐" if val else "—"
    avg_rating_display.short_description = 'Avg Rating'

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
        ('Status', {'fields': ('is_active', 'verification_status', 'review_count', 'avg_rating_display')}),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.action(description='✅ Mark selected stays as Verified')
    def mark_verified(self, request, queryset):
        queryset.update(verification_status='verified')
        self.message_user(request, f"{queryset.count()} stay(s) verified.")

    @admin.action(description='❌ Mark selected stays as Rejected')
    def mark_rejected(self, request, queryset):
        queryset.update(verification_status='rejected')
        self.message_user(request, f"{queryset.count()} stay(s) rejected.")

    @admin.action(description='🟢 Activate selected stays')
    def activate(self, request, queryset):
        updated = queryset.filter(verification_status='verified').update(is_active=True)
        self.message_user(request, f"{updated} verified stay(s) activated.")

    @admin.action(description='🔴 Deactivate selected stays')
    def deactivate(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} stay(s) deactivated.")


@admin.register(StayAvailability)
class StayAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('stay', 'date', 'total_room', 'occupied_room', 'is_available')
    list_filter = ('is_available',)
    search_fields = ('stay__name',)
    ordering = ('stay', 'date')
    raw_id_fields = ('stay',)
    date_hierarchy = 'date'


@admin.register(StayDocument)
class StayDocumentAdmin(admin.ModelAdmin):
    list_display = ['document_type', 'get_stay_name', 'verification_status', 'view_document', 'created_at']
    list_filter = ['verification_status', 'document_type']
    search_fields = ['stay__name']
    actions = ['mark_verified', 'mark_rejected']

    def get_stay_name(self, obj):
        return obj.stay.name
    get_stay_name.short_description = "Stay"

    def view_document(self, obj):
        if obj.document_url:
            return format_html('<a href="{}" target="_blank">Open</a>', obj.document_url)
        return "—"
    view_document.short_description = "Doc"

    @admin.action(description='✅ Mark selected documents as Verified')
    def mark_verified(self, request, queryset):
        queryset.update(verification_status='verified')

    @admin.action(description='❌ Mark selected documents as Rejected')
    def mark_rejected(self, request, queryset):
        queryset.update(verification_status='rejected')


@admin.register(ProfileDocument)
class ProfileDocumentAdmin(admin.ModelAdmin):
    list_display = ['document_type', 'get_owner', 'verification_status', 'view_document', 'created_at']
    list_filter = ['verification_status', 'document_type']
    search_fields = [
        'guide__user_profile__first_name',
        'guide__user_profile__last_name',
        'host__user_profile__first_name',
        'host__user_profile__last_name',
    ]
    actions = ['mark_verified', 'mark_rejected']

    def get_owner(self, obj):
        if obj.guide:
            return format_html('<b>Guide:</b> {}', obj.guide.user_profile.full_name)
        if obj.host:
            return format_html('<b>Host:</b> {}', obj.host.user_profile.full_name)
        return "—"
    get_owner.short_description = "Owner"

    def view_document(self, obj):
        if obj.document_url:
            return format_html('<a href="{}" target="_blank">Open</a>', obj.document_url)
        return "—"
    view_document.short_description = "Doc"

    @admin.action(description='✅ Mark selected documents as Verified')
    def mark_verified(self, request, queryset):
        queryset.update(verification_status='verified')

    @admin.action(description='❌ Mark selected documents as Rejected')
    def mark_rejected(self, request, queryset):
        queryset.update(verification_status='rejected')


# ══════════════════════════════════════════════════════════
# INTERESTS & USER INTERESTS
# ══════════════════════════════════════════════════════════

@admin.register(UserInterest)
class UserInterestAdmin(admin.ModelAdmin):
    list_display = ['get_user_name', 'get_user_role', 'get_interest_name', 'get_interest_category', 'created_at']
    list_filter = ['interest__category', 'created_at']
    search_fields = ['user_profile__first_name', 'user_profile__last_name', 'interest__name']

    def get_user_name(self, obj):
        return obj.user_profile.full_name
    get_user_name.short_description = 'User'

    def get_user_role(self, obj):
        return obj.user_profile.user_role.capitalize()
    get_user_role.short_description = 'Role'

    def get_interest_name(self, obj):
        return obj.interest.name
    get_interest_name.short_description = 'Interest'

    def get_interest_category(self, obj):
        return obj.interest.category
    get_interest_category.short_description = 'Category'


# ══════════════════════════════════════════════════════════
# GUIDE AVAILABILITY
# ══════════════════════════════════════════════════════════

@admin.register(GuideAvailabilityPattern)
class GuideAvailabilityPatternAdmin(admin.ModelAdmin):
    list_display = ('get_guide_name', 'reccuring_type', 'start_time', 'end_time', 'active_from', 'active_until')
    list_filter = ('reccuring_type',)
    search_fields = ('guide_profile__user_profile__first_name', 'guide_profile__user_profile__last_name')
    raw_id_fields = ('guide_profile',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    date_hierarchy = 'active_from'

    def get_guide_name(self, obj):
        return obj.guide_profile.user_profile.full_name
    get_guide_name.short_description = 'Guide'


@admin.register(GuideAvailability)
class GuideAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('get_guide_name', 'date', 'start_time', 'end_time', 'is_booked')
    list_filter = ('is_booked', 'date')
    search_fields = ('guide_profile__user_profile__first_name', 'guide_profile__user_profile__last_name')
    ordering = ('date', 'start_time')
    raw_id_fields = ('guide_profile',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    date_hierarchy = 'date'
    actions = ['mark_unbooked']

    def get_guide_name(self, obj):
        return obj.guide_profile.user_profile.full_name
    get_guide_name.short_description = 'Guide'

    @admin.action(description='🔓 Mark selected slots as unbooked')
    def mark_unbooked(self, request, queryset):
        updated = queryset.update(is_booked=False)
        self.message_user(request, f"{updated} slot(s) marked as unbooked.")


# ══════════════════════════════════════════════════════════
# REVIEWS & MEDIA
# ══════════════════════════════════════════════════════════

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('get_tourist_name', 'get_target', 'rating', 'review_excerpt', 'created_at')
    list_filter = ('rating',)
    search_fields = (
        'tourist__user_profile__first_name',
        'tourist__user_profile__last_name',
        'guide__user_profile__first_name',
        'stay__name',
    )
    readonly_fields = ('id', 'created_at', 'updated_at')
    raw_id_fields = ('tourist', 'guide', 'stay')
    date_hierarchy = 'created_at'

    def get_tourist_name(self, obj):
        try:
            return obj.tourist.user_profile.full_name
        except Exception:
            return '—'
    get_tourist_name.short_description = 'Tourist'

    def get_target(self, obj):
        if obj.guide:
            return format_html('Guide: {}', obj.guide.user_profile.full_name)
        if obj.stay:
            return format_html('Stay: {}', obj.stay.name)
        return '—'
    get_target.short_description = 'Reviewed'

    def review_excerpt(self, obj):
        if obj.review:
            return obj.review[:60] + '…' if len(obj.review) > 60 else obj.review
        return '—'
    review_excerpt.short_description = 'Review'


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    list_display = (
        'get_uploader_name', 'entity_type', 'entity_id',
        'file_type', 'is_official', 'order_index',
        'preview', 'created_at'
    )
    list_filter = ('entity_type', 'file_type', 'is_official')
    search_fields = ('uploader__first_name', 'uploader__last_name')
    readonly_fields = ('id', 'created_at', 'preview')
    raw_id_fields = ('uploader',)

    def get_uploader_name(self, obj):
        return obj.uploader.full_name if obj.uploader else '—'
    get_uploader_name.short_description = 'Uploader'

    def preview(self, obj):
        if obj.file_type == 'image' and obj.file_path:
            return format_html(
                '<img src="{}" style="height:60px;border-radius:4px;" />',
                obj.file_path
            )
        elif obj.file_path:
            return format_html('<a href="{}" target="_blank">View File</a>', obj.file_path)
        return '—'
    preview.short_description = 'Preview'


# ══════════════════════════════════════════════════════════
# ACTIVITIES & BOOKINGS
# ══════════════════════════════════════════════════════════

@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'base_price', 'duration', 'difficulty_level', 'is_active', 'guide_count', 'created_at')
    list_filter = ('is_active', 'category', 'difficulty_level')
    search_fields = ('name', 'description')
    readonly_fields = ('id', 'created_at')
    list_editable = ['is_active']

    def guide_count(self, obj):
        return LocalActivity.objects.filter(activity=obj).count()
    guide_count.short_description = 'Guides'


@admin.register(LocalActivity)
class LocalActivityAdmin(admin.ModelAdmin):
    list_display = ('get_activity_name', 'get_guide_name', 'get_host_name', 'set_price', 'created_at')
    search_fields = (
        'host__user_profile__first_name',
        'guide__user_profile__first_name',
        'activity__name',
    )
    readonly_fields = ('id', 'created_at')
    raw_id_fields = ('host', 'guide', 'activity')
    list_filter = ['activity__category']

    def get_activity_name(self, obj):
        return obj.activity.name if obj.activity else '—'
    get_activity_name.short_description = 'Activity'

    def get_guide_name(self, obj):
        if obj.guide:
            return obj.guide.user_profile.full_name
        return '—'
    get_guide_name.short_description = 'Guide'

    def get_host_name(self, obj):
        if obj.host:
            return obj.host.user_profile.full_name
        return '—'
    get_host_name.short_description = 'Host'


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'get_tourist_name', 'get_stay_name', 'booking_type',
        'booking_status', 'total_amount', 'guest_count',
        'arrival_time', 'departure_time', 'created_at'
    )
    list_filter = ('booking_type', 'booking_status')
    search_fields = (
        'tourist_profile__first_name',
        'tourist_profile__last_name',
        'stay__name',
    )
    readonly_fields = ('id', 'created_at', 'updated_at')
    raw_id_fields = ('tourist_profile', 'stay')
    actions = ['mark_confirmed', 'mark_cancelled', 'mark_completed']
    date_hierarchy = 'created_at'

    def get_tourist_name(self, obj):
        if obj.tourist_profile:
            return obj.tourist_profile.full_name
        return '—'
    get_tourist_name.short_description = 'Tourist'

    def get_stay_name(self, obj):
        return obj.stay.name if obj.stay else '—'
    get_stay_name.short_description = 'Stay'

    @admin.action(description='✅ Mark selected bookings as Confirmed')
    def mark_confirmed(self, request, queryset):
        queryset.update(booking_status='confirmed')

    @admin.action(description='❌ Mark selected bookings as Cancelled')
    def mark_cancelled(self, request, queryset):
        queryset.update(booking_status='cancelled')

    @admin.action(description='🏁 Mark selected bookings as Completed')
    def mark_completed(self, request, queryset):
        queryset.update(booking_status='completed')