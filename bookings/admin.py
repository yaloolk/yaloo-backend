# bookings/admin.py

from django.contrib import admin
from .models import GuideBooking, BookedGuide


# ══════════════════════════════════════════════════════════
# INLINE
# ══════════════════════════════════════════════════════════

class BookedGuideInline(admin.TabularInline):
    model = BookedGuide
    extra = 0
    fields = ('guide_availability_id', 'price_per_slot_at_bookingtime', 'created_at')
    readonly_fields = ('id', 'created_at')


# ══════════════════════════════════════════════════════════
# GUIDE BOOKING
# ══════════════════════════════════════════════════════════

@admin.register(GuideBooking)
class GuideBookingAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'tourist_profile_id', 'guide_profile_id',
        'booking_date', 'start_time', 'end_time',
        'booking_status', 'payment_status',
        'total_amount', 'total_hours', 'created_at'
    )
    list_filter = ('booking_status', 'payment_status', 'booking_date')
    search_fields = ('id', 'tourist_profile_id', 'guide_profile_id', 'pickup_address', 'special_note')
    readonly_fields = (
        'id', 'total_hours', 'total_amount', 'rate_per_hour',
        'responded_at', 'created_at', 'updated_at'
    )
    ordering = ('-created_at',)
    inlines = [BookedGuideInline]
    actions = [
        'mark_confirmed', 'mark_rejected',
        'mark_completed', 'mark_cancelled',
        'mark_paid',
    ]

    fieldsets = (
        ('Parties', {
            'fields': ('id', 'tourist_profile_id', 'guide_profile_id')
        }),
        ('Schedule', {
            'fields': ('booking_date', 'start_time', 'end_time', 'total_hours')
        }),
        ('Financials', {
            'fields': ('rate_per_hour', 'total_amount', 'tip_amount')
        }),
        ('Status', {
            'fields': ('booking_status', 'payment_status')
        }),
        ('Details', {
            'fields': (
                'guest_count',
                'pickup_latitude', 'pickup_longitude', 'pickup_address',
                'special_note',
            )
        }),
        ('Guide Response', {
            'fields': ('guide_response_note', 'responded_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.action(description='Mark selected bookings as Confirmed')
    def mark_confirmed(self, request, queryset):
        queryset.filter(booking_status='pending').update(booking_status='confirmed')

    @admin.action(description='Mark selected bookings as Rejected')
    def mark_rejected(self, request, queryset):
        queryset.filter(booking_status='pending').update(booking_status='rejected')

    @admin.action(description='Mark selected bookings as Completed')
    def mark_completed(self, request, queryset):
        queryset.filter(booking_status='confirmed').update(booking_status='completed')

    @admin.action(description='Mark selected bookings as Cancelled')
    def mark_cancelled(self, request, queryset):
        queryset.filter(booking_status__in=['pending', 'confirmed']).update(booking_status='cancelled')

    @admin.action(description='Mark selected bookings as Paid')
    def mark_paid(self, request, queryset):
        queryset.update(payment_status='paid')


# ══════════════════════════════════════════════════════════
# BOOKED GUIDE SLOTS
# ══════════════════════════════════════════════════════════

@admin.register(BookedGuide)
class BookedGuideAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'booking', 'guide_availability_id',
        'price_per_slot_at_bookingtime', 'created_at'
    )
    search_fields = ('booking__id', 'guide_availability_id')
    readonly_fields = ('id', 'created_at')
    raw_id_fields = ('booking',)
    ordering = ('-created_at',)