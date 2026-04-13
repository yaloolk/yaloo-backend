
# accounts/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # ── Health / Debug ──────────────────────────────────────
    path('health/', views.health_check, name='health-check'),
    path('test-auth/', views.test_auth, name='test-auth'),
    path('debug/me/', views.debug_me_endpoint, name='debug-me'),

    # ── Universal "me" ──────────────────────────────────────
    path('me/', views.get_current_user, name='get_current_user'),
    path('stats/', views.get_user_stats, name='get-user-stats'),

    # ── Profile completion ──────────────────────────────────
    path('profile/complete/tourist/', views.complete_tourist_profile),
    path('profile/complete/guide/',   views.complete_guide_profile),
    path('profile/complete/host/',    views.complete_host_profile),
    path('profile/skip/',             views.skip_profile_completion),

    # ── Profile update ──────────────────────────────────────
    path('profile/update/',   views.update_user_profile),
    path('profile/bio/',      views.update_profile_bio),
    path('profile/picture/',  views.upload_profile_picture),

    # ── Gallery ─────────────────────────────────────────────
    path('gallery/upload/',         views.upload_gallery_photo),
    path('gallery/',                views.get_gallery_photos),
    path('gallery/<uuid:photo_id>/', views.delete_gallery_photo),

    # ── Verification ────────────────────────────────────────
    path('verification/status/', views.get_verification_status),

    # ── Interests ───────────────────────────────────────────
    path('interests/',          views.get_all_interests),
    path('interests/user/',     views.get_user_interests),
    path('interests/user/add/', views.add_user_interests),

    # ── Languages / Cities ──────────────────────────────────
    path('languages/', views.get_all_languages),
    path('cities/',    views.get_all_cities),

    # ── GUIDE endpoints ─────────────────────────────────────
    path('guide/profile/',        views.get_guide_profile),
    path('guide/profile/update/', views.update_guide_profile),

    path('guide/languages/add/',                           views.add_guide_language),
    path('guide/languages/<uuid:language_id>/update/',     views.update_guide_language),
    path('guide/languages/<uuid:language_id>/delete/',     views.remove_guide_language),

    path('guide/availability/',                         views.get_guide_availability),
    path('guide/availability/add/',                     views.add_guide_availability),
    path('guide/availability/<uuid:slot_id>/delete/',   views.delete_guide_availability),
    path('guide/availability/toggle/',                  views.toggle_guide_is_available),

    path('guide/reviews/', views.get_guide_reviews),

    path('specializations/',                                          views.get_all_specializations,       name='specializations-list'),
    path('guide/specializations/add/',                                views.add_guide_specializations,     name='guide-specializations-add'),
    path('guide/specializations/<uuid:specialization_id>/delete/',    views.remove_guide_specialization,   name='guide-specialization-delete'),

    path('activities/',                                        views.get_all_activities,      name='activities-list'),
    path('activities/local/',                                  views.get_local_activities,    name='local-activities'),
    path('guide/activities/',                                  views.get_guide_activities,    name='guide-activities-list'),
    path('guide/activities/add/',                              views.add_guide_activity,      name='guide-activity-add'),
    path('guide/activities/<uuid:local_activity_id>/delete/',  views.remove_guide_activity,   name='guide-activity-delete'),
    # ══════════════════════════════════════════════════════════
    # HOST PROFILE
    # ══════════════════════════════════════════════════════════
    path('host/profile/', views.get_host_profile, name='host-profile'),
    path('host/profile/update/', views.update_host_profile, name='host-profile-update'),
    path('host/profile/picture/', views.update_profile_picture, name='host-profile-picture'),
    path('host/dashboard/', views.get_host_dashboard, name='host-dashboard'),
    
    # ══════════════════════════════════════════════════════════
    # STAY MANAGEMENT
    # ══════════════════════════════════════════════════════════
    path('host/stays/create/', views.create_stay, name='stay-create'),
    path('host/stays/<uuid:stay_id>/', views.get_stay_detail, name='stay-detail'),
    path('host/stays/<uuid:stay_id>/update/', views.update_stay, name='stay-update'),
    
    # ══════════════════════════════════════════════════════════
    # STAY PHOTOS
    # ══════════════════════════════════════════════════════════
    path('host/stays/<uuid:stay_id>/photos/add/', views.add_stay_photos, name='stay-photos-add'),
    path('host/stays/<uuid:stay_id>/photos/<uuid:photo_id>/delete/', views.delete_stay_photo, name='stay-photo-delete'),
    path('host/stays/<uuid:stay_id>/photos/reorder/', views.reorder_stay_photos, name='stay-photos-reorder'),
    
    # ══════════════════════════════════════════════════════════
    # FACILITIES
    # ══════════════════════════════════════════════════════════
    path('facilities/', views.get_all_facilities, name='facilities-list'),
    path('host/stays/<uuid:stay_id>/facilities/', views.update_stay_facilities, name='stay-facilities-update'),
    
    # ══════════════════════════════════════════════════════════
    # AVAILABILITY
    # ══════════════════════════════════════════════════════════
    path('host/stays/<uuid:stay_id>/availability/', views.get_stay_availability, name='stay-availability-get'),
    path('host/stays/<uuid:stay_id>/availability/set/', views.set_stay_availability, name='stay-availability-set'),
    path('host/stays/<uuid:stay_id>/availability/<uuid:avail_id>/', views.update_single_availability, name='stay-availability-update'),
    
    # ══════════════════════════════════════════════════════════
    # LANGUAGES
    # ══════════════════════════════════════════════════════════
    path('host/languages/add/', views.add_host_language, name='host-language-add'),
    path('host/languages/<uuid:language_id>/update/', views.update_host_language, name='host-language-update'),
    path('host/languages/<uuid:language_id>/delete/', views.remove_host_language, name='host-language-delete'),
    
    
    # ══════════════════════════════════════════════════════════
    # BOOKINGS
    # ══════════════════════════════════════════════════════════
    path('host/bookings/<uuid:booking_id>/', views.get_booking_detail, name='booking-detail'),
    path('host/bookings/<uuid:booking_id>/respond/', views.respond_to_booking, name='booking-respond'),
    
    # Local activities
    path('activities/local/', views.get_local_activities, name='local-activities'),

    # Guides Search
    path('guides/search/',               views.search_guides,        name='guide-search'),
    path('guides/<uuid:guide_profile_id>/', views.guide_public_profile, name='guide-public-profile'),

    # tourist public profile
    path('tourist/<uuid:tourist_id>/public-profile/', views.tourist_public_profile, name='tourist-public-profile'),

    # tourist pickup location
    path('locations/', views.get_system_locations, name='system-locations'),
    path('locations/saved/', views.tourist_saved_locations, name='tourist-saved-locations'),
    path('locations/saved/<uuid:location_id>/', views.delete_saved_location, name='tourist-saved-location-delete'),

    # tourist guide review
    path('reviews/', views.create_guide_review, name='create-review'),
    
    # tourist stay review (ADD THIS LINE)
    path('stays/<uuid:booking_id>/review/', views.create_stay_review, name='create-stay-review'),
]