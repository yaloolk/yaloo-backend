# accounts/views.py

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction, connection
import uuid as uuid_lib
import json
import logging
from datetime import datetime, time, timedelta, date
from datetime import datetime as _datetime, timedelta as _timedelta, date as _date_type
from django.db.models import Prefetch, Avg
from django.core.cache import cache
from django.db.models import Count as _Count

from .supabase_utils import get_supabase_client

from .models import (
    UserProfile, TouristProfile, GuideProfile, HostProfile, 
    Interest, UserInterest, Language, UserLanguage, City, 
    ProfileDocument, Stay, StayPic, StayDocument, Media, GuideProfile, GuideAvailability, GuideAvailabilityPattern, Review, Facilities,
    StayFacility, StayAvailability, Booking, TouristLocation, Specialization, GuideSpecialization, Activity, LocalActivity,
)

from bookings.models import GuideBooking, StayBooking

from .serializers import (
    UserProfileSerializer, InterestSerializer, UserInterestSerializer, 
    LanguageSerializer, CitySerializer, GuideProfileSerializer, 
    HostProfileSerializer, ProfileDocumentSerializer, StaySerializer, StayPicSerializer, StayDocumentSerializer, CompleteGuideProfileSerializer,
    GuideAvailabilitySerializer, GuideAvailabilityPatternSerializer , ReviewSerializer, 
    FacilitiesSerializer, StayAvailabilitySerializer, CompleteHostProfileSerializer, 
    CompleteStaySerializer, MediaSerializer, StayDetailSerializer, BookingSerializer, SpecializationSerializer,
    ActivitySerializer, LocalActivitySerializer,
)

from .redis_utils import RedisCache
logger = logging.getLogger(__name__)

_LOCATIONS_CACHE_KEY = 'system_tourist_locations'
_LOCATIONS_CACHE_TTL = 3600  # 1 hour — rarely changes

# ══════════════════════════════════════════════════════════
# REDIS SAFE WRAPPER - ✅ MAKES REDIS OPTIONAL
# ══════════════════════════════════════════════════════════

def safe_cache_get(key):
    """Get from Redis, return None if Redis is down"""
    try:
        cached = cache.get(key)
        if cached:
            try:
                return json.loads(cached)
            except:
                return cached
        return None
    except Exception as e:
        logger.warning(f"⚠️  Redis unavailable for GET {key}: {e}")
        return None

def safe_cache_set(key, value, timeout=600):
    """Set to Redis, silently fail if Redis is down"""
    try:
        cache.set(key, json.dumps(value, default=str), timeout=timeout)
    except Exception as e:
        logger.warning(f"⚠️  Redis unavailable for SET {key}: {e}")
        pass

def safe_cache_delete(key):
    """Delete from Redis, silently fail if Redis is down"""
    try:
        cache.delete(key)
    except Exception as e:
        logger.warning(f"⚠️  Redis unavailable for DELETE {key}: {e}")
        pass

def safe_cache_delete_pattern(pattern):
    """Delete multiple keys matching pattern"""
    try:
        keys = cache.keys(pattern)
        for key in keys:
            cache.delete(key)
    except Exception as e:
        logger.warning(f"⚠️  Redis unavailable for DELETE pattern {pattern}: {e}")
        pass


def _resolve_user_profile(request):
    """Get UserProfile regardless of auth backend."""
    if hasattr(request.user, 'user_profile'):
        return request.user.user_profile
    return request.user

# ══════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════

def _get_user_profile(request):
    """Get UserProfile from request"""
    if hasattr(request.user, 'user_profile'):
        return request.user.user_profile
    return UserProfile.objects.get(auth_user_id=request.user.id)

def _get_host_profile(user_profile):
    """Get or create host profile"""
    if user_profile.user_role != 'host':
        return None, Response({'error': 'Not authorized as host'}, status=403)
    
    try:
        return HostProfile.objects.get(user_profile=user_profile), None
    except HostProfile.DoesNotExist:
        host = HostProfile.objects.create(
            user_profile=user_profile,
            verification_status='pending'
        )
        return host, None


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Health check including Redis status"""
    redis_health = RedisCache.health_check()
    
    return Response({
        'status': 'healthy',
        'message': 'Yaloo API is running',
        'redis': redis_health
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def test_auth(request):
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    
    return Response({
        'message': 'Authentication successful!',
        'user': {
            'id': str(user_profile.id),
            'auth_user_id': str(user_profile.auth_user_id),
            'full_name': user_profile.full_name,
            'user_role': user_profile.user_role,
            'is_complete': user_profile.is_complete,
            'verification_status': user_profile.verification_status,
        }
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def get_all_interests(request):
    """Get all available interests"""
    interests = Interest.objects.filter(is_active=True).order_by('category', 'name')
    serializer = InterestSerializer(interests, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_interests(request):
    """Get current user's interests - WITH REDIS CACHE"""
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    user_id = str(user_profile.id)
    
    # ✅ Try cache first
    cached_interests = RedisCache.get_user_interests(user_id)
    if cached_interests:
        logger.info(f"🚀 Serving interests from cache for user {user_id}")
        return Response(cached_interests)
    
    # ❌ Cache miss - fetch from DB
    logger.info(f"🔍 Cache miss - fetching interests from DB for user {user_id}")
    user_interests = UserInterest.objects.filter(user_profile=user_profile).select_related('interest')
    serializer = UserInterestSerializer(user_interests, many=True)
    
    # ✅ Store in cache
    RedisCache.set_user_interests(user_id, serializer.data)
    
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_user_interests(request):
    """Add interests for current user - INVALIDATE CACHE"""
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    user_id = str(user_profile.id)
    
    interest_ids = request.data.get('interest_ids', [])
    
    if not interest_ids:
        return Response({'error': 'No interests provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Clear existing interests
        UserInterest.objects.filter(user_profile=user_profile).delete()
        
        # Add new interests
        for interest_id in interest_ids:
            UserInterest.objects.create(
                user_profile=user_profile,
                interest_id=interest_id
            )
        
        # ✅ Invalidate cache
        RedisCache.invalidate_user_profile(user_id)
        
        # Return updated list
        user_interests = UserInterest.objects.filter(user_profile=user_profile)
        serializer = UserInterestSerializer(user_interests, many=True)
        
        # ✅ Cache new data
        RedisCache.set_user_interests(user_id, serializer.data)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_languages(request):
    """Get all languages"""
    cache_key = 'all_languages'
    
    cached = safe_cache_get(cache_key)
    if cached:
        return Response(cached)
    
    languages = Language.objects.filter(is_active=True).order_by('name')
    data = LanguageSerializer(languages, many=True).data
    
    safe_cache_set(cache_key, list(data), timeout=3600)
    
    return Response(data)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_all_cities(request):
    """Get all cities"""
    cache_key = 'all_cities'
    cached = safe_cache_get(cache_key)
    if cached:
        return Response(cached)
    
    cities = City.objects.filter(is_active=True).order_by('name')
    data = [{
        'id': str(c.id),
        'name': c.name
    } for c in cities]
    
    safe_cache_set(cache_key, data, timeout=3600)
    return Response(data)




# ==================== TOURIST PROFILE COMPLETION ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def complete_tourist_profile(request):
    """Complete tourist profile with interests - INVALIDATE CACHE"""
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    user_id = str(user_profile.id)
    
    if user_profile.user_role != 'tourist':
        return Response({'error': 'This endpoint is only for tourists'}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        with transaction.atomic():
            # Update user profile
            user_profile.first_name = request.data.get('first_name', '')
            user_profile.last_name = request.data.get('last_name', '')
            
            phone = request.data.get('phone_number')
            if phone:
                if not phone.startswith('+'):
                    return Response(
                        {'error': 'Phone number must include country code (e.g., +94...)'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
                user_profile.phone_number = phone
            
            user_profile.date_of_birth = request.data.get('date_of_birth')
            user_profile.gender = request.data.get('gender')
            user_profile.country = request.data.get('country')
            user_profile.profile_bio = request.data.get('bio', '')
            user_profile.is_complete = True
            user_profile.save()
            
            # Create or update tourist profile
            tourist_profile, created = TouristProfile.objects.get_or_create(user_profile=user_profile)
            tourist_profile.passport_number = request.data.get('passport_number')
            
            travel_style = request.data.get('travel_style')
            if travel_style:
                tourist_profile.travel_style = travel_style

            language_id = request.data.get('preferred_language')
            if language_id:
                try:
                    lang_obj = Language.objects.get(id=language_id)
                    user_lang, created = UserLanguage.objects.get_or_create(
                        user_profile=user_profile,
                        language=lang_obj,
                        defaults={
                            'proficiency': 'native',
                            'is_native': True
                        }
                    )
                    tourist_profile.preferred_language = user_lang
                except Language.DoesNotExist:
                    pass
            
            tourist_profile.save()
            
            # Handle interests
            interest_ids = request.data.get('interest_ids', [])
            if interest_ids:
                UserInterest.objects.filter(user_profile=user_profile).delete()
                for interest_id in interest_ids:
                    UserInterest.objects.create(
                        user_profile=user_profile,
                        interest_id=interest_id
                    )
        
        # ✅ Invalidate ALL cached data for this user
        RedisCache.invalidate_all_user_data(user_id)
        
        serializer = UserProfileSerializer(user_profile)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def skip_profile_completion(request):
    """Allow tourists to skip profile completion"""
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    
    if user_profile.user_role != 'tourist':
        return Response({'error': 'Only tourists can skip'}, status=status.HTTP_403_FORBIDDEN)
    
    user_profile.is_complete = True
    user_profile.save()
    
    # Create minimal tourist profile
    TouristProfile.objects.get_or_create(user_profile=user_profile)
    
    serializer = UserProfileSerializer(user_profile)
    return Response(serializer.data, status=status.HTTP_200_OK)


# ==================== FILE UPLOAD HELPER ====================

def upload_file_to_supabase(file, bucket_name, folder_path):
    """Upload a file to Supabase Storage"""
    supabase = get_supabase_client(use_service_role=True)
    
    if not supabase:
        raise Exception("Supabase client not initialized")
    
    file_extension = file.name.split('.')[-1]
    unique_filename = f"{uuid_lib.uuid4()}.{file_extension}"
    file_path = f"{folder_path}/{unique_filename}"
    
    response = supabase.storage.from_(bucket_name).upload(
        file_path,
        file.read(),
        {"content-type": file.content_type}
    )
    
    public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)
    
    return public_url


@api_view(['GET'])
@permission_classes([IsAuthenticated]) # Or [AllowAny] if anyone can see it
def tourist_public_profile(request, tourist_id):
    """Fetch public details for a tourist profile"""
    try:
        # Assuming tourist_id is the user_profile.id
        user_profile = UserProfile.objects.get(id=tourist_id, user_role='tourist')
        tourist = user_profile.tourist_profile
        
        # Get Languages
        languages = [
            {'name': l.language.name, 'is_native': l.is_native}
            for l in UserLanguage.objects.filter(user_profile=user_profile).select_related('language')
        ]
        
        # Get Interests
        interests = [
            {'name': i.interest.name}
            for i in UserInterest.objects.filter(user_profile=user_profile).select_related('interest')
        ]
        
        data = {
            'id': str(user_profile.id),
            'full_name': user_profile.full_name,
            'profile_pic': user_profile.profile_pic or '',
            'country': user_profile.country or '',
            'profile_bio': user_profile.profile_bio or '',
            'travel_style': tourist.travel_style or '',
            'member_since': user_profile.created_at.isoformat(),
            'tours_completed': tourist.total_bookings,
            'avg_rating': float(tourist.trust_score or 0.0),
            'review_count': 0, # Tourists typically don't receive reviews in this schema
            'is_verified': user_profile.is_complete,
            'languages': languages,
            'interests': interests,
            'reviews': [],
            'rating_breakdown': { "5": 0, "4": 0, "3": 0, "2": 0, "1": 0 }
        }
        
        return Response(data)
        
    except UserProfile.DoesNotExist:
        return Response({'error': 'Tourist not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

# ==================== GUIDE PROFILE COMPLETION ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def complete_guide_profile(request):
    """
    Complete guide profile with verification documents
    Uses existing profile_document table
    """
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    
    if user_profile.user_role != 'guide':
        return Response({'error': 'This endpoint is only for guides'}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        with transaction.atomic():
            # Update user profile
            user_profile.first_name = request.data.get('first_name', '')
            user_profile.last_name = request.data.get('last_name', '')
            user_profile.phone_number = request.data.get('phone_number')
            user_profile.date_of_birth = request.data.get('date_of_birth')
            user_profile.gender = request.data.get('gender')
            user_profile.country = request.data.get('country')
            user_profile.is_complete = True
            
            # Handle profile picture upload
            profile_pic = request.FILES.get('profile_photo')
            if profile_pic:
                try:
                    profile_url = upload_file_to_supabase(
                        profile_pic,
                        'verification-documents',
                        f'guides/{user_profile.id}/profile'
                    )
                    user_profile.profile_pic = profile_url
                except Exception as e:
                    return Response({'error': f'Profile photo upload failed: {str(e)}'}, 
                                  status=status.HTTP_400_BAD_REQUEST)
            
            user_profile.save()
            
            # Create or update guide profile
            city_id = request.data.get('city_id')
            if not city_id:
                return Response({'error': 'city_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Verify city exists
            try:
                City.objects.get(id=city_id)
            except City.DoesNotExist:
                return Response({'error': 'City not found'}, status=status.HTTP_400_BAD_REQUEST)
            
            guide_profile, created = GuideProfile.objects.get_or_create(
                user_profile=user_profile,
                defaults={'city_id': city_id}
            )
            
            if not created:
                guide_profile.city_id = city_id
            
            guide_profile.experience_years = request.data.get('experience_years')
            guide_profile.education = request.data.get('education', '')
            guide_profile.rate_per_hour = request.data.get('rate_per_hour', 0.0)
            guide_profile.verification_status = 'pending'
            guide_profile.save()
            
            # Handle languages
            language_ids = request.data.getlist('language_ids[]') or request.data.getlist('language_ids')
            if language_ids:
                # Clear existing languages
                UserLanguage.objects.filter(user_profile=user_profile).delete()
                
                # Add new languages
                for lang_id in language_ids:
                    try:
                        lang_obj = Language.objects.get(id=lang_id)
                        UserLanguage.objects.create(
                            user_profile=user_profile,
                            language=lang_obj,
                            proficiency='native',
                            is_native=True
                        )
                    except Language.DoesNotExist:
                        continue
            
            # Handle document uploads using profile_document table
            gov_id = request.FILES.get('government_id')
            license_file = request.FILES.get('license')
            
            # Upload and save government ID
            if gov_id:
                try:
                    doc_url = upload_file_to_supabase(
                        gov_id,
                        'verification-documents',
                        f'guides/{user_profile.id}/documents'
                    )
                    ProfileDocument.objects.create(
                        guide=guide_profile,
                        document_url=doc_url,
                        document_type='government_id',
                        verification_status='pending'
                    )
                except Exception as e:
                    return Response({'error': f'Government ID upload failed: {str(e)}'}, 
                                  status=status.HTTP_400_BAD_REQUEST)
            
            # If profile photo was uploaded, save it to profile_document as well
            if profile_pic:
                ProfileDocument.objects.create(
                    guide=guide_profile,
                    document_url=user_profile.profile_pic,
                    document_type='profile_photo',
                    verification_status='pending'
                )
            
            # Upload and save license (optional)
            if license_file:
                try:
                    license_url = upload_file_to_supabase(
                        license_file,
                        'verification-documents',
                        f'guides/{user_profile.id}/documents'
                    )
                    ProfileDocument.objects.create(
                        guide=guide_profile,
                        document_url=license_url,
                        document_type='license',
                        verification_status='pending'
                    )
                except Exception as e:
                    # License is optional, so we just log the error
                    print(f"License upload failed: {str(e)}")
        
        serializer = GuideProfileSerializer(guide_profile)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        import traceback
        traceback.print_exc() # Print full error to console for debugging
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ==================== HOST PROFILE COMPLETION ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def complete_host_profile(request):
    """
    Complete host profile with verification documents
    Uses existing profile_document table for ID/profile photo
    Property photos will be added when creating stays
    """
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    
    if user_profile.user_role != 'host':
        return Response({'error': 'This endpoint is only for hosts'}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        with transaction.atomic():
            # Update user profile
            user_profile.first_name = request.data.get('first_name', '')
            user_profile.last_name = request.data.get('last_name', '')
            user_profile.phone_number = request.data.get('phone_number')
            user_profile.country = request.data.get('country')
            user_profile.is_complete = True
            
            # Handle profile picture upload
            profile_pic = request.FILES.get('profile_photo')
            if profile_pic:
                try:
                    profile_url = upload_file_to_supabase(
                        profile_pic,
                        'verification-documents',
                        f'hosts/{user_profile.id}/profile'
                    )
                    user_profile.profile_pic = profile_url
                except Exception as e:
                    return Response({'error': f'Profile photo upload failed: {str(e)}'}, 
                                  status=status.HTTP_400_BAD_REQUEST)
            
            user_profile.save()
            
            # Create or update host profile
            host_profile, created = HostProfile.objects.get_or_create(user_profile=user_profile)
            host_profile.verification_status = 'pending'
            host_profile.save()
            
            # Handle document uploads
            gov_id = request.FILES.get('government_id')
            
            # Upload and save government ID
            if gov_id:
                try:
                    doc_url = upload_file_to_supabase(
                        gov_id,
                        'verification-documents',
                        f'hosts/{user_profile.id}/documents'
                    )
                    ProfileDocument.objects.create(
                        host=host_profile,
                        document_url=doc_url,
                        document_type='government_id',
                        verification_status='pending'
                    )
                except Exception as e:
                    return Response({'error': f'Government ID upload failed: {str(e)}'}, 
                                  status=status.HTTP_400_BAD_REQUEST)
            
            # If profile photo was uploaded, save it to profile_document as well
            if profile_pic:
                ProfileDocument.objects.create(
                    host=host_profile,
                    document_url=user_profile.profile_pic,
                    document_type='profile_photo',
                    verification_status='pending'
                )
            
            # NOTE: Property photos will be handled when host creates a Stay
            # For now, we can optionally accept them and store them temporarily
            property_photos = request.FILES.getlist('property_photos[]') or request.FILES.getlist('property_photos')
            if property_photos:
                for photo in property_photos:
                    try:
                        photo_url = upload_file_to_supabase(
                            photo,
                            'verification-documents',
                            f'hosts/{user_profile.id}/property'
                        )
                        # Store as 'property_photo' type - these will be moved to stay_pic when stay is created
                        ProfileDocument.objects.create(
                            host=host_profile,
                            document_url=photo_url,
                            document_type='property_photo',
                            verification_status='pending'
                        )
                    except Exception as e:
                        print(f"Property photo upload failed: {str(e)}")
                        continue
        
        serializer = HostProfileSerializer(host_profile)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ==================== VERIFICATION STATUS ENDPOINTS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_verification_status(request):
    """Get verification status for guide/host"""
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    
    if user_profile.user_role == 'guide':
        try:
            guide_profile = GuideProfile.objects.get(user_profile=user_profile)
            documents = ProfileDocument.objects.filter(guide=guide_profile)
            return Response({
                'verification_status': guide_profile.verification_status,
                'is_verified': guide_profile.is_verified,
                'profile_complete': user_profile.is_complete,
                'documents_count': documents.count(),
                'pending_documents': documents.filter(verification_status='pending').count()
            })
        except GuideProfile.DoesNotExist:
            return Response({'error': 'Guide profile not found'}, status=status.HTTP_404_NOT_FOUND)
    
    elif user_profile.user_role == 'host':
        try:
            host_profile = HostProfile.objects.get(user_profile=user_profile)
            documents = ProfileDocument.objects.filter(host=host_profile)
            return Response({
                'verification_status': host_profile.verification_status,
                'is_verified': host_profile.is_verified,
                'profile_complete': user_profile.is_complete,
                'documents_count': documents.count(),
                'pending_documents': documents.filter(verification_status='pending').count()
            })
        except HostProfile.DoesNotExist:
            return Response({'error': 'Host profile not found'}, status=status.HTTP_404_NOT_FOUND)
    
    return Response({'error': 'Not a guide or host'}, status=status.HTTP_400_BAD_REQUEST)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def create_stay(request):
    # Robust way to get the user profile
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    
    # --- FIX START: Auto-create HostProfile if missing ---
    if user_profile.user_role == 'host':
        # get_or_create checks if it exists; if not, it creates it immediately.
        host_profile, created = HostProfile.objects.get_or_create(user_profile=user_profile)
    else:
        return Response({'error': 'You must be a Host to create a stay'}, status=status.HTTP_403_FORBIDDEN)
    # --- FIX END ---

    data = request.data
    
    try:
        with transaction.atomic():
            # 2. Create the Stay Record
            stay = Stay.objects.create(
                host=host_profile,
                name=data.get('name'),
                type=data.get('type'),
                house_no=data.get('house_no'),
                street=data.get('street'),
                town=data.get('town'),
                city_id=data.get('city_id'),
                postal_code=data.get('postal_code'),
                latitude=data.get('latitude'),
                longitude=data.get('longitude'),
                room_count=data.get('room_count'),
                max_guests=data.get('max_guests'),
                price_per_night=data.get('price_per_night'),
                bathroom_count=data.get('bathroom_count'),
                shared_bathrooms=data.get('shared_bathrooms') == 'true',
                entire_place_is_available=data.get('entire_place_is_available') == 'true',
                price_entire_place=data.get('price_entire_place') or 0,
                price_per_extra_guest=data.get('price_per_extra_guest') or 0,
                halfday_available=data.get('halfday_available') == 'true',
                price_per_halfday=data.get('price_per_halfday') or 0,
            )

            # 3. Handle SLTDA Document
            sltda_file = request.FILES.get('sltda_document')
            if sltda_file:
                path = f"stays/{stay.id}/docs/{sltda_file.name}"
                doc_url = upload_file_to_supabase(sltda_file, 'stay-documents', path)
                
                StayDocument.objects.create(
                    stay=stay,
                    document_type='sltda_registration',
                    document_url=doc_url,
                    verification_status='pending'
                )

            # 4. Handle Property Photos
            photos = request.FILES.getlist('photos') 
            for index, photo in enumerate(photos):
                path = f"stays/{stay.id}/gallery/{photo.name}"
                photo_url = upload_file_to_supabase(photo, 'stay-images', path)
                
                StayPic.objects.create(
                    stay=stay,
                    photo_url=photo_url,
                    position=index,
                    is_cover=(index == 0)
                )
            
            # Increment host listing count
            host_profile.no_of_stays_owned += 1
            host_profile.save()

            return Response({'message': 'Stay created successfully', 'stay_id': stay.id}, status=201)

    except Exception as e:
        print(f"Error creating stay: {str(e)}")
        return Response({'error': str(e)}, status=400)


@api_view(['GET'])
@permission_classes([AllowAny])  # No auth required for testing
def debug_me_endpoint(request):
    """Debug endpoint to check what's happening"""
    return Response({
        'message': 'Endpoint exists',
        'is_authenticated': request.user.is_authenticated,
        'user': str(request.user) if request.user.is_authenticated else None,
        'headers': dict(request.headers),
    })


# Add these updated views to your accounts/views.py

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_current_user(request):
    """
    Universal endpoint - works for TOURIST, GUIDE, HOST
    Returns appropriate data based on user_role
    Redis cached for performance
    """
    user_profile = (
        request.user.user_profile
        if hasattr(request.user, 'user_profile')
        else request.user
    )
    user_id = str(user_profile.id)

    # ✅ Try Redis cache first
    # cached = RedisCache.get_user_profile(user_id)
    # if cached:
    #     logger.info(f"🚀 Cache HIT /me for {user_id}")
    #     RedisCache.set_user_online(user_id)
    #     return Response(cached)

    # logger.info(f"🔍 Cache MISS /me for {user_id}")

    skip_cache = request.headers.get('X-No-Cache') == 'true'
    
    if not skip_cache:
        cached = RedisCache.get_user_profile(user_id)
        if cached:
            logger.info(f"🚀 Cache HIT /me for {user_id}")
            RedisCache.set_user_online(user_id)
            return Response(cached)
    else:
        # Invalidate stale cache before fresh fetch
        RedisCache.invalidate_all_user_data(user_id)
        logger.info(f"🔄 Cache BYPASSED for {user_id}")

    # ── GUIDE ──────────────────────────────────────────────
    if user_profile.user_role == 'guide':
        try:
            guide = GuideProfile.objects.select_related('user_profile').get(
                user_profile=user_profile
            )
            
            # Auto-update avg_rating from reviews
            agg = Review.objects.filter(guide=guide).aggregate(avg=Avg('rating'))
            if agg['avg'] is not None:
                guide.avg_rating = round(agg['avg'], 1)
                guide.save(update_fields=['avg_rating'])
            
            data = CompleteGuideProfileSerializer(guide).data
            
        except GuideProfile.DoesNotExist:
            return Response({'error': 'Guide profile not found'}, status=404)

    # ── TOURIST ────────────────────────────────────────────
    elif user_profile.user_role == 'tourist':
        # Your existing tourist logic
        additional = {}
        if hasattr(user_profile, 'tourist_profile'):
            tourist = user_profile.tourist_profile
            langs = UserLanguage.objects.filter(
                user_profile=user_profile).select_related('language')
            additional = {
                'total_trips_completed': tourist.total_bookings,
                'languages': [
                    {'id': str(ul.language.id), 'name': ul.language.name,
                     'code': ul.language.code, 'is_native': ul.is_native,
                     'proficiency': ul.proficiency}
                    for ul in langs
                ],
                'passport_number': tourist.passport_number,
                'emergency_contact_name': tourist.emergency_contact_name,
                'emergency_contact_relation': tourist.emergency_contact_relation,
                'emergency_contact_number': tourist.emergency_contact_number,
                'travel_style': tourist.travel_style,
            }
        data = {**UserProfileSerializer(user_profile).data, **additional}

    # ── HOST ───────────────────────────────────────────────
    elif user_profile.user_role == 'host':
        # ✅ FIX: Fresh DB query, never rely on cache for host approval check
        additional = {}
        has_verified_stay = False
        
        if hasattr(user_profile, 'host_profile'):
            # Always query DB fresh for verification-critical data
            has_verified_stay = user_profile.host_profile.stays.filter(
                verification_status='verified'
            ).exists()
            additional['no_of_stays_owned'] = user_profile.host_profile.no_of_stays_owned
            additional['host_verification_status'] = user_profile.host_profile.verification_status
        
        serializer_data = UserProfileSerializer(user_profile).data
        data = {
            **serializer_data,
            'has_verified_stay': has_verified_stay,  # ✅ Explicit override
        }

    # ── OTHER ─────────────────────────────────
    else:
        data = UserProfileSerializer(user_profile).data

    # ✅ Cache the result
    RedisCache.set_user_profile(user_id, data)
    RedisCache.set_user_online(user_id)
    
    return Response(data)


@api_view(['PATCH', 'PUT'])
@permission_classes([IsAuthenticated])
def update_user_profile(request):
    """Update user profile information - INVALIDATE CACHE"""
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    user_id = str(user_profile.id)
    
    try:
        # Update basic profile fields
        if 'first_name' in request.data:
            user_profile.first_name = request.data['first_name']
        if 'last_name' in request.data:
            user_profile.last_name = request.data['last_name']
        
        if 'phone_number' in request.data:
            phone = request.data['phone_number']
            if phone and not phone.startswith('+'):
                return Response(
                    {'error': 'Phone number must include country code (e.g., +94...)'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user_profile.phone_number = phone
            
        if 'date_of_birth' in request.data:
            user_profile.date_of_birth = request.data['date_of_birth']
        if 'gender' in request.data:
            user_profile.gender = request.data['gender']
        if 'country' in request.data:
            user_profile.country = request.data['country']
        if 'profile_bio' in request.data:
            user_profile.profile_bio = request.data['profile_bio']
        
        user_profile.save()
        
        # Update role-specific profile if needed
        if user_profile.user_role == 'tourist' and hasattr(user_profile, 'tourist_profile'):
            tourist = user_profile.tourist_profile
            if 'passport_number' in request.data:
                tourist.passport_number = request.data['passport_number']
            if 'travel_style' in request.data:
                tourist.travel_style = request.data['travel_style']
            if 'emergency_contact_name' in request.data:
                tourist.emergency_contact_name = request.data['emergency_contact_name']
            if 'emergency_contact_relation' in request.data:
                tourist.emergency_contact_relation = request.data['emergency_contact_relation']
            if 'emergency_contact_number' in request.data:
                ec_phone = request.data['emergency_contact_number']
                if ec_phone and not ec_phone.startswith('+'):
                     return Response(
                        {'error': 'Emergency contact number must include country code'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                tourist.emergency_contact_number = ec_phone
            tourist.save()
        
        # ✅ Invalidate cache
        RedisCache.invalidate_all_user_data(user_id)
        
        serializer = UserProfileSerializer(user_profile)
        return Response({
            'message': 'Profile updated successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_stats(request):
    """Get user statistics - WITH REDIS CACHE"""
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    user_id = str(user_profile.id)
    
    # ✅ Try cache first
    cached_stats = RedisCache.get_user_stats(user_id)
    if cached_stats:
        logger.info(f"🚀 Serving stats from cache for user {user_id}")
        return Response(cached_stats)
    
    # ❌ Cache miss
    stats = {
        'total_trips': 0,
        'languages_count': 0,
        'languages': [],
        'member_since': user_profile.created_at.year if user_profile.created_at else None,
    }
    
    if user_profile.user_role == 'tourist' and hasattr(user_profile, 'tourist_profile'):
        tourist = user_profile.tourist_profile
        stats['total_trips'] = tourist.total_bookings
        
        user_languages = UserLanguage.objects.filter(user_profile=user_profile).select_related('language')
        stats['languages_count'] = user_languages.count()
        stats['languages'] = [
            {
                'id': str(ul.language.id),
                'name': ul.language.name,
                'code': ul.language.code,
                'is_native': ul.is_native,
            }
            for ul in user_languages
        ]
    
    # ✅ Cache the result
    RedisCache.set_user_stats(user_id, stats)
    
    return Response(stats)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_profile_picture(request):
    """
    Upload or update profile picture
    """
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    
    profile_pic = request.FILES.get('profile_pic')
    if not profile_pic:
        return Response({'error': 'No image provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Upload to Supabase Storage
        photo_url = upload_file_to_supabase(
            profile_pic,
            'profile-pictures',  # bucket name
            f'users/{user_profile.id}'  # folder path
        )
        
        # Update user profile
        user_profile.profile_pic = photo_url
        user_profile.save()
        
        return Response({
            'message': 'Profile picture uploaded successfully',
            'profile_pic': photo_url
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_gallery_photo(request):
    """Upload gallery photo - INVALIDATE CACHE"""
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    user_id = str(user_profile.id)
    
    photo = request.FILES.get('photo')
    if not photo:
        return Response({'error': 'No photo provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        photo_url = upload_file_to_supabase(
            photo,
            'user-gallery', 
            f'users/{user_profile.id}/gallery'
        )
        
        entity_type = user_profile.user_role
        
        media_entry = Media.objects.create(
            uploader=user_profile,
            file_path=photo_url,
            file_type='image',
            entity_type=entity_type,
            entity_id=user_profile.id,
            is_official=False
        )
        
        # ✅ Invalidate gallery cache
        key = f"user_gallery:{user_id}"
        RedisCache.invalidate_user_profile(user_id)  # This will also clear gallery
        
        return Response({
            'message': 'Gallery photo uploaded successfully',
            'photo_url': photo_url,
            'photo_id': str(media_entry.id)
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Gallery upload error: {e}") 
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_gallery_photos(request):
    """Get gallery photos - WITH REDIS CACHE"""
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    user_id = str(user_profile.id)
    
    # ✅ Try cache first
    cached_gallery = RedisCache.get_user_gallery(user_id)
    if cached_gallery:
        logger.info(f"🚀 Serving gallery from cache for user {user_id}")
        return Response(cached_gallery)
    
    # ❌ Cache miss
    try:
        photos = Media.objects.filter(
            uploader=user_profile, 
            file_type='image'
        ).order_by('-created_at')
        
        photo_data = [{
            'id': str(photo.id),
            'url': photo.file_path,
            'created_at': photo.created_at.isoformat()
        } for photo in photos]
        
        # ✅ Cache the result
        RedisCache.set_user_gallery(user_id, photo_data)
        
        return Response(photo_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_gallery_photo(request, photo_id):
    """
    Delete a photo from public.media
    """
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    
    try:
        # Find photo and ensure it belongs to the requester
        photo = Media.objects.get(id=photo_id, uploader=user_profile)
        photo.delete()
        
        return Response({'message': 'Photo deleted successfully'}, status=status.HTTP_200_OK)
        
    except Media.DoesNotExist:
        return Response({'error': 'Photo not found or unauthorized'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_profile_bio(request):
    """Update user's bio - FIXED with proper Redis cache invalidation"""
    user_profile = request.user.user_profile if hasattr(request.user, 'user_profile') else request.user
    user_id = str(user_profile.id)
    
    bio = request.data.get('profile_bio')
    if bio is None:
        return Response({'error': 'profile_bio is required'}, status=400)
    
    try:
        user_profile.profile_bio = bio
        user_profile.save()
        
        # ✅ CRITICAL: Invalidate ALL user caches
        RedisCache.invalidate_all_user_data(user_id)
        
        logger.info(f"✅ Updated bio for user {user_id} and invalidated cache")
        
        return Response({
            'message': 'Bio updated successfully',
            'profile_bio': bio
        }, status=200)
        
    except Exception as e:
        logger.error(f"❌ Error updating bio: {e}")
        return Response({'error': str(e)}, status=400)

# ═══════════════════════════════════════════════════════════
# GUIDE PROFILE ENDPOINTS
# ═══════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_guide_profile(request):
    """Dedicated guide endpoint (uses same cache as /me)"""
    user_profile = (
        request.user.user_profile
        if hasattr(request.user, 'user_profile')
        else request.user
    )
    if user_profile.user_role != 'guide':
        return Response({'error': 'Not authorized'}, status=403)
    return get_current_user(request)


@api_view(['PATCH', 'PUT'])
@permission_classes([IsAuthenticated])
def update_guide_profile(request):
    """Update guide profile - FIXED with proper cache invalidation"""
    user_profile = (
        request.user.user_profile
        if hasattr(request.user, 'user_profile')
        else request.user
    )
    user_id = str(user_profile.id)
    
    if user_profile.user_role != 'guide':
        return Response({'error': 'Not authorized'}, status=403)

    try:
        guide = GuideProfile.objects.get(user_profile=user_profile)

        # Update user profile fields
        updated_fields = []
        for f in ['first_name', 'last_name', 'date_of_birth', 'gender', 'country', 'profile_bio']:
            if f in request.data:
                setattr(user_profile, f, request.data[f])
                updated_fields.append(f)

        if 'phone_number' in request.data:
            phone = request.data['phone_number']
            if phone and not phone.startswith('+'):
                return Response({'error': 'Phone must include country code'}, status=400)
            user_profile.phone_number = phone
            updated_fields.append('phone_number')

        if updated_fields:
            user_profile.save()
            logger.info(f"✅ Updated user profile fields: {updated_fields}")

        # Update guide-specific fields
        guide_updated = []
        for f in ['city_id', 'experience_years', 'education', 'rate_per_hour', 'is_available']:
            if f in request.data:
                setattr(guide, f, request.data[f])
                guide_updated.append(f)
        
        if guide_updated:
            guide.save()
            logger.info(f"✅ Updated guide profile fields: {guide_updated}")

        # ✅ CRITICAL: Invalidate ALL caches
        RedisCache.invalidate_all_user_data(user_id)
        logger.info(f"✅ Invalidated all cache for user {user_id}")
        
        # Recalculate avg_rating
        agg = Review.objects.filter(guide=guide).aggregate(avg=Avg('rating'))
        if agg['avg']:
            guide.avg_rating = round(agg['avg'], 1)
            guide.save(update_fields=['avg_rating'])
        
        # Build fresh data and cache it
        data = CompleteGuideProfileSerializer(guide).data
        RedisCache.set_user_profile(user_id, data)
        logger.info(f"✅ Cached fresh profile data for {user_id}")

        return Response({
            'message': 'Profile updated successfully',
            'data': data
        })

    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide profile not found'}, status=404)
    except Exception as e:
        logger.error(f"❌ Error updating profile: {e}")
        return Response({'error': str(e)}, status=400)


# ═══════════════════════════════════════════════════════════
# AVAILABILITY ENDPOINTS
# ═══════════════════════════════════════════════════════════

AVAILABILITY_CACHE_KEY = "guide_availability:{user_id}"
AVAILABILITY_CACHE_TTL = 600  # 10 minutes




def generate_hourly_slots(start_time_str, end_time_str):
    """
    Split time range into 1-hour slots
    Example: '09:00' to '11:00' → ['09:00-10:00', '10:00-11:00']
    """
    start = datetime.strptime(start_time_str, '%H:%M').time()
    end = datetime.strptime(end_time_str, '%H:%M').time()
    
    slots = []
    current = datetime.combine(date.today(), start)
    end_dt = datetime.combine(date.today(), end)
    
    while current < end_dt:
        slot_start = current.time()
        current += timedelta(hours=1)
        slot_end = min(current.time(), end)
        
        slots.append({
            'start_time': slot_start.strftime('%H:%M:%S'),
            'end_time': slot_end.strftime('%H:%M:%S')
        })
        
        if current.time() >= end:
            break
    
    return slots


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_guide_availability(request):
    """Get all future availability - cached with Redis"""
    user_profile = (
        request.user.user_profile
        if hasattr(request.user, 'user_profile')
        else request.user
    )
    user_id = str(user_profile.id)
    
    if user_profile.user_role != 'guide':
        return Response({'error': 'Not authorized'}, status=403)

    # Try Redis cache
    cache_key = AVAILABILITY_CACHE_KEY.format(user_id=user_id)
    cached = cache.get(cache_key)
    if cached:
        logger.info(f"🚀 Availability CACHE HIT {user_id}")
        return Response(json.loads(cached))

    try:
        guide = GuideProfile.objects.get(user_profile=user_profile)
        slots = GuideAvailability.objects.filter(
            guide_profile=guide,
            date__gte=date.today()
        ).order_by('date', 'start_time')
        
        data = GuideAvailabilitySerializer(slots, many=True).data
        
        # Cache for 10 minutes
        cache.set(cache_key, json.dumps(list(data)), timeout=AVAILABILITY_CACHE_TTL)
        logger.info(f"✅ Cached {len(data)} availability slots for {user_id}")
        
        return Response(data)
        
    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide profile not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_guide_availability(request):
    """
    Add availability with 1-hour slot splitting
    
    Process:
    1. Save pattern to guide_availability_pattern
    2. Generate hourly slots for each date
    3. Save all slots to guide_availability
    4. Invalidate Redis cache
    
    Single day:  {"date": "2026-02-20", "start_time": "09:00", "end_time": "17:00"}
    Date range:  {"start_date": "2026-02-20", "end_date": "2026-02-25", "start_time": "09:00", "end_time": "17:00"}
    """
    user_profile = (
        request.user.user_profile
        if hasattr(request.user, 'user_profile')
        else request.user
    )
    user_id = str(user_profile.id)
    
    if user_profile.user_role != 'guide':
        return Response({'error': 'Not authorized'}, status=403)

    start_time_input = request.data.get('start_time')  # e.g., "09:00"
    end_time_input   = request.data.get('end_time')    # e.g., "11:00"
    
    if not start_time_input or not end_time_input:
        return Response({'error': 'start_time and end_time required'}, status=400)

    # Parse time strings
    try:
        # Ensure HH:MM format
        if len(start_time_input) == 5:  # "09:00"
            start_time_input += ":00"   # "09:00:00"
        if len(end_time_input) == 5:
            end_time_input += ":00"
    except:
        pass

    # Build list of dates
    if 'date' in request.data:
        dates = [request.data['date']]
        active_from = request.data['date']
        active_until = request.data['date']
    elif 'start_date' in request.data and 'end_date' in request.data:
        try:
            start_d = datetime.strptime(request.data['start_date'], '%Y-%m-%d').date()
            end_d   = datetime.strptime(request.data['end_date'], '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Use YYYY-MM-DD format'}, status=400)
        
        if end_d < start_d:
            return Response({'error': 'end_date must be >= start_date'}, status=400)
        if (end_d - start_d).days > 90:
            return Response({'error': 'Range cannot exceed 90 days'}, status=400)
        
        dates = [(start_d + timedelta(days=i)).strftime('%Y-%m-%d')
                 for i in range((end_d - start_d).days + 1)]
        active_from = request.data['start_date']
        active_until = request.data['end_date']
    else:
        return Response({'error': 'Provide "date" or "start_date"+"end_date"'}, status=400)

    try:
        guide = GuideProfile.objects.get(user_profile=user_profile)
        
        # Generate hourly slots from time range
        hourly_slots = generate_hourly_slots(
            start_time_input.split(':')[0] + ':' + start_time_input.split(':')[1],
            end_time_input.split(':')[0] + ':' + end_time_input.split(':')[1]
        )
        
        if not hourly_slots:
            return Response({'error': 'Invalid time range'}, status=400)
        
        with transaction.atomic():
            # 1. Save to guide_availability_pattern
            pattern = GuideAvailabilityPattern.objects.create(
                guide_profile=guide,
                reccuring_type='daily',
                start_time=start_time_input,
                end_time=end_time_input,
                active_from=active_from,
                active_until=active_until
            )
            
            logger.info(f"✅ Created pattern {pattern.id}: {active_from} to {active_until}, {start_time_input}-{end_time_input}")
            
            # 2. Create hourly slots for each date
            created_slots = []
            skipped_dates = []
            
            for date_str in dates:
                # Skip past dates
                if datetime.strptime(date_str, '%Y-%m-%d').date() < date.today():
                    skipped_dates.append(date_str)
                    continue
                
                # Create one slot per hour
                for slot in hourly_slots:
                    # Check if this exact slot already exists
                    existing = GuideAvailability.objects.filter(
                        guide_profile=guide,
                        date=date_str,
                        start_time=slot['start_time']
                    ).exists()
                    
                    if existing:
                        continue  # Skip duplicate hourly slot
                    
                    availability_slot = GuideAvailability.objects.create(
                        guide_profile=guide,
                        date=date_str,
                        start_time=slot['start_time'],
                        end_time=slot['end_time'],
                        is_booked=False
                    )
                    created_slots.append(availability_slot)
            
            logger.info(f"✅ Created {len(created_slots)} hourly slots across {len(dates)} dates")
        
        # 3. Invalidate caches
        cache.delete(AVAILABILITY_CACHE_KEY.format(user_id=user_id))
        RedisCache.invalidate_user_profile(user_id)
        
        return Response({
            'message': f'Created {len(created_slots)} hourly slots across {len([d for d in dates if d not in skipped_dates])} days',
            'pattern_id': str(pattern.id),
            'hourly_slots_per_day': len(hourly_slots),
            'total_slots_created': len(created_slots),
            'dates_processed': len(dates) - len(skipped_dates),
            'skipped_dates': skipped_dates,
            'created_slots': GuideAvailabilitySerializer(created_slots[:10], many=True).data  # Show first 10
        }, status=201)

    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide profile not found'}, status=404)
    except Exception as e:
        logger.error(f"❌ Error creating availability: {e}")
        return Response({'error': str(e)}, status=400)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_guide_availability(request, slot_id):
    """Delete availability slot (can't delete if booked)"""
    user_profile = (
        request.user.user_profile
        if hasattr(request.user, 'user_profile')
        else request.user
    )
    user_id = str(user_profile.id)
    
    if user_profile.user_role != 'guide':
        return Response({'error': 'Not authorized'}, status=403)

    try:
        guide = GuideProfile.objects.get(user_profile=user_profile)
        slot  = GuideAvailability.objects.get(id=slot_id, guide_profile=guide)
        
        if slot.is_booked:
            return Response({'error': 'Cannot delete booked slot'}, status=400)
        
        slot.delete()
        
        # Invalidate caches
        cache.delete(AVAILABILITY_CACHE_KEY.format(user_id=user_id))
        RedisCache.invalidate_user_profile(user_id)
        
        logger.info(f"✅ Deleted availability slot {slot_id}")
        
        return Response({'message': 'Slot deleted'})
        
    except GuideAvailability.DoesNotExist:
        return Response({'error': 'Slot not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_guide_is_available(request):
    """Toggle guide's global is_available flag"""
    user_profile = (
        request.user.user_profile
        if hasattr(request.user, 'user_profile')
        else request.user
    )
    user_id = str(user_profile.id)
    
    if user_profile.user_role != 'guide':
        return Response({'error': 'Not authorized'}, status=403)
    
    try:
        guide = GuideProfile.objects.get(user_profile=user_profile)
        guide.is_available = not guide.is_available
        guide.save(update_fields=['is_available'])
        
        RedisCache.invalidate_all_user_data(user_id)
        
        return Response({'is_available': guide.is_available})
        
    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide profile not found'}, status=404)


# ═══════════════════════════════════════════════════════════
# REVIEWS ENDPOINT
# ═══════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_guide_reviews(request):
    """Get guide reviews - cached via user_stats"""
    user_profile = (
        request.user.user_profile
        if hasattr(request.user, 'user_profile')
        else request.user
    )
    user_id = str(user_profile.id)
    
    if user_profile.user_role != 'guide':
        return Response({'error': 'Not authorized'}, status=403)

    cached = RedisCache.get_user_stats(user_id)
    if cached and 'reviews' in cached:
        logger.info(f"🚀 Reviews CACHE HIT {user_id}")
        return Response(cached)

    try:
        guide   = GuideProfile.objects.get(user_profile=user_profile)
        reviews = Review.objects.filter(guide=guide).order_by('-created_at')
        
        data = {
            'avg_rating':    float(guide.avg_rating or 0),
            'total_reviews': reviews.count(),
            'reviews':       ReviewSerializer(reviews, many=True).data,
        }
        
        RedisCache.set_user_stats(user_id, data)
        return Response(data)
        
    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide profile not found'}, status=404)


# Add these new endpoints to your accounts/views.py

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_guide_language(request):
    """Add a language to guide profile"""
    user_profile = (
        request.user.user_profile
        if hasattr(request.user, 'user_profile')
        else request.user
    )
    user_id = str(user_profile.id)
    
    if user_profile.user_role != 'guide':
        return Response({'error': 'Not authorized'}, status=403)
    
    language_id = request.data.get('language_id')
    proficiency = request.data.get('proficiency', 'native')
    
    if not language_id:
        return Response({'error': 'language_id is required'}, status=400)
    
    # Validate proficiency enum
    valid_proficiencies = ['basic', 'conversational', 'native']
    if proficiency not in valid_proficiencies:
        return Response({
            'error': f'Invalid proficiency. Must be one of: {", ".join(valid_proficiencies)}'
        }, status=400)
    
    try:
        # Check if language exists
        language = Language.objects.get(id=language_id)
        
        # Check if already added
        existing = UserLanguage.objects.filter(
            user_profile=user_profile,
            language=language
        ).first()
        
        if existing:
            return Response({'error': 'Language already added'}, status=400)
        
        # Create new user language
        user_lang = UserLanguage.objects.create(
            user_profile=user_profile,
            language=language,
            proficiency=proficiency,
            is_native=(proficiency == 'native')
        )
        
        # Invalidate caches
        RedisCache.invalidate_all_user_data(user_id)
        
        logger.info(f"✅ Added language {language.name} ({proficiency}) for user {user_id}")
        
        return Response({
            'message': 'Language added successfully',
            'language': {
                'id': str(user_lang.id),
                'language_id': str(language.id),
                'name': language.name,
                'code': language.code,
                'proficiency': proficiency,
                'is_native': proficiency == 'native'
            }
        }, status=201)
        
    except Language.DoesNotExist:
        return Response({'error': 'Language not found'}, status=404)
    except Exception as e:
        logger.error(f"❌ Error adding language: {e}")
        return Response({'error': str(e)}, status=400)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_guide_language(request, language_id):
    """Update proficiency level for a language"""
    user_profile = (
        request.user.user_profile
        if hasattr(request.user, 'user_profile')
        else request.user
    )
    user_id = str(user_profile.id)
    
    if user_profile.user_role != 'guide':
        return Response({'error': 'Not authorized'}, status=403)
    
    proficiency = request.data.get('proficiency')
    
    if not proficiency:
        return Response({'error': 'proficiency is required'}, status=400)
    
    # Validate proficiency enum
    valid_proficiencies = ['basic', 'conversational', 'native']
    if proficiency not in valid_proficiencies:
        return Response({
            'error': f'Invalid proficiency. Must be one of: {", ".join(valid_proficiencies)}'
        }, status=400)
    
    try:
        # Find the user language entry
        user_lang = UserLanguage.objects.get(
            id=language_id,
            user_profile=user_profile
        )
        
        # Update proficiency
        user_lang.proficiency = proficiency
        user_lang.is_native = (proficiency == 'native')
        user_lang.save()
        
        # Invalidate caches
        RedisCache.invalidate_all_user_data(user_id)
        
        logger.info(f"✅ Updated language proficiency to {proficiency} for user {user_id}")
        
        return Response({
            'message': 'Proficiency updated successfully',
            'language': {
                'id': str(user_lang.id),
                'language_id': str(user_lang.language.id),
                'name': user_lang.language.name,
                'code': user_lang.language.code,
                'proficiency': proficiency,
                'is_native': proficiency == 'native'
            }
        })
        
    except UserLanguage.DoesNotExist:
        return Response({'error': 'Language not found'}, status=404)
    except Exception as e:
        logger.error(f"❌ Error updating language: {e}")
        return Response({'error': str(e)}, status=400)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_guide_language(request, language_id):
    """Remove a language from guide profile"""
    user_profile = (
        request.user.user_profile
        if hasattr(request.user, 'user_profile')
        else request.user
    )
    user_id = str(user_profile.id)
    
    if user_profile.user_role != 'guide':
        return Response({'error': 'Not authorized'}, status=403)
    
    try:
        # Find and delete the user language entry
        user_lang = UserLanguage.objects.get(
            id=language_id,
            user_profile=user_profile
        )
        
        language_name = user_lang.language.name
        user_lang.delete()
        
        # Invalidate caches
        RedisCache.invalidate_all_user_data(user_id)
        
        logger.info(f"✅ Removed language {language_name} for user {user_id}")
        
        return Response({'message': 'Language removed successfully'})
        
    except UserLanguage.DoesNotExist:
        return Response({'error': 'Language not found'}, status=404)
    except Exception as e:
        logger.error(f"❌ Error removing language: {e}")
        return Response({'error': str(e)}, status=400)


# ══════════════════════════════════════════════════════════
# HOST PROFILE ENDPOINTS
# ══════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_host_profile(request):
    """Get complete host profile"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        # Check cache
        cache_key = f"host_profile:{user_profile.id}"
        cached = safe_cache_get(cache_key)
        if cached:
            return Response(cached)
        
        # Build response
        data = {
            'id': str(host.id),
            'user_profile_id': str(user_profile.id),
            'first_name': user_profile.first_name or '',
            'last_name': user_profile.last_name or '',
            'full_name': f"{user_profile.first_name or ''} {user_profile.last_name or ''}".strip(),
            'phone_number': user_profile.phone_number or '',
            'date_of_birth': str(user_profile.date_of_birth) if user_profile.date_of_birth else '',
            'gender': user_profile.gender or '',
            'country': user_profile.country or '',
            'profile_pic': user_profile.profile_pic or '',
            'profile_bio': user_profile.profile_bio or '',
            'verification_status': host.verification_status,
            'is_verified': host.verification_status == 'verified',
            'no_of_stays_owned': host.no_of_stays_owned,
            'total_completed_bookings': host.total_completed_bookings or 0,
            'total_cancelled_bookings': host.total_cancelled_bookings or 0,
            'total_rejected_bookings': host.total_rejected_bookings or 0,
            'response_rate': float(host.response_rate or 0),
            'avg_rating': float(host.avg_rating or 0),
            'total_earned': float(host.total_earned or 0),
            'total_tip_earned': float(host.total_tip_earned or 0),
            'member_since': host.created_at.strftime('%B %Y'),
        }
        
        # Languages
        languages = UserLanguage.objects.filter(
            user_profile=user_profile
        ).select_related('language')
        data['languages'] = [{
            'id': str(ul.id),
            'language_id': str(ul.language.id),
            'name': ul.language.name,
            'code': ul.language.code,
            'proficiency': ul.proficiency,
            'is_native': ul.is_native
        } for ul in languages]
        
        # Cache
        safe_cache_set(cache_key, data, timeout=600)
        return Response(data)
        
    except Exception as e:
        logger.error(f'❌ get_host_profile: {e}', exc_info=True)
        return Response({'error': str(e)}, status=500)

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_host_profile(request):
    """Update host profile"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        # Update fields
        for field in ['first_name', 'last_name', 'date_of_birth', 
                      'gender', 'country', 'address', 'profile_bio']:
            if field in request.data:
                setattr(user_profile, field, request.data[field])
        
        if 'phone_number' in request.data:
            phone = request.data['phone_number']
            if phone and not phone.startswith('+'):
                return Response(
                    {'error': 'Phone must include country code'},
                    status=400
                )
            user_profile.phone_number = phone
        
        user_profile.save()
        
        # Clear cache
        safe_cache_delete(f"host_profile:{user_profile.id}")
        safe_cache_delete(f"host_dashboard:{user_profile.id}")
        
        return Response({'message': 'Profile updated successfully'})
        
    except Exception as e:
        logger.error(f'❌ update_host_profile: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def update_profile_picture(request):
    """Update profile picture"""
    try:
        user_profile = _get_user_profile(request)
        
        if 'profile_pic' not in request.FILES:
            return Response({'error': 'No photo provided'}, status=400)
        
        photo = request.FILES['profile_pic']
        
        # Upload to Supabase
        url = upload_file_to_supabase(
            photo, 
            'profile-pictures',
            f'users/{user_profile.id}'
        )
        
        user_profile.profile_pic = url
        user_profile.save()
        
        # Clear cache
        safe_cache_delete(f"host_profile:{user_profile.id}")
        
        return Response({
            'message': 'Profile picture updated',
            'profile_pic': url
        })
        
    except Exception as e:
        logger.error(f'❌ update_profile_picture: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)

# ══════════════════════════════════════════════════════════
# HOST DASHBOARD
# ══════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_host_dashboard(request):
    """Get complete host dashboard"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        # Check cache
        cache_key = f"host_dashboard:{user_profile.id}"
        cached = safe_cache_get(cache_key)
        if cached:
            return Response(cached)
        
        # Get all stays with prefetch
        stays = Stay.objects.filter(host=host).prefetch_related(
            'stay_facilities__facility'
        )
        
        stays_data = []
        total_bookings_all_stays = 0
        total_earnings_all_stays = 0
        
        for stay in stays:
            cover = Media.objects.filter(
                entity_type='stay',
                entity_id=stay.id,
                file_type='image'
            ).order_by('order_index').first()

            reviews = Review.objects.filter(stay=stay)
            avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0

            stay_bookings_count = 0   # ✅ renamed to avoid conflict
            stay_total_earned = 0.0   # ✅ renamed to avoid conflict

            stays_data.append({
                'id': str(stay.id),
                'name': stay.name or 'Unnamed Stay',
                'type': stay.type or '',
                'cover_photo': cover.file_path if cover else None,
                'city_name': '',
                'verification_status': stay.verification_status,
                'is_active': stay.is_active,
                'room_count': stay.room_count or 0,
                'max_guests': stay.max_guests or 0,
                'price_per_night': float(stay.price_per_night),
                'avg_rating': round(float(avg_rating), 1),
                'review_count': reviews.count(),
                'bookings_count': stay_bookings_count,
                'total_earned': stay_total_earned,
            })

            total_bookings_all_stays += stay_bookings_count   # ✅ uses renamed var
            total_earnings_all_stays += stay_total_earned     # ✅ uses renamed var
        
        # Get recent bookings (mock for now)
        # TODO: Add stay_id to booking table
        recent_bookings = []
        upcoming_bookings = []
        
        # Get unread notifications count
        # TODO: Implement notification system
        unread_notifications = 0
        
        # Build response
        data = {
            'host_id': str(host.id),
            'host_name': f"{user_profile.first_name} {user_profile.last_name}".strip(),
            'profile_pic': user_profile.profile_pic,
            'verification_status': host.verification_status,
            'avg_rating': float(host.avg_rating or 0),
            'total_stays': stays.count(),
            'active_stays': stays.filter(
                is_active=True, 
                verification_status='verified'
            ).count(),
            'pending_stays': stays.filter(verification_status='pending').count(),
            'total_earned': total_earnings_all_stays,
            'total_bookings': total_bookings_all_stays,
            'stays': stays_data,
            'booking_requests': recent_bookings,
            'upcoming_bookings': upcoming_bookings,
            'unread_notifications': unread_notifications,
        }
        
        # Cache
        safe_cache_set(cache_key, data, timeout=300)
        return Response(data)
        
    except Exception as e:
        logger.error(f'❌ get_host_dashboard: {e}', exc_info=True)
        return Response({'error': str(e)}, status=500)



# ══════════════════════════════════════════════════════════
# STAYS MANAGEMENT
# ══════════════════════════════════════════════════════════

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def create_stay(request):
    """Create new stay"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        with transaction.atomic():
            # Create stay
            stay = Stay.objects.create(
                host=host,
                name=request.data.get('name'),
                type=request.data.get('type'),
                description=request.data.get('description', ''),
                house_no=request.data.get('house_no', ''),
                street=request.data.get('street', ''),
                town=request.data.get('town', ''),
                city_id=request.data.get('city_id'),
                postal_code=request.data.get('postal_code'),
                latitude=request.data.get('latitude'),
                longitude=request.data.get('longitude'),
                room_count=int(request.data.get('room_count', 1)),
                max_guests=int(request.data.get('max_guests', 2)),
                price_per_night=float(request.data.get('price_per_night', 0)),
                price_entire_place=float(request.data.get('price_entire_place', 0)),
                entire_place_is_available=request.data.get('entire_place_is_available', 'false').lower() == 'true',
                price_per_extra_guest=float(request.data.get('price_per_extra_guest', 0)),
                bathroom_count=int(request.data.get('bathroom_count', 1)),
                shared_bathrooms=request.data.get('shared_bathrooms', 'false').lower() == 'true',
                price_per_halfday=float(request.data.get('price_per_halfday', 0)),
                halfday_available=request.data.get('halfday_available', 'false').lower() == 'true',
                verification_status='pending',
                is_active=False
            )
            
            # Upload photos
            photos = request.FILES.getlist('photos') or request.FILES.getlist('photos[]')
            for idx, photo in enumerate(photos):
                url = upload_file_to_supabase(
                    photo, 
                    'stay-images',
                    f'stays/{stay.id}'
                )
                Media.objects.create(
                    uploader=user_profile,
                    entity_type='stay',
                    entity_id=stay.id,
                    file_path=url,
                    file_type='image',
                    is_official=False,
                    order_index=idx
                )
            
            # Upload documents
            docs = request.FILES.getlist('documents') or request.FILES.getlist('documents[]')
            for doc in docs:
                url = upload_file_to_supabase(
                    doc,
                    'stay-documents',
                    f'stays/{stay.id}/docs'
                )
                Media.objects.create(
                    uploader=user_profile,
                    entity_type='stay',
                    entity_id=stay.id,
                    file_path=url,
                    file_type='document',
                    is_official=True,
                    order_index=0
                )
            
            # Add facilities
            facility_ids = request.data.getlist('facility_ids') or request.data.getlist('facility_ids[]') or []
            for fid in facility_ids:
                try:
                    facility = Facilities.objects.get(id=fid, is_active=True)
                    StayFacility.objects.create(stay=stay, facility=facility)
                except Facilities.DoesNotExist:
                    continue
            
            # Clear cache
            safe_cache_delete(f"host_dashboard:{user_profile.id}")
            safe_cache_delete(f"host_profile:{user_profile.id}")
            
            return Response({
                'message': 'Stay created successfully',
                'stay_id': str(stay.id),
                'verification_status': stay.verification_status
            }, status=201)
        
    except Exception as e:
        logger.error(f'❌ create_stay: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_stay_detail(request, stay_id):
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err

        # ✅ FIX: Remove prefetch_related with invalid 'media_set'
        stay = Stay.objects.prefetch_related(
            'stay_facilities__facility'
        ).get(id=stay_id, host=host)

        # ✅ FIX: Query Media directly using entity_id
        photos = Media.objects.filter(
            entity_type='stay',
            entity_id=stay.id,
            file_type='image'
        ).order_by('order_index')

        docs = StayDocument.objects.filter(stay=stay)
        docs_data = [{
            'id': str(d.id),
            'url': d.document_url,
            'document_type': d.document_type,
            'verification_status': d.verification_status
        } for d in docs]

        photos_data = [{'id': str(p.id), 'url': p.file_path, 'order': p.order_index} for p in photos]

        # Facilities
        facilities = [str(sf.facility.id) for sf in stay.stay_facilities.all()]

        # Availability (next 60 days)
        today = date.today()
        availability = StayAvailability.objects.filter(
            stay=stay,
            date__gte=today,
            date__lte=today + timedelta(days=60)
        ).order_by('date')

        avail_data = [{
            'id': str(a.id),
            'date': str(a.date),
            'total_room': a.total_room,
            'occupied_room': a.occupied_room,
            'is_available': a.is_available
        } for a in availability]

        # Reviews
        reviews = Review.objects.filter(stay=stay).select_related(
            'tourist__user_profile'
        ).order_by('-created_at')[:10]

        reviews_data = [{
            'id': str(r.id),
            'tourist_name': r.tourist.user_profile.full_name,
            'tourist_photo': r.tourist.user_profile.profile_pic,
            'rating': float(r.rating),
            'review': r.review,
            'created_at': r.created_at.isoformat()
        } for r in reviews]

        avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0

        data = {
            'id': str(stay.id),
            'name': stay.name,
            'type': stay.type,
            'description': stay.description,
            'house_no': stay.house_no,
            'street': stay.street,
            'town': stay.town,
            'city_id': str(stay.city_id) if stay.city_id else None,
            'city_name': '',
            'postal_code': stay.postal_code,
            'latitude': stay.latitude,
            'longitude': stay.longitude,
            'room_count': stay.room_count,
            'room_available': stay.room_available,
            'max_guests': stay.max_guests,
            'price_per_night': float(stay.price_per_night),
            'price_entire_place': float(stay.price_entire_place),
            'entire_place_is_available': stay.entire_place_is_available,
            'price_per_extra_guest': float(stay.price_per_extra_guest),
            'bathroom_count': stay.bathroom_count,
            'shared_bathrooms': stay.shared_bathrooms,
            'price_per_halfday': float(stay.price_per_halfday),
            'halfday_available': stay.halfday_available,
            'standard_checkin_time': str(stay.standard_checkin_time),
            'standard_checkout_time': str(stay.standard_checkout_time),
            'standard_halfday_checkout': str(stay.standard_halfday_checkout),
            'is_active': stay.is_active,
            'verification_status': stay.verification_status,
            'photos': photos_data,
            'documents': docs_data,
            'facility_ids': facilities,
            'facilities': [],  # full facility objects if needed
            'availability': avail_data,
            'reviews': reviews_data,
            'avg_rating': round(float(avg_rating), 1),
            'review_count': len(reviews_data),
            'cover_photo': photos_data[0]['url'] if photos_data else None,
            'created_at': stay.created_at.isoformat(),
            'updated_at': stay.updated_at.isoformat(),
        }

        return Response(data)

    except Stay.DoesNotExist:
        return Response({'error': 'Stay not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ get_stay_detail: {e}', exc_info=True)
        return Response({'error': str(e)}, status=500)

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_stay(request, stay_id):
    """Update stay details"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        stay = Stay.objects.get(id=stay_id, host=host)
        
        # Update fields
        updatable = [
            'name', 'type', 'description', 'house_no', 'street', 'town',
            'city_id', 'postal_code', 'latitude', 'longitude', 'room_count',
            'room_available', 'max_guests', 'price_per_night', 'price_entire_place',
            'entire_place_is_available', 'price_per_extra_guest', 'bathroom_count',
            'shared_bathrooms', 'price_per_halfday', 'halfday_available',
            'standard_checkin_time', 'standard_checkout_time', 'standard_halfday_checkout'
        ]
        
        for field in updatable:
            if field in request.data:
                value = request.data[field]
                # Handle boolean fields
                if field in ['entire_place_is_available', 'halfday_available', 
                            'shared_bathrooms', 'room_available']:
                    if isinstance(value, str):
                        value = value.lower() == 'true'
                setattr(stay, field, value)
        
        stay.save()
        
        # Clear cache
        safe_cache_delete(f"host_dashboard:{user_profile.id}")
        
        return Response({'message': 'Stay updated successfully'})
        
    except Stay.DoesNotExist:
        return Response({'error': 'Stay not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ update_stay: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_stay_active(request, stay_id):
    """Toggle stay active status - ✅ Safe Redis"""
    try:
        user_profile = _resolve_user_profile(request)
        if user_profile.user_role != 'host':
            return Response({'error': 'Not authorized'}, status=403)

        user_id = str(user_profile.id)
        host, err = _get_host_profile(user_profile)
        if err:
            return err

        stay = Stay.objects.get(id=stay_id, host=host)
        
        if stay.verification_status != 'verified':
            return Response({
                'error': 'Can only activate verified stays'
            }, status=400)

        stay.is_active = not stay.is_active
        stay.save(update_fields=['is_active'])

        # ✅ Safe cache invalidation
        safe_cache_delete(f"host_stays:{user_id}")
        safe_cache_delete(f"host_profile:{user_id}")
        safe_cache_delete(f"host_dashboard:{user_id}")

        return Response({
            'message': f"Stay {'activated' if stay.is_active else 'deactivated'}",
            'is_active': stay.is_active
        })

    except Stay.DoesNotExist:
        return Response({'error': 'Stay not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ toggle_stay_active: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_stay(request, stay_id):
    """Delete stay - ✅ Safe Redis"""
    try:
        user_profile = _resolve_user_profile(request)
        if user_profile.user_role != 'host':
            return Response({'error': 'Not authorized'}, status=403)

        user_id = str(user_profile.id)
        host, err = _get_host_profile(user_profile)
        if err:
            return err

        stay = Stay.objects.get(id=stay_id, host=host)
        
        # Check if has bookings (TODO: wire to booking model when ready)
        # if stay.bookings.exists():
        #     return Response({'error': 'Cannot delete stay with bookings'}, status=400)

        stay.delete()
        
        # Update host count
        host.no_of_stays_owned = Stay.objects.filter(host=host).count()
        host.save(update_fields=['no_of_stays_owned'])

        # ✅ Safe cache invalidation
        safe_cache_delete(f"host_stays:{user_id}")
        safe_cache_delete(f"host_profile:{user_id}")
        safe_cache_delete(f"host_dashboard:{user_id}")

        return Response({'message': 'Stay deleted successfully'})

    except Stay.DoesNotExist:
        return Response({'error': 'Stay not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ delete_stay: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def add_stay_photo(request, stay_id):
    """Add photos to stay - ✅ Safe Redis"""
    try:
        user_profile = _resolve_user_profile(request)
        if user_profile.user_role != 'host':
            return Response({'error': 'Not authorized'}, status=403)

        user_id = str(user_profile.id)
        host, err = _get_host_profile(user_profile)
        if err:
            return err

        stay = Stay.objects.get(id=stay_id, host=host)
        photos = request.FILES.getlist('photos') or request.FILES.getlist('photos[]')
        
        if not photos:
            return Response({'error': 'No photos provided'}, status=400)

        max_pos = StayPic.objects.filter(stay=stay).count()
        created = []

        for idx, photo in enumerate(photos):
            url = upload_file_to_supabase(
                photo, 'stay-images',
                f'stays/{stay.id}/gallery/{photo.name}'
            )
            sp = StayPic.objects.create(
                stay=stay,
                photo_url=url,
                position=max_pos + idx,
                is_cover=(max_pos == 0 and idx == 0),
            )
            created.append(StayPicSerializer(sp).data)

        # ✅ Safe cache invalidation
        safe_cache_delete(f"host_stays:{user_id}")
        safe_cache_delete(f"host_profile:{user_id}")
        safe_cache_delete(f"host_dashboard:{user_id}")

        return Response({
            'message': f'{len(created)} photo(s) added',
            'photos': created
        }, status=201)

    except Stay.DoesNotExist:
        return Response({'error': 'Stay not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ add_stay_photo: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_stay_photo(request, stay_id, photo_id):
    """Delete stay photo - ✅ Safe Redis"""
    try:
        user_profile = _resolve_user_profile(request)
        if user_profile.user_role != 'host':
            return Response({'error': 'Not authorized'}, status=403)

        user_id = str(user_profile.id)
        host, err = _get_host_profile(user_profile)
        if err:
            return err

        stay = Stay.objects.get(id=stay_id, host=host)
        photo = StayPic.objects.get(id=photo_id, stay=stay)
        photo.delete()

        # ✅ Safe cache invalidation
        safe_cache_delete(f"host_stays:{user_id}")
        safe_cache_delete(f"host_profile:{user_id}")
        safe_cache_delete(f"host_dashboard:{user_id}")

        return Response({'message': 'Photo deleted'})

    except StayPic.DoesNotExist:
        return Response({'error': 'Photo not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_cover_photo(request, stay_id, photo_id):
    """Set cover photo - ✅ Safe Redis"""
    try:
        user_profile = _resolve_user_profile(request)
        if user_profile.user_role != 'host':
            return Response({'error': 'Not authorized'}, status=403)

        user_id = str(user_profile.id)
        host, err = _get_host_profile(user_profile)
        if err:
            return err

        stay = Stay.objects.get(id=stay_id, host=host)
        
        # Remove existing cover
        StayPic.objects.filter(stay=stay, is_cover=True).update(is_cover=False)
        
        # Set new cover
        photo = StayPic.objects.get(id=photo_id, stay=stay)
        photo.is_cover = True
        photo.save(update_fields=['is_cover'])

        # ✅ Safe cache invalidation
        safe_cache_delete(f"host_stays:{user_id}")
        safe_cache_delete(f"host_profile:{user_id}")
        safe_cache_delete(f"host_dashboard:{user_id}")

        return Response({'message': 'Cover photo updated'})

    except (Stay.DoesNotExist, StayPic.DoesNotExist):
        return Response({'error': 'Not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

# ══════════════════════════════════════════════════════════
# FACILITIES MANAGEMENT
# ══════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_facilities(request):
    """Get all available facilities"""
    cache_key = 'all_facilities'
    cached = safe_cache_get(cache_key)
    if cached:
        return Response(cached)
    
    try:
        facilities = Facilities.objects.filter(is_active=True).order_by('name')
        data = [{
            'id': str(f.id),
            'name': f.name,
            'description': f.description,
            'addon_price': float(f.addon_price) if f.addon_price else 0
        } for f in facilities]
        
        safe_cache_set(cache_key, data, timeout=3600)
        return Response(data)
        
    except Exception as e:
        logger.error(f'❌ get_all_facilities: {e}', exc_info=True)
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_stay_facilities(request, stay_id):
    """Update stay facilities with special notes"""
    try:
        user_profile = _resolve_user_profile(request)
        if user_profile.user_role != 'host':
            return Response({'error': 'Not authorized'}, status=403)

        user_id = str(user_profile.id)
        host, err = _get_host_profile(user_profile)
        if err:
            return err

        stay = Stay.objects.get(id=stay_id, host=host)
        
        # Expect: {"facilities": [{"facility_id": "uuid", "special_note": "optional"}]}
        facilities_data = request.data.get('facilities', [])
        
        # OR simple format: {"facility_ids": ["uuid1", "uuid2"]}
        facility_ids = request.data.get('facility_ids')
        
        with transaction.atomic():
            # Clear existing
            StayFacility.objects.filter(stay=stay).delete()
            
            if facility_ids:
                # Simple format (no special notes)
                for fid in facility_ids:
                    try:
                        f = Facilities.objects.get(id=fid, is_active=True)
                        StayFacility.objects.create(
                            stay=stay, 
                            facility=f,
                            special_note=None
                        )
                    except Facilities.DoesNotExist:
                        continue
            elif facilities_data:
                # Complex format (with special notes)
                for item in facilities_data:
                    fid = item.get('facility_id')
                    note = item.get('special_note', '')
                    try:
                        f = Facilities.objects.get(id=fid, is_active=True)
                        StayFacility.objects.create(
                            stay=stay,
                            facility=f,
                            special_note=note if note else None
                        )
                    except Facilities.DoesNotExist:
                        continue

        # Clear cache
        safe_cache_delete(f"host_stays:{user_id}")
        safe_cache_delete(f"host_dashboard:{user_id}")

        return Response({'message': 'Facilities updated successfully'})

    except Stay.DoesNotExist:
        return Response({'error': 'Stay not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ update_stay_facilities: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)


# ══════════════════════════════════════════════════════════
# AVAILABILITY MANAGEMENT
# ══════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_stay_availability(request, stay_id):
    """Get stay availability calendar"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        stay = Stay.objects.get(id=stay_id, host=host)
        
        # Get date range (default 90 days)
        today = date.today()
        end_date = today + timedelta(days=90)
        
        availability = StayAvailability.objects.filter(
            stay=stay,
            date__gte=today,
            date__lte=end_date
        ).order_by('date')
        
        data = [{
            'id': str(a.id),
            'date': str(a.date),
            'total_room': a.total_room,
            'occupied_room': a.occupied_room,
            'is_available': a.is_available
        } for a in availability]
        
        return Response(data)
        
    except Stay.DoesNotExist:
        return Response({'error': 'Stay not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ get_stay_availability: {e}', exc_info=True)
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_stay_availability(request, stay_id):
    """Set availability for date range"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        stay = Stay.objects.get(id=stay_id, host=host)
        
        # Parse request
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        total_room = int(request.data.get('total_room', 1))
        is_available = request.data.get('is_available', True)
        
        if isinstance(is_available, str):
            is_available = is_available.lower() == 'true'
        
        if not start_date or not end_date:
            return Response({
                'error': 'start_date and end_date required'
            }, status=400)
        
        try:
            start_d = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_d = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({
                'error': 'Use YYYY-MM-DD format'
            }, status=400)
        
        if end_d < start_d:
            return Response({
                'error': 'end_date must be >= start_date'
            }, status=400)
        
        if (end_d - start_d).days > 180:
            return Response({
                'error': 'Range cannot exceed 180 days'
            }, status=400)
        
        created = updated = 0
        
        with transaction.atomic():
            current_date = start_d
            while current_date <= end_d:
                _, was_created = StayAvailability.objects.update_or_create(
                    stay=stay,
                    date=current_date,
                    defaults={
                        'total_room': total_room,
                        'is_available': is_available
                    }
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
                
                current_date += timedelta(days=1)
        
        return Response({
            'message': f'Availability set: {created} created, {updated} updated',
            'dates_processed': (end_d - start_d).days + 1
        }, status=201)
        
    except Stay.DoesNotExist:
        return Response({'error': 'Stay not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ set_stay_availability: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_single_availability(request, stay_id, avail_id):
    """Update single availability date"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        stay = Stay.objects.get(id=stay_id, host=host)
        avail = StayAvailability.objects.get(id=avail_id, stay=stay)
        
        if 'total_room' in request.data:
            avail.total_room = int(request.data['total_room'])
        
        if 'is_available' in request.data:
            val = request.data['is_available']
            avail.is_available = val if isinstance(val, bool) else str(val).lower() == 'true'
        
        avail.save()
        
        return Response({
            'message': 'Updated',
            'date': str(avail.date),
            'is_available': avail.is_available
        })
        
    except (Stay.DoesNotExist, StayAvailability.DoesNotExist):
        return Response({'error': 'Not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ update_single_availability: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_availability(request, stay_id, avail_id):
    """Delete availability - ✅ Safe Redis"""
    try:
        user_profile = _resolve_user_profile(request)
        if user_profile.user_role != 'host':
            return Response({'error': 'Not authorized'}, status=403)

        host, err = _get_host_profile(user_profile)
        if err:
            return err

        stay = Stay.objects.get(id=stay_id, host=host)
        avail = StayAvailability.objects.get(id=avail_id, stay=stay)
        
        # Check if booked
        if avail.occupied_room > 0:
            return Response({
                'error': 'Cannot delete availability with bookings'
            }, status=400)

        avail.delete()
        
        # ✅ Safe cache invalidation
        safe_cache_delete(f"stay_availability:{stay_id}")

        return Response({'message': 'Availability deleted'})

    except (Stay.DoesNotExist, StayAvailability.DoesNotExist):
        return Response({'error': 'Not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=400)



# ============================================================
# HOST REVIEWS
# ============================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_host_reviews(request):
    """Get host reviews - ✅ Safe Redis"""
    try:
        user_profile = _resolve_user_profile(request)
        if user_profile.user_role != 'host':
            return Response({'error': 'Not authorized'}, status=403)

        host, err = _get_host_profile(user_profile)
        if err:
            return err

        reviews = Review.objects.filter(
            stay__host=host
        ).select_related('tourist__user_profile').order_by('-created_at')

        return Response({
            'avg_rating': float(host.avg_rating or 0),
            'total_reviews': reviews.count(),
            'reviews': ReviewSerializer(reviews, many=True).data,
        })

    except Exception as e:
        return Response({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════
# LANGUAGE MANAGEMENT 
# ══════════════════════════════════════════════════════════

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_host_language(request):
    """Add language to host profile"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        language_id = request.data.get('language_id')
        proficiency = request.data.get('proficiency', 'native')
        
        if not language_id:
            return Response({'error': 'language_id required'}, status=400)
        
        if proficiency not in ['basic', 'conversational', 'native']:
            return Response({
                'error': 'Invalid proficiency. Use: basic, conversational, native'
            }, status=400)
        
        language = Language.objects.get(id=language_id)
        
        # Check if exists
        if UserLanguage.objects.filter(
            user_profile=user_profile,
            language=language
        ).exists():
            return Response({'error': 'Language already added'}, status=400)
        
        user_lang = UserLanguage.objects.create(
            user_profile=user_profile,
            language=language,
            proficiency=proficiency,
            is_native=(proficiency == 'native')
        )
        
        # Clear cache
        safe_cache_delete(f"host_profile:{user_profile.id}")
        
        return Response({
            'message': 'Language added successfully',
            'language': {
                'id': str(user_lang.id),
                'language_id': str(language.id),
                'name': language.name,
                'code': language.code,
                'proficiency': proficiency,
                'is_native': proficiency == 'native'
            }
        }, status=201)
        
    except Language.DoesNotExist:
        return Response({'error': 'Language not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ add_host_language: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_host_language(request, language_id):
    """Update language proficiency"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        proficiency = request.data.get('proficiency')
        
        if proficiency not in ['basic', 'conversational', 'native']:
            return Response({
                'error': 'Invalid proficiency'
            }, status=400)
        
        user_lang = UserLanguage.objects.get(
            id=language_id,
            user_profile=user_profile
        )
        
        user_lang.proficiency = proficiency
        user_lang.is_native = (proficiency == 'native')
        user_lang.save()
        
        # Clear cache
        safe_cache_delete(f"host_profile:{user_profile.id}")
        
        return Response({'message': 'Proficiency updated successfully'})
        
    except UserLanguage.DoesNotExist:
        return Response({'error': 'Language not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ update_host_language: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_host_language(request, language_id):
    """Remove language from host profile"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        user_lang = UserLanguage.objects.get(
            id=language_id,
            user_profile=user_profile
        )
        
        user_lang.delete()
        
        # Clear cache
        safe_cache_delete(f"host_profile:{user_profile.id}")
        
        return Response({'message': 'Language removed successfully'})
        
    except UserLanguage.DoesNotExist:
        return Response({'error': 'Language not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ remove_host_language: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)


# ══════════════════════════════════════════════════════════
# STAY PHOTOS MANAGEMENT
# ══════════════════════════════════════════════════════════

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def add_stay_photos(request, stay_id):
    """Add photos to stay"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        stay = Stay.objects.get(id=stay_id, host=host)
        
        photos = request.FILES.getlist('photos') or request.FILES.getlist('photos[]')
        if not photos:
            return Response({'error': 'No photos provided'}, status=400)
        
        # Get max order
        max_order = Media.objects.filter(
            entity_type='stay',
            entity_id=stay.id,
            file_type='image'
        ).count()
        
        created = []
        for idx, photo in enumerate(photos):
            url = upload_file_to_supabase(
                photo,
                'stay-images',
                f'stays/{stay.id}'
            )
            media = Media.objects.create(
                uploader=user_profile,
                entity_type='stay',
                entity_id=stay.id,
                file_path=url,
                file_type='image',
                is_official=False,
                order_index=max_order + idx
            )
            created.append({
                'id': str(media.id),
                'url': url,
                'order': max_order + idx
            })
        
        # Clear cache
        safe_cache_delete(f"host_dashboard:{user_profile.id}")
        
        return Response({
            'message': f'{len(created)} photo(s) added',
            'photos': created
        }, status=201)
        
    except Stay.DoesNotExist:
        return Response({'error': 'Stay not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ add_stay_photos: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_stay_photo(request, stay_id, photo_id):
    """Delete stay photo"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        stay = Stay.objects.get(id=stay_id, host=host)
        photo = Media.objects.get(
            id=photo_id,
            entity_type='stay',
            entity_id=stay.id,
            file_type='image'
        )
        
        photo.delete()
        
        # Clear cache
        safe_cache_delete(f"host_dashboard:{user_profile.id}")
        
        return Response({'message': 'Photo deleted successfully'})
        
    except Media.DoesNotExist:
        return Response({'error': 'Photo not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ delete_stay_photo: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reorder_stay_photos(request, stay_id):
    """Reorder stay photos"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        stay = Stay.objects.get(id=stay_id, host=host)
        
        # Expect: {"photo_ids": ["id1", "id2", "id3"]}
        photo_ids = request.data.get('photo_ids', [])
        
        with transaction.atomic():
            for idx, photo_id in enumerate(photo_ids):
                Media.objects.filter(
                    id=photo_id,
                    entity_type='stay',
                    entity_id=stay.id
                ).update(order_index=idx)
        
        return Response({'message': 'Photos reordered successfully'})
        
    except Stay.DoesNotExist:
        return Response({'error': 'Stay not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ reorder_stay_photos: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)


# ============================================================
# LOCAL ACTIVITIES (for stay pages)
# ============================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_local_activities(request):
    cached = cache.get('all_local_activities')
    if cached:
        try:
            return Response(json.loads(cached))
        except Exception:
            pass

    try:
        from .models import LocalActivity
        activities = LocalActivity.objects.all()
        data = [
            {
                'id':           str(a.id),
                'activity_id':  str(a.activity_id) if a.activity_id else None,
                'set_price':    a.set_price,
                'special_note': a.special_note,
            }
            for a in activities
        ]
        cache.set('all_local_activities', json.dumps(data, default=str), timeout=3600)
        return Response(data)
    except Exception as e:
        logger.error(f'❌ get_local_activities: {e}')
        return Response([])


# ══════════════════════════════════════════════════════════
# BOOKING DETAILS (for dialog)
# ══════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_booking_detail(request, booking_id):
    """Get booking details for dialog"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        booking = Booking.objects.select_related('tourist_profile').get(
            id=booking_id
        )
        
        # Verify booking belongs to this host (via stay)
        # TODO: Add stay_id to booking table to make this check possible
        
        data = {
            'id': str(booking.id),
            'tourist_name': f"{booking.tourist_profile.first_name} {booking.tourist_profile.last_name}",
            'tourist_photo': booking.tourist_profile.profile_pic,
            'tourist_phone': booking.tourist_profile.phone_number,
            'tourist_email': booking.tourist_profile.auth_user_id,  # TODO: Get email from auth.users
            'booking_type': booking.booking_type,
            'booking_status': booking.booking_status,
            'total_amount': float(booking.total_amount),
            'guest_count': booking.guest_count,
            'arrival_time': str(booking.arrival_time) if booking.arrival_time else None,
            'departure_time': str(booking.departure_time) if booking.departure_time else None,
            'special_note': booking.special_note,
            'pickup_location': {
                'latitude': booking.pickup_latitude,
                'longitude': booking.pickup_longitude
            },
            'created_at': booking.created_at.isoformat(),
        }
        
        return Response(data)
        
    except Booking.DoesNotExist:
        return Response({'error': 'Booking not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ get_booking_detail: {e}', exc_info=True)
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def respond_to_booking(request, booking_id):
    """Accept or reject booking request"""
    try:
        user_profile = _get_user_profile(request)
        host, err = _get_host_profile(user_profile)
        if err:
            return err
        
        action = request.data.get('action')  # 'accept' or 'reject'
        
        if action not in ['accept', 'reject']:
            return Response({'error': 'action must be accept or reject'}, status=400)
        
        booking = Booking.objects.get(id=booking_id)
        
        # TODO: Verify booking belongs to this host's stay
        
        if action == 'accept':
            booking.booking_status = 'confirmed'
        else:
            booking.booking_status = 'rejected'
        
        booking.save()
        
        return Response({
            'message': f'Booking {action}ed successfully',
            'booking_status': booking.booking_status
        })
        
    except Booking.DoesNotExist:
        return Response({'error': 'Booking not found'}, status=404)
    except Exception as e:
        logger.error(f'❌ respond_to_booking: {e}', exc_info=True)
        return Response({'error': str(e)}, status=400)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_guides(request):

    city_id_str    = request.query_params.get('city_id',    '').strip()
    date_str       = request.query_params.get('date',       '').strip()
    start_time_str = request.query_params.get('start_time', '').strip()

    errors = {}
    if not city_id_str:    errors['city_id']    = 'Required'
    if not date_str:       errors['date']       = 'Required'
    if not start_time_str: errors['start_time'] = 'Required'
    if errors:
        return Response({'errors': errors}, status=400)

    try:
        search_date = _datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return Response({'errors': {'date': 'Use YYYY-MM-DD format'}}, status=400)

    if search_date < _date_type.today():
        return Response({'errors': {'date': 'Date must be today or in the future'}}, status=400)

    def _parse_time(s):
        for fmt in ('%H:%M:%S', '%H:%M'):
            try:
                return _datetime.strptime(s, fmt).time()
            except ValueError:
                continue
        return None

    tourist_time = _parse_time(start_time_str)
    if not tourist_time:
        return Response({'errors': {'start_time': 'Use HH:MM format'}}, status=400)

    try:
        city_uuid = uuid_lib.UUID(city_id_str)
        city_obj  = City.objects.get(id=city_uuid)
    except (ValueError, City.DoesNotExist):
        return Response({'errors': {'city_id': 'City not found'}}, status=404)

    matching_guide_ids = (
        GuideAvailability.objects
        .filter(
            date=search_date,
            start_time__lte=tourist_time,   # slot starts at or before tourist
            end_time__gt=tourist_time,       # slot ends strictly after tourist
            is_booked=False,
        )
        .values('guide_profile_id')
        .annotate(cnt=_Count('id'))
        .filter(cnt__gte=1)
        .values_list('guide_profile_id', flat=True)
    )

    guides = (
        GuideProfile.objects
        .select_related('user_profile')
        .filter(
            id__in=matching_guide_ids,
            city_id=city_uuid,
            verification_status='verified',
            is_available=True,
        )
    )

    result = []
    for guide in guides:
        up = guide.user_profile

        languages = [
            {'id': str(l.language.id), 'name': l.language.name,
             'code': l.language.code,  'proficiency': l.proficiency}
            for l in UserLanguage.objects.filter(user_profile=up)
                                         .select_related('language')
        ]

        specialties = [
            {'id': str(i.interest.id), 'name': i.interest.name,
             'category': i.interest.category}
            for i in UserInterest.objects.filter(user_profile=up)
                                         .select_related('interest')
        ]

        specializations = [
            {'id': str(gs.specialization.id), 'slug': gs.specialization.slug,
             'label': gs.specialization.label, 'category': gs.specialization.category}
            for gs in GuideSpecialization.objects.filter(guide_profile=guide)
                                                 .select_related('specialization')
        ]

        # ALL free slots on that date — tourist picks freely in detail screen
        all_day_slots = GuideAvailability.objects.filter(
            guide_profile=guide,
            date=search_date,
            is_booked=False,
        ).order_by('start_time')

        available_slots = [
            {'id': str(s.id),
             'start_time': str(s.start_time),
             'end_time':   str(s.end_time)}
            for s in all_day_slots
        ]

        reviews_preview = []
        for r in Review.objects.filter(guide=guide).order_by('-created_at')[:3]:
            try:    tourist_name = r.tourist.user_profile.full_name
            except: tourist_name = ''
            reviews_preview.append({
                'rating':       r.rating,
                'review':       r.review or '',
                'tourist_name': tourist_name,
                'created_at':   r.created_at.isoformat(),
            })

        result.append({
            'guide_profile_id':         str(guide.id),
            'user_profile_id':          str(up.id),
            'full_name':                up.full_name,
            'profile_pic':              up.profile_pic or '',
            'profile_bio':              up.profile_bio or '',
            'city_id':                  str(guide.city_id),
            'city_name':                city_obj.name,
            'experience_years':         guide.experience_years,
            'rate_per_hour':            float(guide.rate_per_hour or 0),
            'avg_rating':               float(guide.avg_rating or 0),
            'total_completed_bookings': guide.total_completed_bookings or 0,
            'is_SLTDA_verified':        guide.is_SLTDA_verified,
            'languages':                languages,
            'specialties':              specialties,
            'available_slots':          available_slots,
            'reviews_preview':          reviews_preview,
        })

    result.sort(key=lambda g: g['avg_rating'], reverse=True)

    return Response({
        'count':      len(result),
        'city':       {'id': str(city_obj.id), 'name': city_obj.name},
        'date':       date_str,
        'start_time': start_time_str,
        'guides':     result,
    })
 

# ══════════════════════════════════════════════════════════════════════════════
# GUIDE PUBLIC PROFILE
# GET /api/accounts/guides/<guide_profile_id>/
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([AllowAny])
def guide_public_profile(request, guide_profile_id):

    try:
        guide = GuideProfile.objects.select_related('user_profile').get(
            id=guide_profile_id,
            verification_status='verified',
        )
    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide not found'}, status=404)

    up = guide.user_profile

    city_data = None
    try:
        city = City.objects.get(id=guide.city_id)
        city_data = {'id': str(city.id), 'name': city.name,
                     'country': getattr(city, 'country', '')}
    except City.DoesNotExist:
        pass

    languages = [
        {'id': str(l.language.id), 'name': l.language.name,
         'code': l.language.code, 'proficiency': l.proficiency,
         'is_native': l.is_native}
        for l in UserLanguage.objects.filter(user_profile=up)
                                     .select_related('language')
    ]

    specialties = [
        {'id': str(i.interest.id), 'name': i.interest.name,
         'category': i.interest.category}
        for i in UserInterest.objects.filter(user_profile=up)
                                     .select_related('interest')
    ]

    specializations = [
        {'id': str(gs.specialization.id), 'slug': gs.specialization.slug,
         'label': gs.specialization.label, 'category': gs.specialization.category}
        for gs in GuideSpecialization.objects.filter(guide_profile=guide)
                                             .select_related('specialization')
    ]

    local_activities_data = []
    las = LocalActivity.objects.filter(guide=guide).select_related('activity')
    for la in las:
        if la.activity:
            local_activities_data.append({
                'local_activity_id': str(la.id),
                'activity_id': str(la.activity.id),
                'name': la.activity.name,
                'category': la.activity.category,
                'description': la.activity.description or '',
                'duration': la.activity.duration,
                'set_price': la.set_price or la.activity.base_price,
                'special_note': la.special_note or '',
            })

    gallery_data = [
        {'id': str(p.id), 'url': p.file_path}
        for p in Media.objects.filter(uploader=up, file_type='image')
                              .order_by('order_index', '-created_at')
    ]

    # All free slots for the next 60 days — grouped by date
    today  = _date_type.today()
    slots  = GuideAvailability.objects.filter(
        guide_profile=guide,
        date__gte=today,
        date__lte=today + _timedelta(days=60),
        is_booked=False,
    ).order_by('date', 'start_time')

    availability = {}
    for s in slots:
        key = str(s.date)
        availability.setdefault(key, []).append({
            'id':         str(s.id),
            'start_time': str(s.start_time),
            'end_time':   str(s.end_time),
        })

    reviews_qs = (
        Review.objects.filter(guide=guide)
        .select_related('tourist__user_profile')
        .order_by('-created_at')[:20]
    )
    reviews_data = []
    for r in reviews_qs:
        tourist_name = tourist_photo = ''
        try:
            tourist_name  = r.tourist.user_profile.full_name
            tourist_photo = r.tourist.user_profile.profile_pic or ''
        except Exception:
            pass
        reviews_data.append({
            'id':            str(r.id),
            'rating':        r.rating,
            'review':        r.review or '',
            'tourist_name':  tourist_name,
            'tourist_photo': tourist_photo,
            'created_at':    r.created_at.isoformat(),
        })

    return Response({
        'guide_profile_id':         str(guide.id),
        'user_profile_id':          str(up.id),
        'full_name':                up.full_name,
        'profile_pic':              up.profile_pic or '',
        'profile_bio':              up.profile_bio or '',
        'gender':                   up.gender or '',
        'country':                  up.country or '',
        'phone_number':             up.phone_number or '',
        'member_since':             guide.created_at.strftime('%B %Y'),
        'city':                     city_data,
        'experience_years':         guide.experience_years,
        'education':                guide.education or '',
        'rate_per_hour':            float(guide.rate_per_hour or 0),
        'avg_rating':               float(guide.avg_rating or 0),
        'booking_response_rate':    float(guide.booking_response_rate or 0),
        'total_completed_bookings': guide.total_completed_bookings or 0,
        'is_available':             guide.is_available,
        'is_SLTDA_verified':        guide.is_SLTDA_verified,
        'verification_status':      guide.verification_status,
        'languages':                languages,
        'specialties':              specialties,
        'specializations':          specializations,
        'local_activities':         local_activities_data,
        'gallery':                  gallery_data,
        'availability':             availability,
        'reviews':                  reviews_data,
        'review_count':             len(reviews_data),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_system_locations(request):
    """
    GET /api/accounts/locations/
    Returns all is_system=True, is_active=True locations.
    Optional query params:
        ?category=Beach|Heritage|City|Nature|Airport|Hotel|Other
        ?q=search_term   (matches name or region, case-insensitive)
    Redis-cached for 1 hour.
    """
    category = request.query_params.get('category', '').strip()
    q        = request.query_params.get('q', '').strip().lower()
 
    # Only use cache for un-filtered requests
    if not category and not q:
        cached = safe_cache_get(_LOCATIONS_CACHE_KEY)
        if cached:
            return Response(cached)
 
    qs = TouristLocation.objects.filter(is_system=True, is_active=True)
 
    if category and category != 'All':
        qs = qs.filter(category=category)
 
    if q:
        from django.db.models import Q
        qs = qs.filter(Q(name__icontains=q) | Q(region__icontains=q))
 
    data = [
        {
            'id':        str(loc.id),
            'name':      loc.name,
            'region':    loc.region,
            'category':  loc.category,
            'latitude':  loc.latitude,
            'longitude': loc.longitude,
        }
        for loc in qs
    ]
 
    # Cache only the full unfiltered list
    if not category and not q:
        safe_cache_set(_LOCATIONS_CACHE_KEY, data, timeout=_LOCATIONS_CACHE_TTL)
 
    return Response(data)
 
 
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def tourist_saved_locations(request):
    """
    GET  /api/accounts/locations/saved/  → tourist's own custom saved locations
    POST /api/accounts/locations/saved/  → save a new location
         body: { name, latitude, longitude, region?, category? }
    """
    user_profile = _get_user_profile(request)
 
    if user_profile.user_role != 'tourist':
        return Response({'error': 'Only tourists can save locations'}, status=403)
 
    if request.method == 'GET':
        locs = TouristLocation.objects.filter(
            is_system=False,
            created_by=user_profile,
            is_active=True,
        ).order_by('-created_at')
 
        data = [
            {
                'id':        str(loc.id),
                'name':      loc.name,
                'region':    loc.region,
                'category':  loc.category,
                'latitude':  loc.latitude,
                'longitude': loc.longitude,
            }
            for loc in locs
        ]
        return Response(data)
 
    # POST — save a new custom location
    name      = request.data.get('name', '').strip()
    latitude  = request.data.get('latitude')
    longitude = request.data.get('longitude')
 
    if not name:
        return Response({'error': 'name is required'}, status=400)
    if latitude is None or longitude is None:
        return Response({'error': 'latitude and longitude are required'}, status=400)
 
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return Response({'error': 'latitude and longitude must be numbers'}, status=400)
 
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return Response({'error': 'Coordinates out of range'}, status=400)
 
    # Limit to 20 saved locations per tourist
    existing_count = TouristLocation.objects.filter(
        is_system=False, created_by=user_profile, is_active=True
    ).count()
    if existing_count >= 20:
        return Response(
            {'error': 'You can save up to 20 custom locations'},
            status=400
        )
 
    loc = TouristLocation.objects.create(
        name       = name,
        region     = request.data.get('region', '').strip(),
        category   = request.data.get('category', 'Other'),
        latitude   = lat,
        longitude  = lng,
        is_system  = False,
        created_by = user_profile,
    )
 
    return Response({
        'id':        str(loc.id),
        'name':      loc.name,
        'region':    loc.region,
        'category':  loc.category,
        'latitude':  loc.latitude,
        'longitude': loc.longitude,
    }, status=201)
 
 
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_saved_location(request, location_id):
    """
    DELETE /api/accounts/locations/saved/<location_id>/
    Deletes a tourist's own saved location.
    """
    user_profile = _get_user_profile(request)
 
    if user_profile.user_role != 'tourist':
        return Response({'error': 'Only tourists can delete saved locations'}, status=403)
 
    try:
        loc = TouristLocation.objects.get(
            id=location_id,
            is_system=False,
            created_by=user_profile,
        )
        loc.delete()
        return Response({'message': 'Location deleted'})
    except TouristLocation.DoesNotExist:
        return Response({'error': 'Location not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_guide_review(request):
    """
    POST /api/accounts/reviews/
 
    Body:
        guide_profile_id  – UUID    (required)
        booking_id        – UUID    (required)  ← guide_booking.id
        rating            – int 1-5 (required)
        review            – str     (optional)
        tip_amount        – int LKR (optional)
    """
 
    # ── 1. UserProfile ─────────────────────────────────────────────────────
    user_profile = _get_user_profile(request)
    if user_profile.user_role != 'tourist':
        return Response({'error': 'Only tourists can leave reviews'}, status=403)
 
    # ── 2. TouristProfile ──────────────────────────────────────────────────
    try:
        tourist = TouristProfile.objects.get(user_profile=user_profile)
    except TouristProfile.DoesNotExist:
        return Response({'error': 'Tourist profile not found'}, status=404)
 
    # ── 3. Validate body ───────────────────────────────────────────────────
    guide_profile_id = request.data.get('guide_profile_id')
    booking_id       = request.data.get('booking_id')
    rating           = request.data.get('rating')
 
    if not guide_profile_id:
        return Response({'error': 'guide_profile_id is required'}, status=400)
    if not booking_id:
        return Response({'error': 'booking_id is required'}, status=400)
    if rating is None:
        return Response({'error': 'rating is required'}, status=400)
 
    try:
        rating = int(rating)
        if not (1 <= rating <= 5):
            raise ValueError
    except (ValueError, TypeError):
        return Response({'error': 'rating must be an integer between 1 and 5'}, status=400)
 
    # ── 4. GuideProfile ────────────────────────────────────────────────────
    try:
        guide = GuideProfile.objects.get(id=guide_profile_id)
    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide not found'}, status=404)
 
    # ── 5. Verify booking belongs to this tourist ──────────────────────────
    #      GuideBooking.tourist_profile_id = user_profile.id  (from models.py)
    try:
        booking = GuideBooking.objects.get(
            id=booking_id,
            tourist_profile_id=user_profile.id,
        )
    except GuideBooking.DoesNotExist:
        return Response({'error': 'Booking not found or does not belong to you'}, status=404)
 
    # ── 6. Status guards ───────────────────────────────────────────────────
    if booking.booking_status == 'pending':
        return Response({'error': 'Tour has not started yet'}, status=400)
    if booking.booking_status in ('cancelled', 'rejected'):
        return Response({'error': 'Cannot review a cancelled or rejected booking'}, status=400)
 
    # ── 7. Duplicate check — use tourist_id + guide_id ─────────────────────
    #      We cannot use booking_id on the review table since it references
    #      a different "booking" table, not "guide_booking".
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id FROM public.review WHERE tourist_id = %s AND guide_id = %s LIMIT 1",
            [str(tourist.id), str(guide.id)],
        )
        if cur.fetchone():
            return Response({'error': 'You have already reviewed this guide'}, status=400)
 
    # ── 8. Insert + tip + avg_rating ───────────────────────────────────────
    try:
        with transaction.atomic():
 
            # Raw INSERT — booking_id = NULL to avoid FK violation.
            # Requires: ALTER TABLE public.review
            #           ALTER COLUMN booking_id DROP NOT NULL;
            new_id      = uuid_lib.uuid4()
            review_text = request.data.get('review', '').strip() or None
 
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.review
                        (id, tourist_id, guide_id, stay_id, booking_id, rating, review)
                    VALUES
                        (%s, %s, %s, NULL, NULL, %s, %s)
                    """,
                    [str(new_id), str(tourist.id), str(guide.id), rating, review_text],
                )
 
            # Tip
            tip = 0
            try:
                tip = int(request.data.get('tip_amount', 0) or 0)
            except (ValueError, TypeError):
                pass
 
            if tip > 0:
                GuideBooking.objects.filter(id=booking_id).update(tip_amount=tip)
                upd = {}
                if hasattr(guide, 'total_tip_earned'):
                    upd['total_tip_earned'] = guide.total_tip_earned + tip
                if hasattr(guide, 'total_earned'):
                    upd['total_earned'] = guide.total_earned + tip
                if upd:
                    GuideProfile.objects.filter(id=guide.id).update(**upd)
 
            # Recalculate avg_rating
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT ROUND(AVG(rating)::numeric, 1) FROM public.review WHERE guide_id = %s",
                    [str(guide.id)],
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    GuideProfile.objects.filter(id=guide.id).update(avg_rating=float(row[0]))
 
            # Redis cache invalidation (safe)
            try:
                RedisCache.invalidate_all_user_data(str(guide.user_profile_id))
            except Exception:
                pass
 
        return Response({'message': 'Review submitted successfully'}, status=201)
 
    except Exception as e:
        logger.error(f'❌ create_guide_review: {e}', exc_info=True)
        return Response({'error': str(e)}, status=500)
 
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_stay_review(request, booking_id):
    """
    POST /api/accounts/stays/<booking_id>/review/
    """
    user_profile = _get_user_profile(request)
    if user_profile.user_role != 'tourist':
        return Response({'error': 'Only tourists can leave reviews'}, status=403)

    try:
        tourist = TouristProfile.objects.get(user_profile=user_profile)
    except TouristProfile.DoesNotExist:
        return Response({'error': 'Tourist profile not found'}, status=404)

    rating = request.data.get('rating')
    if rating is None:
        return Response({'error': 'rating is required'}, status=400)
        
    try:
        rating = int(rating)
        if not (1 <= rating <= 5):
            raise ValueError
    except (ValueError, TypeError):
        return Response({'error': 'rating must be an integer between 1 and 5'}, status=400)

    try:
        booking = StayBooking.objects.get(
            id=booking_id,
            tourist_profile_id=user_profile.id,
        )
    except StayBooking.DoesNotExist:
        return Response({'error': 'Booking not found or does not belong to you'}, status=404)

    if booking.booking_status != 'completed':
        return Response({'error': 'Can only review completed stays'}, status=400)

    # Prevent duplicate reviews
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id FROM public.review WHERE tourist_id = %s AND stay_id = %s LIMIT 1",
            [str(tourist.id), str(booking.stay_id)]
        )
        if cur.fetchone():
            return Response({'error': 'You have already reviewed this stay'}, status=400)

    try:
        with transaction.atomic():
            new_id = uuid_lib.uuid4()
            review_text = request.data.get('review', '').strip() or None

            # Raw INSERT to handle schema constraints safely (same as guide reviews)
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.review
                        (id, tourist_id, guide_id, stay_id, booking_id, rating, review)
                    VALUES
                        (%s, %s, NULL, %s, NULL, %s, %s)
                    """,
                    [str(new_id), str(tourist.id), str(booking.stay_id), rating, review_text],
                )

            # Handle Tip Amount & update Host's total earnings
            tip = 0
            try:
                tip = int(request.data.get('tip_amount', 0) or 0)
            except (ValueError, TypeError):
                pass

            if tip > 0:
                StayBooking.objects.filter(id=booking_id).update(tip_amount=tip)
                try:
                    host_prof = HostProfile.objects.get(id=booking.host_profile_id)
                    host_prof.total_tip_earned = (host_prof.total_tip_earned or 0) + tip
                    host_prof.total_earned = (host_prof.total_earned or 0) + tip
                    host_prof.save(update_fields=['total_tip_earned', 'total_earned'])
                except HostProfile.DoesNotExist:
                    pass

            # Recalculate avg_rating for Host (across all their stays)
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT ROUND(AVG(r.rating)::numeric, 1) 
                    FROM public.review r
                    JOIN public.stay s ON r.stay_id = s.id
                    WHERE s.host_id = %s
                    """,
                    [str(booking.host_profile_id)]
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    HostProfile.objects.filter(id=booking.host_profile_id).update(avg_rating=float(row[0]))

            # Clear Redis Cache for both tourist and host
            try:
                RedisCache.invalidate_all_user_data(str(booking.tourist_profile_id))
                host_prof = HostProfile.objects.get(id=booking.host_profile_id)
                safe_cache_delete(f"host_dashboard:{host_prof.user_profile_id}")
                safe_cache_delete(f"host_profile:{host_prof.user_profile_id}")
            except Exception:
                pass

        return Response({'message': 'Stay review submitted successfully'}, status=201)

    except Exception as e:
        logger.error(f'❌ create_stay_review: {e}', exc_info=True)
        return Response({'error': str(e)}, status=500)


# ── GET all specializations ──────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def get_all_specializations(request):
    """
    GET /api/accounts/specializations/
    Returns the full master specialization list grouped by category.
    """
    specs = Specialization.objects.filter()
    serializer = SpecializationSerializer(specs, many=True)
    return Response(serializer.data)


# ── Add guide specializations ────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_guide_specializations(request):
    """
    POST /api/accounts/guide/specializations/add/
    Body: { "specialization_ids": ["<uuid>", ...] }
    Replaces the guide's entire specialization list with the provided IDs.
    """
    user_profile = (
        request.user.user_profile
        if hasattr(request.user, 'user_profile')
        else request.user
    )
    if user_profile.user_role != 'guide':
        return Response({'error': 'Not authorized'}, status=403)

    try:
        guide = GuideProfile.objects.get(user_profile=user_profile)
    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide profile not found'}, status=404)

    spec_ids = request.data.get('specialization_ids', [])
    if not isinstance(spec_ids, list):
        return Response({'error': 'specialization_ids must be a list'}, status=400)

    # Validate all IDs exist
    valid_specs = Specialization.objects.filter(id__in=spec_ids)
    if valid_specs.count() != len(spec_ids):
        return Response({'error': 'One or more specialization IDs are invalid'}, status=400)

    # Replace: delete existing, then bulk-create new
    GuideSpecialization.objects.filter(guide_profile=guide).delete()
    GuideSpecialization.objects.bulk_create([
        GuideSpecialization(guide_profile=guide, specialization=s)
        for s in valid_specs
    ])

    # Invalidate cache
    RedisCache.invalidate_all_user_data(str(user_profile.id))

    saved = GuideSpecialization.objects.filter(
        guide_profile=guide).select_related('specialization')
    return Response({
        'specializations': [
            {'id': str(s.specialization.id), 'slug': s.specialization.slug,
             'label': s.specialization.label, 'category': s.specialization.category}
            for s in saved
        ]
    })


# ── Remove a single guide specialization ─────────────────────────────────────
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_guide_specialization(request, specialization_id):
    """
    DELETE /api/accounts/guide/specializations/<specialization_id>/delete/
    """
    user_profile = (
        request.user.user_profile
        if hasattr(request.user, 'user_profile')
        else request.user
    )
    if user_profile.user_role != 'guide':
        return Response({'error': 'Not authorized'}, status=403)

    try:
        guide = GuideProfile.objects.get(user_profile=user_profile)
    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide profile not found'}, status=404)

    deleted, _ = GuideSpecialization.objects.filter(
        guide_profile=guide,
        specialization_id=specialization_id
    ).delete()

    if not deleted:
        return Response({'error': 'Specialization not found on this guide'}, status=404)

    RedisCache.invalidate_all_user_data(str(user_profile.id))
    return Response({'message': 'Specialization removed'})


# ============================================================
# LOCAL ACTIVITIES
# ============================================================
 
@api_view(['GET'])
@permission_classes([AllowAny])
def get_all_activities(request):
    """GET /api/accounts/activities/ — full master activity list (public)."""
    try:
        activities = Activity.objects.filter(is_active=True)
        return Response(ActivitySerializer(activities, many=True).data)
    except Exception as e:
        logger.error(f'❌ get_all_activities: {e}')
        return Response([])
 
 
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_local_activities(request):
    """GET /api/accounts/activities/local/ — legacy endpoint (host page)."""
    try:
        activities = LocalActivity.objects.select_related('activity').all()
        data = [
            {
                'id':            str(a.id),
                'activity_id':   str(a.activity.id) if a.activity else None,
                'name':          a.activity.name if a.activity else '',
                'set_price':     a.set_price,
                'special_note':  a.special_note,
            }
            for a in activities
        ]
        return Response(data)
    except Exception as e:
        logger.error(f'❌ get_local_activities: {e}')
        return Response([])
 
 
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_guide_activities(request):
    """GET /api/accounts/guide/activities/ — guide's own local activities."""
    user_profile = _get_user_profile(request)
    try:
        guide = GuideProfile.objects.get(user_profile=user_profile)
    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide profile not found'}, status=404)
    las = LocalActivity.objects.filter(guide=guide).select_related('activity')
    return Response(LocalActivitySerializer(las, many=True).data)
 
 
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_guide_activity(request):
    """POST /api/accounts/guide/activities/add/
    Body: { activity_id, set_price (opt), special_note (opt) }"""
    user_profile = _get_user_profile(request)
    try:
        guide = GuideProfile.objects.get(user_profile=user_profile)
    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide profile not found'}, status=404)
 
    activity_id = request.data.get('activity_id')
    if not activity_id:
        return Response({'error': 'activity_id is required'}, status=400)
 
    try:
        activity = Activity.objects.get(id=activity_id, is_active=True)
    except Activity.DoesNotExist:
        return Response({'error': 'Activity not found'}, status=404)
 
    # Prevent duplicates
    if LocalActivity.objects.filter(guide=guide, activity=activity).exists():
        return Response({'error': 'Activity already added'}, status=400)
 
    la = LocalActivity.objects.create(
        guide=guide,
        activity=activity,
        set_price=request.data.get('set_price'),
        special_note=request.data.get('special_note', ''),
    )
    # Invalidate profile cache
    RedisCache.invalidate_all_user_data(str(user_profile.id))
    return Response(LocalActivitySerializer(la).data, status=201)
 
 
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_guide_activity(request, local_activity_id):
    """DELETE /api/accounts/guide/activities/<local_activity_id>/delete/"""
    user_profile = _get_user_profile(request)
    try:
        guide = GuideProfile.objects.get(user_profile=user_profile)
    except GuideProfile.DoesNotExist:
        return Response({'error': 'Guide profile not found'}, status=404)
 
    deleted, _ = LocalActivity.objects.filter(
        id=local_activity_id, guide=guide).delete()
    if not deleted:
        return Response({'error': 'Activity not found'}, status=404)
 
    RedisCache.invalidate_all_user_data(str(user_profile.id))
    return Response({'message': 'Activity removed'})


