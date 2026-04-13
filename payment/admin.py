# payment/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import Payment, CancellationPolicy, CancellationRecord


# ══════════════════════════════════════════════════════════
# CANCELLATION POLICY
# ══════════════════════════════════════════════════════════

@admin.register(CancellationPolicy)
class CancellationPolicyAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'is_active', 'free_cancel_hours',
        'partial_fee_hours', 'partial_fee_percent',
        'updated_at'
    ]
    list_filter = ['is_active']
    search_fields = ['name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    list_editable = ['is_active']

    fieldsets = (
        ('Policy Details', {
            'fields': ('id', 'name', 'is_active')
        }),
        ('Fee Tiers', {
            'description': (
                'Cancellation fee logic: '
                'free if >free_cancel_hours before start, '
                'partial fee if between partial_fee_hours and free_cancel_hours, '
                '100% fee if <partial_fee_hours before start.'
            ),
            'fields': ('free_cancel_hours', 'partial_fee_hours', 'partial_fee_percent')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        # Enforce only one active policy at a time
        if obj.is_active:
            CancellationPolicy.objects.exclude(pk=obj.pk).update(is_active=False)
        super().save_model(request, obj, form, change)


# ══════════════════════════════════════════════════════════
# PAYMENTS
# ══════════════════════════════════════════════════════════

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'short_id', 'booking_type', 'get_booking_id',
        'tourist_profile_id', 'payment_status_badge',
        'base_amount_display', 'platform_fee_display',
        'total_paid_display', 'currency',
        'refund_amount_display', 'created_at'
    ]
    list_filter = ['payment_status', 'booking_type', 'currency']
    search_fields = [
        'stripe_payment_intent_id',
        'stripe_charge_id',
        'stripe_refund_id',
        'tourist_profile_id',
    ]
    readonly_fields = [
        'id', 'stripe_payment_intent_id', 'stripe_charge_id',
        'stripe_refund_id', 'tourist_profile_id',
        'guide_booking_id', 'stay_booking_id',
        'payment_captured_at', 'refunded_at',
        'created_at', 'updated_at',
        'stripe_links',
    ]
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    actions = ['mark_captured', 'mark_refunded']

    fieldsets = (
        ('Booking Reference', {
            'fields': (
                'id', 'booking_type',
                'guide_booking_id', 'stay_booking_id',
                'tourist_profile_id',
            )
        }),
        ('Stripe', {
            'fields': (
                'stripe_payment_intent_id',
                'stripe_charge_id',
                'stripe_refund_id',
                'stripe_links',
            )
        }),
        ('Amounts', {
            'fields': (
                'base_amount', 'platform_fee', 'total_paid', 'currency',
            )
        }),
        ('Status & Timing', {
            'fields': (
                'payment_status',
                'payment_captured_at',
                'expires_at',
            )
        }),
        ('Refund', {
            'fields': (
                'cancellation_fee_percent',
                'refund_amount',
                'refunded_at',
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    # ── Display helpers ──────────────────────────────────

    def short_id(self, obj):
        return str(obj.id)[:8] + '…'
    short_id.short_description = 'ID'

    def get_booking_id(self, obj):
        bid = obj.guide_booking_id or obj.stay_booking_id
        return str(bid)[:8] + '…' if bid else '—'
    get_booking_id.short_description = 'Booking'

    def payment_status_badge(self, obj):
        colours = {
            'awaiting_capture':   '#f59e0b',
            'captured':           '#10b981',
            'cancelled':          '#6b7280',
            'refunded':           '#3b82f6',
            'partially_refunded': '#8b5cf6',
        }
        colour = colours.get(obj.payment_status, '#6b7280')
        label = obj.get_payment_status_display()
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;">{}</span>',
            colour, label
        )
    payment_status_badge.short_description = 'Status'

    def base_amount_display(self, obj):
        return f"LKR {obj.base_amount:,.2f}"
    base_amount_display.short_description = 'Base (LKR)'

    def platform_fee_display(self, obj):
        return f"LKR {obj.platform_fee:,.2f}"
    platform_fee_display.short_description = 'Fee (LKR)'

    def total_paid_display(self, obj):
        return f"{obj.currency} {obj.total_paid:,.0f}¢"
    total_paid_display.short_description = 'Total Charged'

    def refund_amount_display(self, obj):
        if obj.refund_amount:
            return f"{obj.currency} {obj.refund_amount:,.0f}¢"
        return '—'
    refund_amount_display.short_description = 'Refunded'

    def stripe_links(self, obj):
        links = []
        if obj.stripe_payment_intent_id:
            links.append(format_html(
                '<a href="https://dashboard.stripe.com/payments/{}" target="_blank">View Payment Intent ↗</a>',
                obj.stripe_payment_intent_id
            ))
        if obj.stripe_charge_id:
            links.append(format_html(
                '<a href="https://dashboard.stripe.com/charges/{}" target="_blank">View Charge ↗</a>',
                obj.stripe_charge_id
            ))
        if obj.stripe_refund_id:
            links.append(format_html(
                '<a href="https://dashboard.stripe.com/refunds/{}" target="_blank">View Refund ↗</a>',
                obj.stripe_refund_id
            ))
        return format_html(' &nbsp;|&nbsp; '.join(links)) if links else '—'
    stripe_links.short_description = 'Stripe Dashboard'

    # ── Actions ─────────────────────────────────────────

    @admin.action(description='✅ Mark selected payments as Captured')
    def mark_captured(self, request, queryset):
        from django.utils import timezone
        queryset.update(payment_status='captured', payment_captured_at=timezone.now())
        self.message_user(request, f"{queryset.count()} payment(s) marked as captured.")

    @admin.action(description='🔁 Mark selected payments as Refunded')
    def mark_refunded(self, request, queryset):
        from django.utils import timezone
        queryset.update(payment_status='refunded', refunded_at=timezone.now())
        self.message_user(request, f"{queryset.count()} payment(s) marked as refunded.")


# ══════════════════════════════════════════════════════════
# CANCELLATION RECORDS
# ══════════════════════════════════════════════════════════

@admin.register(CancellationRecord)
class CancellationRecordAdmin(admin.ModelAdmin):
    list_display = [
        'short_id', 'booking_type', 'get_booking_ref',
        'initiated_by', 'hours_before_start_display',
        'fee_percent_badge', 'original_amount_display',
        'refund_amount_display', 'fee_amount_display',
        'cancelled_at'
    ]
    list_filter = ['booking_type', 'initiated_by', 'fee_percent']
    search_fields = ['guide_booking_id', 'stay_booking_id', 'stripe_refund_id']
    readonly_fields = [
        'id', 'booking_type',
        'guide_booking_id', 'stay_booking_id',
        'payment_id', 'stripe_refund_id',
        'cancelled_at', 'policy_id',
        'hours_before_start', 'fee_percent',
        'original_amount_lkr', 'refund_amount_lkr', 'fee_amount_lkr',
        'initiated_by',
    ]
    date_hierarchy = 'cancelled_at'
    ordering = ['-cancelled_at']

    fieldsets = (
        ('Booking Reference', {
            'fields': ('id', 'booking_type', 'guide_booking_id', 'stay_booking_id', 'payment_id')
        }),
        ('Cancellation Details', {
            'fields': (
                'cancelled_at', 'hours_before_start',
                'initiated_by', 'policy_id',
            )
        }),
        ('Fee Breakdown (LKR)', {
            'fields': (
                'fee_percent',
                'original_amount_lkr',
                'fee_amount_lkr',
                'refund_amount_lkr',
            )
        }),
        ('Stripe', {
            'fields': ('stripe_refund_id',)
        }),
    )

    def short_id(self, obj):
        return str(obj.id)[:8] + '…'
    short_id.short_description = 'ID'

    def get_booking_ref(self, obj):
        bid = obj.guide_booking_id or obj.stay_booking_id
        return str(bid)[:8] + '…' if bid else '—'
    get_booking_ref.short_description = 'Booking'

    def hours_before_start_display(self, obj):
        h = obj.hours_before_start
        if h >= 24:
            return f"{h:.0f}h (>{24}h)"
        return f"{h:.1f}h"
    hours_before_start_display.short_description = 'Hours Before'

    def fee_percent_badge(self, obj):
        pct = obj.fee_percent
        if pct == 0:
            colour, label = '#10b981', 'Free (0%)'
        elif pct == 100:
            colour, label = '#ef4444', 'No Refund (100%)'
        else:
            colour, label = '#f59e0b', f'Partial ({pct:.0f}%)'
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;">{}</span>',
            colour, label
        )
    fee_percent_badge.short_description = 'Fee Tier'

    def original_amount_display(self, obj):
        return f"LKR {obj.original_amount_lkr:,}"
    original_amount_display.short_description = 'Original'

    def refund_amount_display(self, obj):
        return f"LKR {obj.refund_amount_lkr:,}"
    refund_amount_display.short_description = 'Refunded'

    def fee_amount_display(self, obj):
        return f"LKR {obj.fee_amount_lkr:,}"
    fee_amount_display.short_description = 'Fee Charged'