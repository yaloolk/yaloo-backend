# payment/views.py

import stripe
import logging
from decimal import Decimal
from datetime import datetime, timezone as dt_timezone
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from accounts.models import UserProfile, GuideProfile, HostProfile
from bookings.models import GuideBooking, StayBooking
from .models import Payment, CancellationPolicy, CancellationRecord

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

# ── LKR → cents (Stripe requires smallest currency unit) ──────────────────────
# Stripe does NOT support LKR natively. Use USD or the currency your
# Stripe account is configured for. Change LKR_TO_USD_RATE to match.
# For testing with test keys, USD is simplest.
LKR_TO_USD_RATE = 0.0031   # Update with live rate or use a FX API
PLATFORM_FEE_PERCENT = 5.0  # 5% platform fee


def _lkr_to_cents(lkr_amount: float) -> int:
    """Convert LKR amount to USD cents for Stripe."""
    usd = lkr_amount * LKR_TO_USD_RATE
    return max(int(round(usd * 100)), 50)  # Stripe minimum is 50 cents


def _get_user_profile(request):
    if hasattr(request.user, 'user_profile'):
        return request.user.user_profile
    return UserProfile.objects.get(auth_user_id=request.user.id)


# ─────────────────────────────────────────────────────────────────────────────
# CREATE PAYMENT INTENT
# POST /api/payment/create-intent/
#
# Called by Flutter BEFORE showing the Stripe payment sheet.
# Creates a PaymentIntent with capture_method='manual' so funds are
# held but not charged until guide/host confirms.
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_payment_intent(request):
    """
    Body:
        booking_type    – 'guide' | 'stay'
        booking_id      – UUID of the pre-created booking record
    Returns:
        client_secret   – passed to Flutter Stripe.instance.initPaymentSheet()
        payment_id      – our internal Payment row ID
        amount_lkr      – displayed to tourist in Flutter
        amount_usd_cents – actual amount charged (for transparency)
    """
    import traceback
    try:
        user_profile = _get_user_profile(request)

        if user_profile.user_role != 'tourist':
            return Response({'error': 'Only tourists can initiate payments'}, status=403)

        booking_type = request.data.get('booking_type')
        booking_id   = request.data.get('booking_id')

        if booking_type not in ('guide', 'stay'):
            return Response({'error': 'booking_type must be guide or stay'}, status=400)
        if not booking_id:
            return Response({'error': 'booking_id is required'}, status=400)

        # ── Fetch the booking ──────────────────────────────────────────────────────
        try:
            if booking_type == 'guide':
                booking = GuideBooking.objects.get(
                    id=booking_id, tourist_profile_id=user_profile.id
                )
                amount_lkr   = float(booking.total_amount)
                booking_label = f"Guide Tour – {booking.booking_date}"
            else:
                booking = StayBooking.objects.get(
                    id=booking_id, tourist_profile_id=user_profile.id
                )
                amount_lkr   = float(booking.total_amount)
                booking_label = f"Stay – {booking.checkin_date} to {booking.checkout_date}"
        except (GuideBooking.DoesNotExist, StayBooking.DoesNotExist):
            return Response({'error': 'Booking not found'}, status=404)

        if booking.booking_status != 'pending':
            return Response(
                {'error': f'Booking is already {booking.booking_status}. Cannot take payment.'},
                status=400
            )

        # ── Check no existing payment for this booking ─────────────────────────────
        existing_filter = (
            {'guide_booking_id': booking_id}
            if booking_type == 'guide' else
            {'stay_booking_id': booking_id}
        )
        existing = Payment.objects.filter(
            **existing_filter,
            payment_status__in=['awaiting_capture', 'captured']
        ).first()

        if existing:
            # Return the existing intent's client secret (idempotent)
            try:
                intent = stripe.PaymentIntent.retrieve(existing.stripe_payment_intent_id)
                return Response({
                    'client_secret':    intent.client_secret,
                    'payment_id':       str(existing.id),
                    'amount_lkr':       amount_lkr,
                    'amount_usd_cents': existing.total_paid,
                })
            except stripe.error.StripeError:
                pass  # Fall through to create a new one

        # ── Calculate fees ─────────────────────────────────────────────────────────
        platform_fee = round(amount_lkr * PLATFORM_FEE_PERCENT / 100, 2)
        total_lkr    = amount_lkr + platform_fee
        amount_cents = _lkr_to_cents(total_lkr)

        # ── Create Stripe PaymentIntent with manual capture ────────────────────────
        try:
            intent = stripe.PaymentIntent.create(
                amount         = amount_cents,
                currency       = 'usd',   # Change to your Stripe account currency
                capture_method = 'manual',
                metadata       = {
                    'booking_type': booking_type,
                    'booking_id':   str(booking_id),
                    'tourist_id':   str(user_profile.id),
                    'amount_lkr':   str(amount_lkr),
                },
                description    = f"Yaloo – {booking_label}",
            )
        except stripe.error.StripeError as e:
            logger.error(f"Stripe PaymentIntent creation failed: {e}")
            return Response({'error': str(e.user_message)}, status=502)

        # ── Save Payment record ────────────────────────────────────────────────────
        from django.utils import timezone as tz
        from datetime import timedelta

        try:
            with transaction.atomic():
                payment = Payment.objects.create(
                    booking_type             = booking_type,
                    guide_booking_id         = booking_id if booking_type == 'guide' else None,
                    stay_booking_id          = booking_id if booking_type == 'stay'  else None,
                    tourist_profile_id       = user_profile.id,   # ← this is user_profile.id, correct
                    stripe_payment_intent_id = intent.id,
                    base_amount              = amount_lkr,
                    platform_fee             = platform_fee,
                    total_paid               = amount_cents,
                    currency                 = 'USD',
                    payment_status           = 'awaiting_capture',
                    expires_at               = tz.now() + timedelta(days=6),
                )

                # Tag the booking with the intent ID for quick lookup on confirm
                if booking_type == 'guide':
                    GuideBooking.objects.filter(id=booking_id).update(
                        stripe_payment_intent_id=intent.id,
                        stripe_capture_status='awaiting_capture',
                    )
                else:
                    StayBooking.objects.filter(id=booking_id).update(
                        stripe_payment_intent_id=intent.id,
                        stripe_capture_status='awaiting_capture',
                    )

            logger.info(f"✅ PaymentIntent {intent.id} created for {booking_type} booking {booking_id}")

            return Response({
                'client_secret':    intent.client_secret,
                'payment_id':       str(payment.id),
                'amount_lkr':       amount_lkr,
                'platform_fee_lkr': platform_fee,
                'total_lkr':        total_lkr,
                'amount_usd_cents': amount_cents,
            }, status=201)

        except Exception as e:
            # Roll back the PaymentIntent if DB write fails
            try:
                stripe.PaymentIntent.cancel(intent.id)
            except Exception:
                pass
            logger.error(f"Payment record creation failed: {e}", exc_info=True)
            return Response({'error': 'Failed to initialise payment. Please try again.'}, status=500)
    except Exception as e:
        traceback.print_exc()   # prints full error to Django terminal
        return Response({'error': str(e)}, status=500)    

# ─────────────────────────────────────────────────────────────────────────────
# CANCELLATION PREVIEW
# GET /api/payment/cancellation-preview/?booking_type=guide&booking_id=<uuid>
#
# Flutter calls this BEFORE showing the cancel confirmation dialog.
# Returns the exact fee breakdown with no side effects.
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def cancellation_preview(request):
    user_profile = _get_user_profile(request)
    booking_type = request.query_params.get('booking_type')
    booking_id   = request.query_params.get('booking_id')

    if booking_type not in ('guide', 'stay'):
        return Response({'error': 'booking_type must be guide or stay'}, status=400)
    if not booking_id:
        return Response({'error': 'booking_id is required'}, status=400)

    try:
        if booking_type == 'guide':
            booking = GuideBooking.objects.get(
                id=booking_id, tourist_profile_id=user_profile.id
            )
            start_dt = datetime.combine(
                booking.booking_date,
                booking.start_time,
                tzinfo=dt_timezone.utc
            )
        else:
            booking = StayBooking.objects.get(
                id=booking_id, tourist_profile_id=user_profile.id
            )
            start_dt = datetime(
                booking.checkin_date.year,
                booking.checkin_date.month,
                booking.checkin_date.day,
                14, 0, 0,     # Default 2 PM check-in
                tzinfo=dt_timezone.utc
            )
    except (GuideBooking.DoesNotExist, StayBooking.DoesNotExist):
        return Response({'error': 'Booking not found'}, status=404)

    if booking.booking_status not in ('pending', 'confirmed'):
        return Response({'error': f'Cannot cancel a {booking.booking_status} booking'}, status=400)

    policy, fee_percent, tier = _get_cancellation_tier(start_dt)
    hours_before = (start_dt - datetime.now(dt_timezone.utc)).total_seconds() / 3600
    original_lkr = float(booking.total_amount)
    fee_lkr      = round(original_lkr * fee_percent / 100, 2)
    refund_lkr   = round(original_lkr - fee_lkr, 2)

    descriptions = {
        'free':    f'Cancel more than {policy.free_cancel_hours}h before — full refund.',
        'partial': f'Cancel between {policy.partial_fee_hours}–{policy.free_cancel_hours}h before — {policy.partial_fee_percent}% fee applies.',
        'none':    f'Cancel less than {policy.partial_fee_hours}h before — no refund.',
    }

    return Response({
        'booking_type':         booking_type,
        'booking_id':           str(booking_id),
        'hours_before_start':   round(hours_before, 1),
        'tier':                 tier,
        'fee_percent':          fee_percent,
        'original_amount_lkr':  original_lkr,
        'fee_amount_lkr':       fee_lkr,
        'refund_amount_lkr':    refund_lkr,
        'policy_description':   descriptions[tier],
        'free_cancel_hours':    policy.free_cancel_hours,
        'partial_fee_hours':    policy.partial_fee_hours,
    })


# ─────────────────────────────────────────────────────────────────────────────
# CANCEL BOOKING WITH REFUND
# POST /api/payment/cancel/
#
# Replaces the old cancel endpoints in bookings/views.py.
# Handles Stripe refund/release + DB updates atomically.
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_booking_with_refund(request):
    """
    Body:
        booking_type  – 'guide' | 'stay'
        booking_id    – UUID
    """
    user_profile = _get_user_profile(request)
    booking_type = request.data.get('booking_type')
    booking_id   = request.data.get('booking_id')

    if booking_type not in ('guide', 'stay'):
        return Response({'error': 'booking_type must be guide or stay'}, status=400)
    if not booking_id:
        return Response({'error': 'booking_id is required'}, status=400)

    # ── Load booking ───────────────────────────────────────────────────────────
    try:
        if booking_type == 'guide':
            booking = GuideBooking.objects.prefetch_related('locked_slots').get(
                id=booking_id, tourist_profile_id=user_profile.id
            )
            start_dt = datetime.combine(
                booking.booking_date,
                booking.start_time,
                tzinfo=dt_timezone.utc
            )
        else:
            booking = StayBooking.objects.get(
                id=booking_id, tourist_profile_id=user_profile.id
            )
            start_dt = datetime(
                booking.checkin_date.year,
                booking.checkin_date.month,
                booking.checkin_date.day,
                14, 0, 0,
                tzinfo=dt_timezone.utc
            )
    except (GuideBooking.DoesNotExist, StayBooking.DoesNotExist):
        return Response({'error': 'Booking not found'}, status=404)

    if booking.booking_status not in ('pending', 'confirmed'):
        return Response(
            {'error': f'Cannot cancel a {booking.booking_status} booking'},
            status=400
        )

    # ── Load payment record ────────────────────────────────────────────────────
    payment_filter = (
        {'guide_booking_id': booking_id}
        if booking_type == 'guide' else
        {'stay_booking_id': booking_id}
    )
    payment = Payment.objects.filter(**payment_filter).order_by('-created_at').first()

    # ── Determine fee ──────────────────────────────────────────────────────────
    policy, fee_percent, tier = _get_cancellation_tier(start_dt)
    hours_before    = (start_dt - datetime.now(dt_timezone.utc)).total_seconds() / 3600
    original_lkr    = float(booking.total_amount)
    original_cents  = int(payment.total_paid) if payment else _lkr_to_cents(original_lkr)
    fee_lkr         = round(original_lkr * fee_percent / 100, 2)
    refund_lkr      = round(original_lkr - fee_lkr, 2)
    fee_cents       = int(original_cents * fee_percent / 100)
    refund_cents    = original_cents - fee_cents

    stripe_refund_id = None

    # ── Stripe operation ───────────────────────────────────────────────────────
    if payment and payment.stripe_payment_intent_id:
        intent_id = payment.stripe_payment_intent_id
        try:
            intent = stripe.PaymentIntent.retrieve(intent_id)

            if intent.status == 'requires_capture':
                # Payment held but not yet captured — cancel the hold entirely,
                # no charge regardless of policy tier (tourist never confirmed booking)
                if booking.booking_status == 'pending':
                    stripe.PaymentIntent.cancel(intent_id)
                    refund_cents  = original_cents
                    refund_lkr    = original_lkr
                    fee_percent   = 0
                    fee_lkr       = 0
                    fee_cents     = 0
                else:
                    # Confirmed booking with uncaptured intent — apply fee policy
                    # Capture only the fee amount, refund the rest
                    if fee_cents > 0:
                        stripe.PaymentIntent.capture(
                            intent_id,
                            amount_to_capture=fee_cents
                        )
                    else:
                        stripe.PaymentIntent.cancel(intent_id)

            elif intent.status == 'succeeded':
                # Already captured — issue refund
                if refund_cents > 0:
                    refund = stripe.Refund.create(
                        payment_intent=intent_id,
                        amount=refund_cents,
                    )
                    stripe_refund_id = refund.id

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error during cancel: {e}")
            return Response({'error': f'Payment processing error: {e.user_message}'}, status=502)

    # ── DB updates ─────────────────────────────────────────────────────────────
    try:
        with transaction.atomic():
            # Update booking status
            booking.booking_status = 'cancelled'
            booking.save(update_fields=['booking_status', 'updated_at'])

            # Unlock guide slots if guide booking
            if booking_type == 'guide' and hasattr(booking, 'locked_slots'):
                from accounts.models import GuideAvailability
                slot_ids = booking.locked_slots.values_list('guide_availability_id', flat=True)
                GuideAvailability.objects.filter(id__in=slot_ids).update(is_booked=False)

            # Update payment record
            if payment:
                new_status = 'refunded' if fee_percent == 0 else (
                    'partially_refunded' if refund_cents > 0 else 'cancelled'
                )
                payment.payment_status          = new_status
                payment.cancellation_fee_percent = fee_percent
                payment.refund_amount           = refund_cents
                payment.refunded_at             = timezone.now() if refund_cents > 0 else None
                payment.stripe_refund_id        = stripe_refund_id
                payment.save()

            # Write cancellation record
            CancellationRecord.objects.create(
                booking_type        = booking_type,
                guide_booking_id    = booking_id if booking_type == 'guide' else None,
                stay_booking_id     = booking_id if booking_type == 'stay'  else None,
                payment_id          = payment.id if payment else None,
                hours_before_start  = max(hours_before, 0),
                policy_id           = policy.id,
                fee_percent         = fee_percent,
                original_amount_lkr = int(original_lkr),
                refund_amount_lkr   = int(refund_lkr),
                fee_amount_lkr      = int(fee_lkr),
                stripe_refund_id    = stripe_refund_id,
                initiated_by        = 'tourist',
            )

        logger.info(
            f"✅ {booking_type} booking {booking_id} cancelled | "
            f"fee={fee_percent}% | refund=LKR{refund_lkr}"
        )

        return Response({
            'message':             'Booking cancelled successfully',
            'booking_status':      'cancelled',
            'tier':                tier,
            'fee_percent':         fee_percent,
            'refund_amount_lkr':   refund_lkr,
            'fee_amount_lkr':      fee_lkr,
            'refund_note':         (
                'Full refund — no charge' if fee_percent == 0 else
                f'{fee_percent}% cancellation fee applied' if refund_lkr > 0 else
                'No refund — late cancellation'
            ),
        })

    except Exception as e:
        logger.error(f"cancel_booking_with_refund DB error: {e}", exc_info=True)
        return Response({'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# STRIPE WEBHOOK
# POST /api/payment/webhook/
#
# Add this URL to your Stripe Dashboard → Webhooks.
# Events to listen for:
#   payment_intent.succeeded
#   payment_intent.payment_failed
#   payment_intent.canceled
#   charge.refunded
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
def stripe_webhook(request):
    # Ensure it's a POST request
    if request.method != 'POST':
        return HttpResponse(status=405)

    payload    = request.body  # This will now be the raw, unparsed bytes
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError as e:
        logger.warning(f"Webhook payload invalid: {e}")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        logger.warning(f"Webhook signature failed: {e}")
        return HttpResponse(status=400)

    event_type = event['type']
    intent     = event['data']['object']
    intent_id  = intent.id

    logger.info(f"Stripe webhook: {event_type} for intent {intent_id}")

    payment = Payment.objects.filter(
        stripe_payment_intent_id=intent_id
    ).first()

    if not payment:
        return HttpResponse(status=200) # Use standard HttpResponse (200 OK)

    try:
        if event_type == 'payment_intent.succeeded':
            payment.payment_status      = 'captured'
            payment.payment_captured_at = timezone.now()
            if getattr(intent, 'latest_charge', None):
                payment.stripe_charge_id = intent.latest_charge
            payment.save()
            _update_booking_payment_status(payment, 'paid')

        elif event_type == 'payment_intent.canceled':
            payment.payment_status = 'cancelled'
            payment.save()
            _update_booking_payment_status(payment, 'unpaid')

        elif event_type == 'payment_intent.payment_failed':
            logger.warning(f"Payment failed for intent {intent_id}")
            _update_booking_payment_status(payment, 'unpaid')

        elif event_type == 'charge.refunded':
            charge = event['data']['object']
            refunded = getattr(charge, 'amount_refunded', 0)
            total    = getattr(charge, 'amount', 1)
            if refunded >= total:
                payment.payment_status = 'refunded'
            else:
                payment.payment_status = 'partially_refunded'
            payment.refunded_at = timezone.now()
            payment.save()
            _update_booking_payment_status(payment, 'refunded')

    except Exception as e:
        logger.error(f"Webhook handler error: {e}", exc_info=True)
        return HttpResponse(status=500)

    # Return standard 200 HTTP response so Stripe knows it was received
    return HttpResponse(status=200)


# ─────────────────────────────────────────────────────────────────────────────
# GET CANCELLATION POLICY  (for admin dashboard)
# GET /api/payment/policy/
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_cancellation_policy(request):
    """Returns the currently active cancellation policy."""
    try:
        policy = CancellationPolicy.objects.filter(is_active=True).latest('updated_at')
        return Response({
            'id':                   str(policy.id),
            'name':                 policy.name,
            'is_active':            policy.is_active,
            'free_cancel_hours':    policy.free_cancel_hours,
            'partial_fee_hours':    policy.partial_fee_hours,
            'partial_fee_percent':  policy.partial_fee_percent,
            'updated_at':           policy.updated_at.isoformat(),
        })
    except CancellationPolicy.DoesNotExist:
        return Response({'error': 'No active policy found'}, status=404)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_cancellation_policy(request):
    """
    Admin-only: update the active cancellation policy.
    Body: { free_cancel_hours, partial_fee_hours, partial_fee_percent, name? }
    """
    user_profile = _get_user_profile(request)
    if user_profile.user_role != 'admin':
        return Response({'error': 'Admin only'}, status=403)

    try:
        policy = CancellationPolicy.objects.filter(is_active=True).latest('updated_at')
    except CancellationPolicy.DoesNotExist:
        policy = CancellationPolicy()
        policy.is_active = True

    if 'free_cancel_hours' in request.data:
        policy.free_cancel_hours = int(request.data['free_cancel_hours'])
    if 'partial_fee_hours' in request.data:
        policy.partial_fee_hours = int(request.data['partial_fee_hours'])
    if 'partial_fee_percent' in request.data:
        policy.partial_fee_percent = float(request.data['partial_fee_percent'])
    if 'name' in request.data:
        policy.name = request.data['name']

    # Validate
    if policy.partial_fee_hours >= policy.free_cancel_hours:
        return Response(
            {'error': 'partial_fee_hours must be less than free_cancel_hours'},
            status=400
        )
    if not (0 <= policy.partial_fee_percent <= 100):
        return Response({'error': 'partial_fee_percent must be between 0 and 100'}, status=400)

    policy.save()
    return Response({'message': 'Policy updated', 'updated_at': policy.updated_at.isoformat()})


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_cancellation_tier(start_dt: datetime):
    """
    Returns (policy, fee_percent, tier_name).
    tier_name: 'free' | 'partial' | 'none'
    """
    try:
        policy = CancellationPolicy.objects.filter(is_active=True).latest('updated_at')
    except CancellationPolicy.DoesNotExist:
        # Fallback defaults if no policy exists
        class DefaultPolicy:
            id = None
            free_cancel_hours    = 24
            partial_fee_hours    = 12
            partial_fee_percent  = 10.0
        policy = DefaultPolicy()

    now          = datetime.now(dt_timezone.utc)
    hours_before = (start_dt - now).total_seconds() / 3600

    if hours_before >= policy.free_cancel_hours:
        return policy, 0.0, 'free'
    elif hours_before >= policy.partial_fee_hours:
        return policy, float(policy.partial_fee_percent), 'partial'
    else:
        return policy, 100.0, 'none'


def _update_booking_payment_status(payment: Payment, new_status: str):
    """Helper to sync payment_status on the booking table."""
    try:
        if payment.booking_type == 'guide' and payment.guide_booking_id:
            GuideBooking.objects.filter(id=payment.guide_booking_id).update(
                payment_status=new_status
            )
        elif payment.booking_type == 'stay' and payment.stay_booking_id:
            StayBooking.objects.filter(id=payment.stay_booking_id).update(
                payment_status=new_status
            )
    except Exception as e:
        logger.error(f"Failed to update booking payment_status: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CAPTURE PAYMENT  (called internally from bookings/views.py on confirm)
# Not an HTTP endpoint — imported and called by guide_respond_booking()
# and host_respond_stay_booking()
# ─────────────────────────────────────────────────────────────────────────────

def capture_payment_for_booking(booking_type: str, booking_id: str) -> bool:
    """
    Captures the Stripe PaymentIntent for a confirmed booking.
    Called from bookings/views.py when guide/host accepts.
    Returns True on success.
    """
    payment_filter = (
        {'guide_booking_id': booking_id}
        if booking_type == 'guide' else
        {'stay_booking_id': booking_id}
    )
    payment = Payment.objects.filter(
        **payment_filter,
        payment_status='awaiting_capture'
    ).first()

    if not payment:
        logger.warning(f"No awaiting_capture payment found for {booking_type} booking {booking_id}")
        return False

    try:
        intent = stripe.PaymentIntent.capture(payment.stripe_payment_intent_id)

        payment.payment_status      = 'captured'
        payment.payment_captured_at = timezone.now()
        if intent.latest_charge:
            payment.stripe_charge_id = intent.latest_charge
        payment.save()

        # Update booking capture status
        if booking_type == 'guide':
            GuideBooking.objects.filter(id=booking_id).update(
                stripe_capture_status='captured',
                payment_status='paid',
            )
        else:
            StayBooking.objects.filter(id=booking_id).update(
                stripe_capture_status='captured',
                payment_status='paid',
            )

        logger.info(f"✅ Payment captured for {booking_type} booking {booking_id}")
        return True

    except stripe.error.StripeError as e:
        logger.error(f"Stripe capture failed for {booking_id}: {e}")
        return False


def release_payment_for_booking(booking_type: str, booking_id: str) -> bool:
    """
    Cancels the Stripe PaymentIntent hold when guide/host rejects.
    Called from bookings/views.py when guide/host declines.
    Returns True on success.
    """
    payment_filter = (
        {'guide_booking_id': booking_id}
        if booking_type == 'guide' else
        {'stay_booking_id': booking_id}
    )
    payment = Payment.objects.filter(
        **payment_filter,
        payment_status='awaiting_capture'
    ).first()

    if not payment:
        return True  # No payment to release — that's fine

    try:
        stripe.PaymentIntent.cancel(payment.stripe_payment_intent_id)

        payment.payment_status = 'cancelled'
        payment.save()

        if booking_type == 'guide':
            GuideBooking.objects.filter(id=booking_id).update(
                stripe_capture_status='cancelled',
                payment_status='unpaid',
            )
        else:
            StayBooking.objects.filter(id=booking_id).update(
                stripe_capture_status='cancelled',
                payment_status='unpaid',
            )

        logger.info(f"✅ Payment hold released for {booking_type} booking {booking_id}")
        return True

    except stripe.error.StripeError as e:
        logger.error(f"Stripe cancel failed for {booking_id}: {e}")
        return False