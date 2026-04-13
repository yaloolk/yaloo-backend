# bookings/views.py

import logging
from datetime import datetime, timedelta, date as date_type
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Avg
from rest_framework.permissions import AllowAny

from payment.views import capture_payment_for_booking, release_payment_for_booking

from accounts.models import (
    UserProfile, GuideProfile, GuideAvailability, TouristProfile, HostProfile, Stay, Media, City, Review
)
from .models import GuideBooking, BookedGuide, StayBooking

from .serializers import (
    GuideBookingSerializer,
    GuideBookingListSerializer,
    CreateGuideBookingSerializer,
    RespondBookingSerializer,
    CreateStayBookingSerializer,
    RespondStayBookingSerializer,
    StayBookingSerializer,
    StayBookingListSerializer,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_user_profile(request):
    if hasattr(request.user, 'user_profile'):
        return request.user.user_profile
    return UserProfile.objects.get(auth_user_id=request.user.id)


def _enrich_request_for_serializer(request, bookings):
    """
    Attach tourist & guide lookup maps to the request object so serializer
    get_* methods can resolve names/photos without N+1 queries.
    """
    tourist_ids = list({str(b.tourist_profile_id) for b in bookings})
    guide_ids   = list({str(b.guide_profile_id)   for b in bookings})

    tourist_profiles = UserProfile.objects.filter(id__in=tourist_ids)
    guide_profiles   = GuideProfile.objects.select_related('user_profile').filter(
        id__in=guide_ids
    )

    request._tourist_map      = {str(p.id): p  for p in tourist_profiles}
    request._guide_profile_map = {str(g.id): g for g in guide_profiles}


def _calculate_hours(start_time, end_time):
    """Return float hours between two time objects."""
    start_dt = datetime.combine(date_type.today(), start_time)
    end_dt   = datetime.combine(date_type.today(), end_time)
    delta    = end_dt - start_dt
    return max(round(delta.total_seconds() / 3600, 2), 0.5)


# ─────────────────────────────────────────────────────────────────────────────
# TOURIST — CREATE BOOKING
# POST /api/booking/guide/create/
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_guide_booking(request):
    """
    Tourist submits a booking request for a guide.

    Flow:
    1. Validate input
    2. Check guide exists and is verified
    3. Find available (is_booked=False) slots that cover the requested window
    4. Lock those slots (is_booked=True) immediately to prevent double-booking
    5. Create GuideBooking + GuideBookingSlot records
    6. Return booking detail
    """
    user_profile = _get_user_profile(request)

    if user_profile.user_role != 'tourist':
        return Response({'error': 'Only tourists can create guide bookings'}, status=403)

    serializer = CreateGuideBookingSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    data = serializer.validated_data

    try:
        guide = GuideProfile.objects.select_related('user_profile').get(
            id=data['guide_profile_id']
        )
    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide not found'}, status=404)

    if guide.verification_status != 'verified':
        return Response({'error': 'Guide is not verified'}, status=400)

    if not guide.is_available:
        return Response({'error': 'Guide is currently not available'}, status=400)

    # Find slots that fall within [start_time, end_time) on booking_date
    slots = GuideAvailability.objects.filter(
        guide_profile=guide,
        date=data['booking_date'],
        start_time__gte=data['start_time'],
        end_time__lte=data['end_time'],
        is_booked=False,
    ).order_by('start_time')

    if not slots.exists():
        return Response(
            {'error': 'No available slots found for the requested time range'},
            status=400
        )

    # Verify slots are contiguous (no gaps)
    slot_list = list(slots)
    for i in range(len(slot_list) - 1):
        if slot_list[i].end_time != slot_list[i + 1].start_time:
            return Response(
                {'error': 'Selected time range has gaps — please choose a continuous window'},
                status=400
            )

    total_hours  = _calculate_hours(data['start_time'], data['end_time'])
    total_amount = round(total_hours * guide.rate_per_hour, 2)

    try:
        with transaction.atomic():
            # Lock the slots
            slots.update(is_booked=True)

            # Create the booking
            booking = GuideBooking.objects.create(
                tourist_profile_id=user_profile.id,
                guide_profile_id=guide.id,
                booking_date=data['booking_date'],
                start_time=data['start_time'],
                end_time=data['end_time'],
                total_hours=total_hours,
                rate_per_hour=guide.rate_per_hour,
                total_amount=total_amount,
                guest_count=data.get('guest_count', 1),
                pickup_latitude=data.get('pickup_latitude'),
                pickup_longitude=data.get('pickup_longitude'),
                pickup_address=data.get('pickup_address'),
                special_note=data.get('special_note'),
                booking_status='pending',
            )

            # Record which slots were locked
            for slot in slot_list:
                BookedGuide.objects.create(
                    booking=booking,
                    guide_availability_id=slot.id,
                        price_per_slot_at_bookingtime=guide.rate_per_hour,
                )

        logger.info(f"✅ GuideBooking {booking.id} created by tourist {user_profile.id}")

        _enrich_request_for_serializer(request, [booking])
        out = GuideBookingSerializer(booking, context={'request': request})
        return Response(out.data, status=201)

    except Exception as e:
        logger.error(f"❌ create_guide_booking error: {e}", exc_info=True)
        return Response({'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# TOURIST — MY BOOKINGS
# GET /api/booking/guide/my/
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tourist_my_bookings(request):
    """
    Returns all bookings for the logged-in tourist.
    Optional query param: ?status=pending|confirmed|completed|cancelled|rejected
    """
    user_profile = _get_user_profile(request)

    if user_profile.user_role != 'tourist':
        return Response({'error': 'Only tourists can access this endpoint'}, status=403)

    qs = GuideBooking.objects.filter(
        tourist_profile_id=user_profile.id
    ).order_by('-created_at')

    booking_status = request.query_params.get('status')
    if booking_status:
        qs = qs.filter(booking_status=booking_status)

    bookings = list(qs)
    _enrich_request_for_serializer(request, bookings)

    # Build list with enriched data manually (lightweight)
    result = []
    for b in bookings:
        gp = request._guide_profile_map.get(str(b.guide_profile_id))
        city_name = ''
        if gp:
            try:
                from accounts.models import City
                city = City.objects.get(id=gp.city_id)
                city_name = city.name
            except Exception:
                pass

        result.append({
            'id':               str(b.id),
            'guide_profile_id': str(b.guide_profile_id),
            'guide_name':       f"{gp.user_profile.first_name or ''} {gp.user_profile.last_name or ''}".strip() if gp else '',
            'guide_photo':      gp.user_profile.profile_pic if gp else '',
            'guide_phone':      gp.user_profile.phone_number if gp else '',
            'city_name':        city_name,
            'booking_date':     str(b.booking_date),
            'start_time':       str(b.start_time),
            'end_time':         str(b.end_time),
            'total_hours':      b.total_hours,
            'total_amount':     b.total_amount,
            'rate_per_hour':    b.rate_per_hour,
            'guest_count':      b.guest_count,
            'pickup_latitude':  b.pickup_latitude,
            'pickup_longitude': b.pickup_longitude,
            'pickup_address':   b.pickup_address,
            'guide_response_note': b.guide_response_note,
            'booking_status':   b.booking_status,
            'payment_status':   b.payment_status,
            'special_note':     b.special_note,
            'created_at':       b.created_at.isoformat(),
        })

    return Response(result)


# ─────────────────────────────────────────────────────────────────────────────
# TOURIST — BOOKING DETAIL
# GET /api/booking/guide/<booking_id>/
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def booking_detail(request, booking_id):
    user_profile = _get_user_profile(request)

    try:
        booking = GuideBooking.objects.prefetch_related('locked_slots').get(id=booking_id)
    except GuideBooking.DoesNotExist:
        return Response({'error': 'Booking not found'}, status=404)

    # Allow tourist who owns it OR guide who was booked
    is_tourist = str(booking.tourist_profile_id) == str(user_profile.id)
    is_guide   = False
    if user_profile.user_role == 'guide':
        try:
            gp = GuideProfile.objects.get(user_profile=user_profile)
            is_guide = str(booking.guide_profile_id) == str(gp.id)
        except GuideProfile.DoesNotExist:
            pass

    if not (is_tourist or is_guide):
        return Response({'error': 'Not authorized'}, status=403)

    _enrich_request_for_serializer(request, [booking])
    out = GuideBookingSerializer(booking, context={'request': request})
    return Response(out.data)


# ─────────────────────────────────────────────────────────────────────────────
# TOURIST — CANCEL BOOKING
# POST /api/booking/guide/<booking_id>/cancel/
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tourist_cancel_booking(request, booking_id):
    """Delegates to payment app cancel — handles refund logic automatically."""
    # Inject booking_type and booking_id into request data
    request.data._mutable = True if hasattr(request.data, '_mutable') else None
    data = {'booking_type': 'guide', 'booking_id': str(booking_id)}
 
    # Use the payment view directly
    from payment.views import cancel_booking_with_refund
    # Temporarily override request.data
    original_data  = request.data
    request._data  = type('FakeData', (), {'get': lambda self, k, d=None: data.get(k, d)})()
    result         = cancel_booking_with_refund(request)
    request._data  = original_data
    return result

# ─────────────────────────────────────────────────────────────────────────────
# GUIDE — PENDING REQUESTS
# GET /api/booking/guide/requests/
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def guide_booking_requests(request):
    """
    Returns all PENDING bookings for the logged-in guide.
    """
    user_profile = _get_user_profile(request)

    if user_profile.user_role != 'guide':
        return Response({'error': 'Only guides can access this endpoint'}, status=403)

    try:
        guide = GuideProfile.objects.get(user_profile=user_profile)
    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide profile not found'}, status=404)

    bookings = list(
        GuideBooking.objects.filter(
            guide_profile_id=guide.id,
            booking_status='pending'
        ).order_by('-created_at')
    )

    _enrich_request_for_serializer(request, bookings)

    result = []
    for b in bookings:
        tourist = request._tourist_map.get(str(b.tourist_profile_id))
        result.append({
            'id':                str(b.id),
            'tourist_profile_id': str(b.tourist_profile_id),
            'tourist_name':      f"{tourist.first_name or ''} {tourist.last_name or ''}".strip() if tourist else '',
            'tourist_photo':     tourist.profile_pic if tourist else '',
            'tourist_phone':     tourist.phone_number if tourist else '',
            'booking_date':      str(b.booking_date),
            'start_time':        str(b.start_time),
            'end_time':          str(b.end_time),
            'total_hours':       b.total_hours,
            'total_amount':      b.total_amount,
            'guest_count':       b.guest_count,
            'special_note':      b.special_note,
            'booking_status':    b.booking_status,
            'created_at':        b.created_at.isoformat(),
        })

    return Response(result)


# ─────────────────────────────────────────────────────────────────────────────
# GUIDE — RESPOND (ACCEPT / REJECT)
# POST /api/booking/guide/<booking_id>/respond/
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def guide_respond_booking(request, booking_id):
    """
    Guide accepts or rejects a pending booking.
    On ACCEPT  → captures the Stripe PaymentIntent (charges tourist).
    On REJECT  → cancels the hold (tourist not charged, money released).
    """
    from payment.views import capture_payment_for_booking, release_payment_for_booking
 
    user_profile = _get_user_profile(request)
    if user_profile.user_role != 'guide':
        return Response({'error': 'Only guides can respond to bookings'}, status=403)
 
    try:
        guide = GuideProfile.objects.get(user_profile=user_profile)
    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide profile not found'}, status=404)
 
    serializer = RespondBookingSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
 
    data = serializer.validated_data
 
    try:
        booking = GuideBooking.objects.prefetch_related('locked_slots').get(
            id=booking_id, guide_profile_id=guide.id
        )
    except GuideBooking.DoesNotExist:
        return Response({'error': 'Booking not found'}, status=404)
 
    if booking.booking_status != 'pending':
        return Response({'error': f'Booking is already {booking.booking_status}'}, status=400)
 
    with transaction.atomic():
        if data['action'] == 'accept':
            booking.booking_status = 'confirmed'
        else:
            booking.booking_status = 'rejected'
            # Unlock availability slots
            slot_ids = booking.locked_slots.values_list('guide_availability_id', flat=True)
            GuideAvailability.objects.filter(id__in=slot_ids).update(is_booked=False)
 
        booking.guide_response_note = data.get('guide_response_note', '')
        booking.responded_at        = timezone.now()
        booking.save(update_fields=[
            'booking_status', 'guide_response_note', 'responded_at', 'updated_at'
        ])
 
        # Update guide stats
        if data['action'] == 'reject':
            GuideProfile.objects.filter(id=guide.id).update(
                total_rejected_bookings=guide.total_rejected_bookings + 1
            )
 
    # ── Stripe: capture or release AFTER DB commit ─────────────────────────────
    if data['action'] == 'accept':
        stripe_ok = capture_payment_for_booking('guide', str(booking_id))
        if not stripe_ok:
            # Payment capture failed — don't block the confirmation,
            # webhook will retry, but log for investigation
            logger.error(f"⚠️  Stripe capture failed for guide booking {booking_id} — needs manual check")
    else:
        release_payment_for_booking('guide', str(booking_id))
 
    logger.info(f"✅ Guide {guide.id} {data['action']}ed booking {booking_id}")
 
    return Response({
        'message':        f'Booking {data["action"]}ed successfully',
        'booking_status': booking.booking_status,
        'payment_note':   (
            'Payment captured — tourist has been charged.' if data['action'] == 'accept'
            else 'Payment hold released — tourist will not be charged.'
        ),
    })


def _recalc_response_rate(guide_id):
    """Recalculate response rate = confirmed / (confirmed + rejected)"""
    total_responded = GuideBooking.objects.filter(
        guide_profile_id=guide_id,
        booking_status__in=['confirmed', 'rejected']
    ).count()
    confirmed = GuideBooking.objects.filter(
        guide_profile_id=guide_id,
        booking_status='confirmed'
    ).count()
    return round((confirmed / total_responded * 100), 1) if total_responded > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# GUIDE — BOOKING HISTORY
# GET /api/booking/guide/history/
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def guide_booking_history(request):
    """
    Returns all non-pending bookings for the logged-in guide.
    Optional ?status= filter.
    """
    user_profile = _get_user_profile(request)

    if user_profile.user_role != 'guide':
        return Response({'error': 'Only guides can access this endpoint'}, status=403)

    try:
        guide = GuideProfile.objects.get(user_profile=user_profile)
    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide profile not found'}, status=404)

    qs = GuideBooking.objects.filter(
        guide_profile_id=guide.id
    ).exclude(booking_status='pending').order_by('-created_at')

    booking_status = request.query_params.get('status')
    if booking_status:
        qs = qs.filter(booking_status=booking_status)

    bookings = list(qs)
    _enrich_request_for_serializer(request, bookings)

    result = []
    for b in bookings:
        tourist = request._tourist_map.get(str(b.tourist_profile_id))
        result.append({
            'id':                str(b.id),
            'tourist_profile_id': str(b.tourist_profile_id),
            'tourist_name':      f"{tourist.first_name or ''} {tourist.last_name or ''}".strip() if tourist else '',
            'tourist_photo':     tourist.profile_pic if tourist else '',
            'booking_date':      str(b.booking_date),
            'start_time':        str(b.start_time),
            'end_time':          str(b.end_time),
            'total_hours':       b.total_hours,
            'total_amount':      b.total_amount,
            'booking_status':    b.booking_status,
            'payment_status':    b.payment_status,
            'tip_amount':        b.tip_amount,
            'guide_response_note': b.guide_response_note,
            'created_at':        b.created_at.isoformat(),
        })

    return Response(result)


# ─────────────────────────────────────────────────────────────────────────────
# GUIDE — UPCOMING CONFIRMED BOOKINGS
# GET /api/booking/guide/upcoming/
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def guide_upcoming_bookings(request):
    user_profile = _get_user_profile(request)

    if user_profile.user_role != 'guide':
        return Response({'error': 'Only guides can access this endpoint'}, status=403)

    try:
        guide = GuideProfile.objects.get(user_profile=user_profile)
    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide profile not found'}, status=404)

    today = date_type.today()
    bookings = list(
        GuideBooking.objects.filter(
            guide_profile_id=guide.id,
            booking_status='confirmed',
            booking_date__gte=today,
        ).order_by('booking_date', 'start_time')
    )

    _enrich_request_for_serializer(request, bookings)

    result = []
    for b in bookings:
        tourist = request._tourist_map.get(str(b.tourist_profile_id))
        result.append({
            'id':             str(b.id),
            'tourist_name':   f"{tourist.first_name or ''} {tourist.last_name or ''}".strip() if tourist else '',
            'tourist_photo':  tourist.profile_pic if tourist else '',
            'tourist_phone':  tourist.phone_number if tourist else '',
            'booking_date':   str(b.booking_date),
            'start_time':     str(b.start_time),
            'end_time':       str(b.end_time),
            'total_hours':    b.total_hours,
            'total_amount':   b.total_amount,
            'guest_count':    b.guest_count,
            'special_note':   b.special_note,
            'booking_status': b.booking_status,
            'pickup_address': b.pickup_address,
            'pickup_latitude':  b.pickup_latitude,
            'pickup_longitude': b.pickup_longitude,
            'created_at':     b.created_at.isoformat(),
        })

    return Response(result)


# ─────────────────────────────────────────────────────────────────────────────
# MARK BOOKING COMPLETE  (guide side)
# POST /api/booking/guide/<booking_id>/complete/
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def guide_complete_booking(request, booking_id):
    user_profile = _get_user_profile(request)

    if user_profile.user_role != 'guide':
        return Response({'error': 'Only guides can complete bookings'}, status=403)

    try:
        guide   = GuideProfile.objects.get(user_profile=user_profile)
        booking = GuideBooking.objects.get(id=booking_id, guide_profile_id=guide.id)
    except (GuideProfile.DoesNotExist, GuideBooking.DoesNotExist):
        return Response({'error': 'Not found'}, status=404)

    if booking.booking_status != 'confirmed':
        return Response({'error': 'Only confirmed bookings can be completed'}, status=400)

    with transaction.atomic():
        booking.booking_status = 'completed'
        booking.save(update_fields=['booking_status', 'updated_at'])

        # Update guide stats
        GuideProfile.objects.filter(id=guide.id).update(
            total_completed_bookings=guide.total_completed_bookings + 1,
            total_earned=guide.total_earned + booking.total_amount,
        )

    return Response({'message': 'Booking marked as completed', 'booking_status': 'completed'})



# Stay Booking

def _enrich_stay_bookings(request, bookings):
    """
    Attach stay, host, and tourist-photo lookup maps to the request object.
    Prevents N+1 queries inside the serializer.
    """
    stay_ids    = list({str(b.stay_id)         for b in bookings})
    host_ids    = list({str(b.host_profile_id) for b in bookings})
    tourist_ids = list({str(b.tourist_profile_id) for b in bookings})
 
    stays   = Stay.objects.filter(id__in=stay_ids)
    hosts   = HostProfile.objects.select_related('user_profile').filter(id__in=host_ids)
    tourists = UserProfile.objects.filter(id__in=tourist_ids)
 
    request._stay_map          = {str(s.id): s  for s in stays}
    request._host_map          = {str(h.id): h  for h in hosts}
    request._tourist_photo_map = {str(u.id): u.profile_pic for u in tourists}
 
 
# ─────────────────────────────────────────────────────────────────────────────
# TOURIST ── SEARCH / BROWSE STAYS
# GET /api/bookings/stays/search/?city_id=&checkin=&checkout=&guests=&rooms=
# ─────────────────────────────────────────────────────────────────────────────
 
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_stays(request):
    """
    Returns verified, active stays that have availability for the given
    check-in → check-out window.
 
    Query params (all optional):
        city_id   – UUID
        checkin   – YYYY-MM-DD
        checkout  – YYYY-MM-DD
        guests    – int
        rooms     – int
        type      – homestay|farm_stay|villa|guesthouse|eco_lodge|hostel
    """
    city_id    = request.query_params.get('city_id')
    checkin    = request.query_params.get('checkin')
    checkout   = request.query_params.get('checkout')
    guests     = int(request.query_params.get('guests', 1))
    rooms      = int(request.query_params.get('rooms',  1))
    stay_type  = request.query_params.get('type')
 
    # Base queryset — verified, active stays
    qs = Stay.objects.filter(
        verification_status='verified',
        is_active=True,
    ).select_related('host')
 
    if city_id:
        qs = qs.filter(city_id=city_id)
    if stay_type:
        qs = qs.filter(type=stay_type)
    if guests:
        qs = qs.filter(max_guests__gte=guests)
    if rooms:
        qs = qs.filter(room_count__gte=rooms)
 
    # Date availability filter
    if checkin and checkout:
        try:
            ci = date_type.fromisoformat(checkin)
            co = date_type.fromisoformat(checkout)
        except ValueError:
            return Response({'error': 'Use YYYY-MM-DD for dates'}, status=400)
 
        if co <= ci:
            return Response({'error': 'checkout must be after checkin'}, status=400)
 
        # Exclude stays that have confirmed bookings overlapping our window
        from django.db.models import Q
        overlapping_stay_ids = StayBooking.objects.filter(
            booking_status__in=['pending', 'confirmed'],
            checkin_date__lt=co,
            checkout_date__gt=ci,
        ).values_list('stay_id', flat=True)
 
        qs = qs.exclude(id__in=overlapping_stay_ids)
 
    stays = list(qs.order_by('-id')[:50])
 
    result = []
    for stay in stays:
        try:
            from accounts.models import Media, City
            # Cover photo
            cover = Media.objects.filter(
                entity_type='stay', entity_id=stay.id, file_type='image'
            ).order_by('order_index').first()
 
            # City name
            city_name = ''
            if stay.city_id:
                try:
                    city_name = City.objects.get(id=stay.city_id).name
                except City.DoesNotExist:
                    pass
 
            # Host info
            host = stay.host
            if not host or not hasattr(host, 'user_profile'):
                continue
            host_name = f"{host.user_profile.first_name or ''} {host.user_profile.last_name or ''}".strip()
 
            # Avg rating
            from accounts.models import Review
            from django.db.models import Avg
            avg = Review.objects.filter(stay=stay).aggregate(avg=Avg('rating'))['avg'] or 0
 
            result.append({
                'stay_id':          str(stay.id),
                'host_profile_id':  str(host.id),
                'name':             stay.name or '',
                'type':             stay.type or '',
                'description':      stay.description or '',
                'city_name':        city_name,
                'cover_photo':      cover.file_path if cover else '',
                'room_count':       stay.room_count or 0,
                'max_guests':       stay.max_guests or 0,
                'price_per_night':  float(stay.price_per_night or 0),
                'price_entire_place': float(stay.price_entire_place or 0),
                'bathroom_count':   stay.bathroom_count or 0,
                'avg_rating':       round(float(avg), 1),
                'host_name':        host_name,
                'host_photo':       host.user_profile.profile_pic or '',
                'is_SLTDA_verified': False,
                'latitude':         stay.latitude,
                'longitude':        stay.longitude,
            })
        except Exception as e:
            logger.warning(f'search_stays: error processing stay {stay.id}: {e}')
            continue
 
    return Response({'count': len(result), 'stays': result})
 
 
# ─────────────────────────────────────────────────────────────────────────────
# TOURIST ── STAY PUBLIC PROFILE
# GET /api/bookings/stays/<stay_id>/
# ─────────────────────────────────────────────────────────────────────────────
 
@api_view(['GET'])
@permission_classes([AllowAny])
def stay_public_profile(request, stay_id):
    try:
        stay = Stay.objects.prefetch_related('stay_facilities__facility').get(
            id=stay_id, 
            is_active=True
        )
        
        # 1. Photos
        photos = Media.objects.filter(entity_type='stay', entity_id=stay.id, file_type='image').order_by('order_index')
        photos_data = [{'photo_url': p.file_path, 'is_cover': p.order_index == 0} for p in photos]
        
        # 2. Host Info (Safe fetch)
        host_user = stay.host.user_profile if hasattr(stay, 'host') and stay.host else None
        
        # 3. Reviews & Ratings
        reviews = Review.objects.filter(stay=stay).select_related('tourist__user_profile').order_by('-created_at')
        
        rating_breakdown = { "5": 0, "4": 0, "3": 0, "2": 0, "1": 0 }
        reviews_data = []
        total_rating = 0
        valid_review_count = 0
        
        for r in reviews:
            if r.rating is not None:
                rate_int = int(r.rating)
                rate_str = str(rate_int)
                if rate_str in rating_breakdown:
                    rating_breakdown[rate_str] += 1
                    
                total_rating += float(r.rating)
                valid_review_count += 1
                
            reviews_data.append({
                'id': str(r.id),
                'tourist_name': r.tourist.user_profile.full_name if getattr(r, 'tourist', None) and getattr(r.tourist, 'user_profile', None) else 'Guest',
                'tourist_photo': r.tourist.user_profile.profile_pic if getattr(r, 'tourist', None) and getattr(r.tourist, 'user_profile', None) else '',
                'rating': float(r.rating) if r.rating is not None else 5.0,
                'review': r.review or '',
                'created_at': r.created_at.isoformat() if r.created_at else ''
            })
            
        avg_rating = (total_rating / valid_review_count) if valid_review_count > 0 else 0.0

        # 4. Facilities
        facilities_list = []
        for sf in stay.stay_facilities.all():
            if hasattr(sf, 'facility') and sf.facility:
                facilities_list.append({
                    'id': str(sf.facility.id),
                    'name': sf.facility.name or '',
                    'description': sf.facility.description or '',
                })
                
        # 🛡️ FIX 1: Safe City Name fetch
        city_name = ''
        if stay.city_id:
            try:
                city = City.objects.get(id=stay.city_id)
                city_name = city.name
            except Exception:
                pass
                
        # 🛡️ FIX 2: Safe Host Member Since parsing
        member_since = ''
        if hasattr(stay, 'host') and stay.host and getattr(stay.host, 'created_at', None):
            member_since = stay.host.created_at.strftime('%B %Y')

        # 🛡️ FIX 3: Safe Time parsing
        checkin_str = stay.standard_checkin_time.strftime('%H:%M') if getattr(stay, 'standard_checkin_time', None) else '14:00'
        checkout_str = stay.standard_checkout_time.strftime('%H:%M') if getattr(stay, 'standard_checkout_time', None) else '11:00'

        # 5. Return Full Profile (WITH SAFE FALLBACKS FOR PRICES)
        data = {
            'id': str(stay.id),
            'name': stay.name or 'Unnamed Stay',
            'type': stay.type or 'Other',
            'description': stay.description or '',
            'city_name': city_name,
            'room_count': stay.room_count or 1,
            'max_guests': stay.max_guests or 1,
            'bathroom_count': stay.bathroom_count or 1,
            'price_per_night': float(stay.price_per_night or 0),
            'price_entire_place': float(stay.price_entire_place or 0),
            'entire_place_is_available': stay.entire_place_is_available or False,
            'price_per_halfday': float(stay.price_per_halfday or 0),
            'halfday_available': stay.halfday_available or False,
            'standard_checkin_time': checkin_str,
            'standard_checkout_time': checkout_str,
            'verification_status': stay.verification_status or 'pending',
            'photos': photos_data,
            'cover_photo': photos_data[0]['photo_url'] if photos_data else '',
            'facilities': facilities_list,
            'host_name': host_user.full_name if host_user else 'Host',
            'host_photo': host_user.profile_pic if host_user else '',
            'host_bio': host_user.profile_bio if host_user else '',
            'host_member_since': member_since,
            'reviews': reviews_data[:10],
            'review_count': len(reviews_data),
            'avg_rating': round(avg_rating, 1),
            'rating_breakdown': rating_breakdown,
        }
        
        return Response(data)
        
    except Stay.DoesNotExist:
        return Response({'error': 'Stay not found or not active'}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# TOURIST ── CREATE BOOKING
# POST /api/bookings/stays/create/
# ─────────────────────────────────────────────────────────────────────────────
 
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_stay_booking(request):
    user_profile = _get_user_profile(request)
    if user_profile.user_role != 'tourist':
        return Response({'error': 'Only tourists can create bookings'}, status=403)
 
    s = CreateStayBookingSerializer(data=request.data)
    if not s.is_valid():
        return Response(s.errors, status=400)
 
    data = s.validated_data
 
    # Fetch the stay
    try:
        stay = Stay.objects.select_related('host').get(
            id=data['stay_id'],
            verification_status='verified',
            is_active=True,
        )
    except Stay.DoesNotExist:
        return Response({'error': 'Stay not found or not available'}, status=404)
 
    host = stay.host
 
    # Check for overlap (pending/confirmed bookings)
    overlap = StayBooking.objects.filter(
        stay_id=stay.id,
        booking_status__in=['pending', 'confirmed'],
        checkin_date__lt=data['checkout_date'],
        checkout_date__gt=data['checkin_date'],
    )
    if data.get('booking_type') != 'entire_place':
        # For per-room bookings: count already-booked rooms on any overlapping day
        # Simple heuristic — if pending+confirmed room_count >= stay.room_count, block
        from django.db.models import Sum
        occupied = overlap.aggregate(r=Sum('room_count'))['r'] or 0
        requested = data.get('room_count', 1)
        if occupied + requested > (stay.room_count or 1):
            return Response({'error': 'Not enough rooms available for selected dates'}, status=400)
    else:
        if overlap.exists():
            return Response({'error': 'Stay is already booked for those dates'}, status=400)
 
    # Calculate price
    nights = (data['checkout_date'] - data['checkin_date']).days
    if data.get('booking_type') == 'entire_place':
        price_night = float(stay.price_entire_place or stay.price_per_night or 0)
    elif data.get('booking_type') == 'halfday':
        price_night = float(stay.price_per_halfday or 0)
        nights = 1
    else:
        price_night = float(stay.price_per_night or 0)
 
    total = round(price_night * nights, 2)
 
    try:
        with transaction.atomic():
            booking = StayBooking.objects.create(
                tourist_profile_id = user_profile.id,
                stay_id            = stay.id,
                host_profile_id    = host.id,
                checkin_date       = data['checkin_date'],
                checkout_date      = data['checkout_date'],
                total_nights       = nights,
                booking_type       = data.get('booking_type', 'per_night'),
                room_count         = data.get('room_count', 1),
                guest_count        = data.get('guest_count', 1),
                meal_preference    = data.get('meal_preference', 'none'),
                checkin_time       = data.get('checkin_time'),
                checkout_time      = data.get('checkout_time'),
                price_per_night    = price_night,
                total_amount       = total,
                special_note       = data.get('special_note'),
                booking_status     = 'pending',
                # Tourist snapshot
                tourist_full_name  = data.get('tourist_full_name', ''),
                tourist_passport   = data.get('tourist_passport', ''),
                tourist_phone      = data.get('tourist_phone', ''),
                tourist_email      = data.get('tourist_email', ''),
                tourist_country    = data.get('tourist_country', ''),
                tourist_gender     = data.get('tourist_gender', ''),
            )
 
        logger.info(f'✅ StayBooking {booking.id} created by tourist {user_profile.id}')
 
        _enrich_stay_bookings(request, [booking])
        out = StayBookingSerializer(booking, context={'request': request})
        return Response(out.data, status=201)
 
    except Exception as e:
        logger.error(f'create_stay_booking error: {e}', exc_info=True)
        return Response({'error': str(e)}, status=500)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# TOURIST ── MY STAY BOOKINGS
# GET /api/bookings/stays/my/
# ─────────────────────────────────────────────────────────────────────────────
 
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tourist_my_stay_bookings(request):
    user_profile = _get_user_profile(request)
    if user_profile.user_role != 'tourist':
        return Response({'error': 'Only tourists can access this'}, status=403)
 
    qs = StayBooking.objects.filter(
        tourist_profile_id=user_profile.id
    ).order_by('-created_at')
 
    status_filter = request.query_params.get('status')
    if status_filter:
        qs = qs.filter(booking_status=status_filter)
 
    bookings = list(qs)
    _enrich_stay_bookings(request, bookings)
 
    result = []
    for b in bookings:
        stay = request._stay_map.get(str(b.stay_id))
        host = request._host_map.get(str(b.host_profile_id))
 
        # Cover photo
        cover = ''
        if stay:
            try:
                from accounts.models import Media
                m = Media.objects.filter(
                    entity_type='stay', entity_id=stay.id, file_type='image'
                ).order_by('order_index').first()
                cover = m.file_path if m else ''
            except Exception:
                pass
 
        # City name
        city_name = ''
        if stay and stay.city_id:
            try:
                from accounts.models import City
                city_name = City.objects.get(id=stay.city_id).name
            except Exception:
                pass
 
        host_name = ''
        if host:
            up = host.user_profile
            host_name = f"{up.first_name or ''} {up.last_name or ''}".strip()
 
        result.append({
            'id':                str(b.id),
            'stay_id':           str(b.stay_id),
            'stay_name':         stay.name if stay else '',
            'stay_cover_photo':  cover,
            'host_profile_id':   str(b.host_profile_id),
            'host_name':         host_name,
            'host_photo':        host.user_profile.profile_pic if host else '',
            'city_name':         city_name,
            'checkin_date':      str(b.checkin_date),
            'checkout_date':     str(b.checkout_date),
            'total_nights':      b.total_nights,
            'room_count':        b.room_count,
            'guest_count':       b.guest_count,
            'meal_preference':   b.meal_preference,
            'price_per_night':   b.price_per_night,
            'total_amount':      b.total_amount,
            'booking_type':      b.booking_type,
            'booking_status':    b.booking_status,
            'payment_status':    b.payment_status,
            'special_note':      b.special_note,
            'host_response_note': b.host_response_note,
            'tourist_full_name': b.tourist_full_name,
            'tourist_phone':     b.tourist_phone,
            'checkin_time':      str(b.checkin_time) if b.checkin_time else None,
            'checkout_time':     str(b.checkout_time) if b.checkout_time else None,
            'created_at':        b.created_at.isoformat(),
        })
 
    return Response(result)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# TOURIST ── BOOKING DETAIL
# GET /api/bookings/stays/<booking_id>/
# ─────────────────────────────────────────────────────────────────────────────
 
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def stay_booking_detail(request, booking_id):
    user_profile = _get_user_profile(request)
 
    try:
        booking = StayBooking.objects.get(id=booking_id)
    except StayBooking.DoesNotExist:
        return Response({'error': 'Booking not found'}, status=404)
 
    is_tourist = str(booking.tourist_profile_id) == str(user_profile.id)
    is_host    = False
    if user_profile.user_role == 'host':
        try:
            hp = HostProfile.objects.get(user_profile=user_profile)
            is_host = str(booking.host_profile_id) == str(hp.id)
        except HostProfile.DoesNotExist:
            pass
 
    if not (is_tourist or is_host):
        return Response({'error': 'Not authorized'}, status=403)
 
    _enrich_stay_bookings(request, [booking])
    out = StayBookingSerializer(booking, context={'request': request})
    return Response(out.data)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# TOURIST ── CANCEL BOOKING
# POST /api/bookings/stays/<booking_id>/cancel/
# ─────────────────────────────────────────────────────────────────────────────
 
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tourist_cancel_stay_booking(request, booking_id):
    """Delegates to payment app cancel — handles refund logic automatically."""
    data = {'booking_type': 'stay', 'booking_id': str(booking_id)}
 
    from payment.views import cancel_booking_with_refund
    original_data  = request.data
    request._data  = type('FakeData', (), {'get': lambda self, k, d=None: data.get(k, d)})()
    result         = cancel_booking_with_refund(request)
    request._data  = original_data
    return result
 
 
# ─────────────────────────────────────────────────────────────────────────────
# HOST ── PENDING REQUESTS
# GET /api/bookings/stays/host/requests/
# ─────────────────────────────────────────────────────────────────────────────
 
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def host_stay_requests(request):
    user_profile = _get_user_profile(request)
    if user_profile.user_role != 'host':
        return Response({'error': 'Only hosts can access this'}, status=403)
 
    try:
        host = HostProfile.objects.get(user_profile=user_profile)
    except HostProfile.DoesNotExist:
        return Response({'error': 'Host profile not found'}, status=404)
 
    bookings = list(
        StayBooking.objects.filter(
            host_profile_id=host.id,
            booking_status='pending',
        ).order_by('-created_at')
    )
 
    _enrich_stay_bookings(request, bookings)
 
    result = []
    for b in bookings:
        stay  = request._stay_map.get(str(b.stay_id))
        cover = ''
        if stay:
            try:
                from accounts.models import Media
                m = Media.objects.filter(
                    entity_type='stay', entity_id=stay.id, file_type='image'
                ).order_by('order_index').first()
                cover = m.file_path if m else ''
            except Exception:
                pass
 
        result.append({
            'id':                str(b.id),
            'stay_id':           str(b.stay_id),
            'stay_name':         stay.name if stay else '',
            'stay_cover_photo':  cover,
            'tourist_profile_id': str(b.tourist_profile_id),
            'tourist_full_name': b.tourist_full_name,
            'tourist_phone':     b.tourist_phone,
            'tourist_email':     b.tourist_email,
            'tourist_country':   b.tourist_country,
            'tourist_photo':     request._tourist_photo_map.get(str(b.tourist_profile_id), ''),
            'checkin_date':      str(b.checkin_date),
            'checkout_date':     str(b.checkout_date),
            'total_nights':      b.total_nights,
            'room_count':        b.room_count,
            'guest_count':       b.guest_count,
            'meal_preference':   b.meal_preference,
            'price_per_night':   b.price_per_night,
            'total_amount':      b.total_amount,
            'booking_type':      b.booking_type,
            'booking_status':    b.booking_status,
            'special_note':      b.special_note,
            'checkin_time':      str(b.checkin_time) if b.checkin_time else None,
            'checkout_time':     str(b.checkout_time) if b.checkout_time else None,
            'created_at':        b.created_at.isoformat(),
        })
 
    return Response(result)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# HOST ── RESPOND (ACCEPT / REJECT)
# POST /api/bookings/stays/<booking_id>/respond/
# ─────────────────────────────────────────────────────────────────────────────
 
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def host_respond_stay_booking(request, booking_id):
    """
    Host accepts or rejects a pending stay booking.
    On ACCEPT  → captures the Stripe PaymentIntent.
    On REJECT  → releases the hold.
    """
    from payment.views import capture_payment_for_booking, release_payment_for_booking
 
    user_profile = _get_user_profile(request)
    if user_profile.user_role != 'host':
        return Response({'error': 'Only hosts can respond to bookings'}, status=403)
 
    try:
        host = HostProfile.objects.get(user_profile=user_profile)
    except HostProfile.DoesNotExist:
        return Response({'error': 'Host profile not found'}, status=404)
 
    s = RespondStayBookingSerializer(data=request.data)
    if not s.is_valid():
        return Response(s.errors, status=400)
 
    data = s.validated_data
 
    try:
        booking = StayBooking.objects.get(id=booking_id, host_profile_id=host.id)
    except StayBooking.DoesNotExist:
        return Response({'error': 'Booking not found'}, status=404)
 
    if booking.booking_status != 'pending':
        return Response({'error': f'Booking is already {booking.booking_status}'}, status=400)
 
    with transaction.atomic():
        booking.booking_status     = 'confirmed' if data['action'] == 'accept' else 'rejected'
        booking.host_response_note = data.get('host_response_note', '')
        booking.responded_at       = timezone.now()
        booking.save(update_fields=[
            'booking_status', 'host_response_note', 'responded_at', 'updated_at'
        ])
 
    # ── Stripe: capture or release AFTER DB commit ─────────────────────────────
    if data['action'] == 'accept':
        stripe_ok = capture_payment_for_booking('stay', str(booking_id))
        if not stripe_ok:
            logger.error(f"⚠️  Stripe capture failed for stay booking {booking_id} — needs manual check")
    else:
        release_payment_for_booking('stay', str(booking_id))
 
    logger.info(f"✅ Host {host.id} {data['action']}ed stay booking {booking_id}")
 
    return Response({
        'message':        f'Booking {data["action"]}ed',
        'booking_status': booking.booking_status,
        'payment_note':   (
            'Payment captured — tourist has been charged.' if data['action'] == 'accept'
            else 'Payment hold released — tourist will not be charged.'
        ),
    })
 
 
# ─────────────────────────────────────────────────────────────────────────────
# HOST ── ALL BOOKINGS (upcoming / history)
# GET /api/bookings/stays/host/all/?status=confirmed|completed|cancelled|rejected
# ─────────────────────────────────────────────────────────────────────────────
 
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def host_all_stay_bookings(request):
    user_profile = _get_user_profile(request)
    if user_profile.user_role != 'host':
        return Response({'error': 'Only hosts can access this'}, status=403)
 
    try:
        host = HostProfile.objects.get(user_profile=user_profile)
    except HostProfile.DoesNotExist:
        return Response({'error': 'Host profile not found'}, status=404)
 
    qs = StayBooking.objects.filter(
        host_profile_id=host.id
    ).exclude(booking_status='pending').order_by('-created_at')
 
    status_filter = request.query_params.get('status')
    if status_filter:
        qs = qs.filter(booking_status=status_filter)
 
    bookings = list(qs)
    _enrich_stay_bookings(request, bookings)
 
    result = []
    for b in bookings:
        stay  = request._stay_map.get(str(b.stay_id))
        cover = ''
        if stay:
            try:
                from accounts.models import Media
                m = Media.objects.filter(
                    entity_type='stay', entity_id=stay.id, file_type='image'
                ).order_by('order_index').first()
                cover = m.file_path if m else ''
            except Exception:
                pass
 
        result.append({
            'id':                str(b.id),
            'stay_id':           str(b.stay_id),
            'stay_name':         stay.name if stay else '',
            'stay_cover_photo':  cover,
            'tourist_full_name': b.tourist_full_name,
            'tourist_phone':     b.tourist_phone,
            'tourist_photo':     request._tourist_photo_map.get(str(b.tourist_profile_id), ''),
            'checkin_date':      str(b.checkin_date),
            'checkout_date':     str(b.checkout_date),
            'total_nights':      b.total_nights,
            'room_count':        b.room_count,
            'guest_count':       b.guest_count,
            'meal_preference':   b.meal_preference,
            'price_per_night':   b.price_per_night,
            'total_amount':      b.total_amount,
            'booking_status':    b.booking_status,
            'payment_status':    b.payment_status,
            'host_response_note': b.host_response_note,
            'checkin_time':      str(b.checkin_time) if b.checkin_time else None,
            'checkout_time':     str(b.checkout_time) if b.checkout_time else None,
            'created_at':        b.created_at.isoformat(),
        })
 
    return Response(result)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# HOST ── COMPLETE BOOKING
# POST /api/bookings/stays/<booking_id>/complete/
# ─────────────────────────────────────────────────────────────────────────────
 
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def host_complete_stay_booking(request, booking_id):
    user_profile = _get_user_profile(request)
    if user_profile.user_role != 'host':
        return Response({'error': 'Only hosts can complete bookings'}, status=403)
 
    try:
        host    = HostProfile.objects.get(user_profile=user_profile)
        booking = StayBooking.objects.get(id=booking_id, host_profile_id=host.id)
    except (HostProfile.DoesNotExist, StayBooking.DoesNotExist):
        return Response({'error': 'Not found'}, status=404)
 
    if booking.booking_status != 'confirmed':
        return Response({'error': 'Only confirmed bookings can be completed'}, status=400)
 
    with transaction.atomic():
        booking.booking_status = 'completed'
        booking.save(update_fields=['booking_status', 'updated_at'])
 
        HostProfile.objects.filter(id=host.id).update(
            total_completed_bookings=(host.total_completed_bookings or 0) + 1,
            total_earned=(host.total_earned or 0) + booking.total_amount,
        )
 
    return Response({'message': 'Booking completed', 'booking_status': 'completed'})
