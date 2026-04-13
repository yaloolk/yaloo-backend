# bookings/models.py

import uuid
from django.db import models


class GuideBooking(models.Model):
    """
    Maps to  public.booking  in Supabase.
    Stores one booking request from a tourist to a guide.
    """

    BOOKING_STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('confirmed', 'Confirmed'),
        ('rejected',  'Rejected'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]

    PAYMENT_STATUS_CHOICES = [
        ('unpaid',   'Unpaid'),
        ('paid',     'Paid'),
        ('refunded', 'Refunded'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ── Parties ───────────────────────────────────────────────────────────────
    tourist_profile_id = models.UUIDField(db_index=True)   # → user_profile.id
    guide_profile_id   = models.UUIDField(db_index=True)   # → guide_profile.id

    # ── Schedule ──────────────────────────────────────────────────────────────
    booking_date = models.DateField()
    start_time   = models.TimeField()
    end_time     = models.TimeField()
    total_hours  = models.FloatField(default=1.0)

    # ── Financials ────────────────────────────────────────────────────────────
    rate_per_hour = models.FloatField(default=0.0)
    total_amount  = models.FloatField(default=0.0)
    tip_amount    = models.FloatField(default=0.0)

    # ── Status ────────────────────────────────────────────────────────────────
    booking_status = models.CharField(
        max_length=20, choices=BOOKING_STATUS_CHOICES, default='pending'
    )
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default='unpaid'
    )

    # ── Extras ────────────────────────────────────────────────────────────────
    guest_count         = models.IntegerField(default=1)
    pickup_latitude     = models.FloatField(null=True, blank=True)
    pickup_longitude    = models.FloatField(null=True, blank=True)
    pickup_address      = models.TextField(null=True, blank=True)
    special_note        = models.TextField(null=True, blank=True)

    # ── Guide response ────────────────────────────────────────────────────────
    guide_response_note = models.TextField(null=True, blank=True)
    responded_at        = models.DateTimeField(null=True, blank=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # stripe payment
    stripe_payment_intent_id = models.TextField(null=True, blank=True)
    stripe_capture_status    = models.CharField(max_length=30, default='pending')

    class Meta:
        db_table = 'guide_booking'     # ← exact Supabase table name
        managed  = False         # ← Django does NOT create/alter this table
        ordering = ['-created_at']

    def __str__(self):
        return f"Booking {self.id} | {self.booking_status}"


class BookedGuide(models.Model):
    """
    Maps to  public.booked_guide  in Supabase.
    One row per availability slot that is locked by a booking.

    Supabase schema:
        id                          uuid  PK
        booking_id                  uuid  FK → booking(id) ON DELETE CASCADE
        guide_availability_id       uuid  FK → guide_availability(id)
        price_per_slot_at_bookingtime real  nullable
        created_at                  timestamptz
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    booking = models.ForeignKey(
        GuideBooking,
        on_delete=models.CASCADE,
        related_name='locked_slots',
        db_column='booking_id',
    )

    # UUID of the guide_availability row (lives in accounts app)
    guide_availability_id = models.UUIDField()

    # Price snapshot at the moment of booking (matches real column)
    price_per_slot_at_bookingtime = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'booked_guide'   # ← exact Supabase table name
        managed  = False            # ← Django does NOT create/alter this table

    def __str__(self):
        return f"BookedGuide slot={self.guide_availability_id} booking={self.booking_id}"


# Stay Booking

class StayBooking(models.Model):
    """
    One booking request from a tourist to a host for a stay.
    Lives in public.stay_booking table (Supabase).
    """
 
    BOOKING_STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('confirmed', 'Confirmed'),
        ('rejected',  'Rejected'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
 
    PAYMENT_STATUS_CHOICES = [
        ('unpaid',   'Unpaid'),
        ('paid',     'Paid'),
        ('refunded', 'Refunded'),
    ]
 
    BOOKING_TYPE_CHOICES = [
        ('per_night',    'Per Night'),
        ('halfday',      'Half Day'),
        ('entire_place', 'Entire Place'),
    ]
 
    MEAL_PREFERENCE_CHOICES = [
        ('veg',     'Vegetarian'),
        ('non_veg', 'Non-Vegetarian'),
        ('halal',   'Halal'),
        ('none',    'No Preference'),
    ]
 
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
 
    # ── Parties ───────────────────────────────────────────────────────────────
    tourist_profile_id = models.UUIDField(db_index=True)   # → user_profile.id
    stay_id            = models.UUIDField(db_index=True)    # → stay.id
    host_profile_id    = models.UUIDField(db_index=True)    # → host_profile.id
 
    # ── Schedule ──────────────────────────────────────────────────────────────
    checkin_date  = models.DateField()
    checkout_date = models.DateField()
    total_nights  = models.IntegerField(default=1)
 
    # ── Booking type & details ────────────────────────────────────────────────
    booking_type    = models.CharField(
        max_length=20, choices=BOOKING_TYPE_CHOICES, default='per_night'
    )
    room_count      = models.IntegerField(default=1)
    guest_count     = models.IntegerField(default=1)
    meal_preference = models.CharField(
        max_length=20, choices=MEAL_PREFERENCE_CHOICES, default='none'
    )
 
    # ── Times ────────────────────────────────────────────────────────────────
    checkin_time  = models.TimeField(null=True, blank=True)
    checkout_time = models.TimeField(null=True, blank=True)
 
    # ── Financials ────────────────────────────────────────────────────────────
    price_per_night = models.FloatField(default=0.0)
    total_amount    = models.FloatField(default=0.0)
    tip_amount      = models.FloatField(default=0.0)
 
    # ── Status ────────────────────────────────────────────────────────────────
    booking_status = models.CharField(
        max_length=20, choices=BOOKING_STATUS_CHOICES, default='pending'
    )
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default='unpaid'
    )
 
    # ── Extras ────────────────────────────────────────────────────────────────
    special_note          = models.TextField(null=True, blank=True)
    host_response_note    = models.TextField(null=True, blank=True)
    responded_at          = models.DateTimeField(null=True, blank=True)
 
    # Tourist info snapshot (filled at booking time for display)
    tourist_full_name    = models.CharField(max_length=255, null=True, blank=True)
    tourist_passport     = models.CharField(max_length=100, null=True, blank=True)
    tourist_phone        = models.CharField(max_length=30,  null=True, blank=True)
    tourist_email        = models.CharField(max_length=255, null=True, blank=True)
    tourist_country      = models.CharField(max_length=100, null=True, blank=True)
    tourist_gender       = models.CharField(max_length=20,  null=True, blank=True)
 
    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # stripe payment
    stripe_payment_intent_id = models.TextField(null=True, blank=True)
    stripe_capture_status    = models.CharField(max_length=30, default='pending')
 
    class Meta:
        db_table = 'stay_booking'
        managed  = False          # Supabase owns the table DDL
        ordering = ['-created_at']
 
    def __str__(self):
        return f"StayBooking {self.id} | {self.booking_status}"

