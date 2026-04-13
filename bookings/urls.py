# bookings/urls.py

from django.urls import path
from . import views

urlpatterns = [

    # ── FIXED PATHS FIRST (no UUID) ──────────────────────────────────────────
    path('guide/create/',
         views.create_guide_booking,
         name='guide-booking-create'),

    path('guide/my/',
         views.tourist_my_bookings,
         name='tourist-my-bookings'),

    path('guide/requests/',
         views.guide_booking_requests,
         name='guide-booking-requests'),

    path('guide/upcoming/',
         views.guide_upcoming_bookings,
         name='guide-upcoming-bookings'),

    path('guide/history/',
         views.guide_booking_history,
         name='guide-booking-history'),

    # ── UUID PATHS LAST ───────────────────────────────────────────────────────
    path('guide/<uuid:booking_id>/',
         views.booking_detail,
         name='booking-detail'),

    path('guide/<uuid:booking_id>/cancel/',
         views.tourist_cancel_booking,
         name='tourist-cancel-booking'),

    path('guide/<uuid:booking_id>/respond/',
         views.guide_respond_booking,
         name='guide-respond-booking'),

    path('guide/<uuid:booking_id>/complete/',
         views.guide_complete_booking,
         name='guide-complete-booking'),


     # ── Stay fixed paths FIRST ────────────────────────────────────────────────
     path('stays/search/',               views.search_stays,               name='stay-search'),
     path('stays/create/',               views.create_stay_booking,        name='stay-booking-create'),
     path('stays/my/',                   views.tourist_my_stay_bookings,   name='tourist-my-stay-bookings'),
     path('stays/host/requests/',        views.host_stay_requests,         name='host-stay-requests'),
     path('stays/host/all/',             views.host_all_stay_bookings,     name='host-all-stay-bookings'),

     # ── Stay UUID paths AFTER ─────────────────────────────────────────────────
     path('stays/<uuid:stay_id>/profile/',      views.stay_public_profile,         name='stay-public-profile'),
     path('stays/<uuid:booking_id>/',           views.stay_booking_detail,         name='stay-booking-detail'),
     path('stays/<uuid:booking_id>/cancel/',    views.tourist_cancel_stay_booking, name='tourist-cancel-stay-booking'),
     path('stays/<uuid:booking_id>/respond/',   views.host_respond_stay_booking,   name='host-respond-stay-booking'),
     path('stays/<uuid:booking_id>/complete/',  views.host_complete_stay_booking,  name='host-complete-stay-booking'),
]