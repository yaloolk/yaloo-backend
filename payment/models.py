# payment/models.py

import uuid
from django.db import models


class CancellationPolicy(models.Model):
    """
    Admin-configurable cancellation fee tiers.
    Only one policy should be active at a time.
    """
    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name                = models.CharField(max_length=100, default='Standard Policy')
    is_active           = models.BooleanField(default=True)

    # Hours before booking start → determines which tier applies
    free_cancel_hours   = models.IntegerField(default=24)   # > this  = free
    partial_fee_hours   = models.IntegerField(default=12)   # > this  = partial fee
    partial_fee_percent = models.FloatField(default=10.0)   # % charged in partial tier
    # anything < partial_fee_hours = 100% fee (no refund)

    created_by          = models.UUIDField(null=True, blank=True)
    created_at          = models.DateTimeField(auto_now_add=True)
    updated_at          = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cancellation_policy'
        managed  = False

    def __str__(self):
        return f"{self.name} ({'active' if self.is_active else 'inactive'})"


class Payment(models.Model):
    """
    One row per booking payment.
    booking_type discriminates guide vs stay.
    """
    PAYMENT_STATUS_CHOICES = [
        ('awaiting_capture',    'Awaiting Capture'),
        ('captured',            'Captured'),
        ('cancelled',           'Cancelled'),
        ('refunded',            'Refunded'),
        ('partially_refunded',  'Partially Refunded'),
    ]

    id                        = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    booking_type              = models.CharField(max_length=10)   # 'guide' | 'stay'
    guide_booking_id          = models.UUIDField(null=True, blank=True)
    stay_booking_id           = models.UUIDField(null=True, blank=True)
    tourist_profile_id        = models.UUIDField(db_index=True)

    stripe_payment_intent_id  = models.TextField()
    stripe_charge_id          = models.TextField(null=True, blank=True)

    base_amount               = models.FloatField(default=0.0)
    platform_fee              = models.FloatField(default=0.0)
    total_paid                = models.FloatField(default=0.0)
    currency                  = models.CharField(max_length=10, default='LKR')

    payment_status            = models.CharField(
        max_length=30, choices=PAYMENT_STATUS_CHOICES, default='awaiting_capture'
    )
    payment_captured_at       = models.DateTimeField(null=True, blank=True)

    cancellation_fee_percent  = models.FloatField(default=0.0)
    refund_amount             = models.FloatField(default=0.0)
    refunded_at               = models.DateTimeField(null=True, blank=True)
    stripe_refund_id          = models.TextField(null=True, blank=True)

    expires_at                = models.DateTimeField()
    created_at                = models.DateTimeField(auto_now_add=True)
    updated_at                = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payment'
        managed  = False
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment {self.id} [{self.booking_type}] {self.payment_status}"


class CancellationRecord(models.Model):
    """Audit trail — one row per cancelled booking."""
    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    booking_type        = models.CharField(max_length=10)   # 'guide' | 'stay'
    guide_booking_id    = models.UUIDField(null=True, blank=True)
    stay_booking_id     = models.UUIDField(null=True, blank=True)
    payment_id          = models.UUIDField(null=True, blank=True)

    cancelled_at        = models.DateTimeField(auto_now_add=True)
    hours_before_start  = models.FloatField()

    policy_id           = models.UUIDField(null=True, blank=True)
    fee_percent         = models.FloatField(default=0.0)
    original_amount_lkr = models.IntegerField()
    refund_amount_lkr   = models.IntegerField()
    fee_amount_lkr      = models.IntegerField(default=0)

    stripe_refund_id    = models.TextField(null=True, blank=True)
    initiated_by        = models.CharField(max_length=20, default='tourist')

    class Meta:
        db_table = 'cancellation_record'
        managed  = False
        ordering = ['-cancelled_at']

    def __str__(self):
        return f"Cancellation {self.id} | {self.fee_percent}% fee | {self.initiated_by}"