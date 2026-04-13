# accounts/authentication.py

from rest_framework import authentication
from rest_framework import exceptions
from supabase import create_client
from django.conf import settings
from .models import UserProfile
from .backends import UserProfileWrapper  # Import the wrapper
import logging

logger = logging.getLogger(__name__)


class SupabaseAuthentication(authentication.BaseAuthentication):
    """
    Custom authentication class that validates Supabase JWT tokens.
    """
    
    def authenticate(self, request):
        """
        Authenticate the request and return a two-tuple of (user, token).
        """
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        
        if not auth_header:
            return None
        
        try:
            auth_parts = auth_header.split()
            
            if len(auth_parts) != 2 or auth_parts[0].lower() != 'bearer':
                raise exceptions.AuthenticationFailed('Invalid authorization header format')
            
            token = auth_parts[1]
            
            # Verify token with Supabase
            supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
            
            try:
                user_response = supabase.auth.get_user(token)
                
                if not user_response or not user_response.user:
                    raise exceptions.AuthenticationFailed('Invalid or expired token')
                
                supabase_user = user_response.user
                logger.info(f"Supabase user authenticated: {supabase_user.id}")
                
            except Exception as e:
                logger.error(f"Supabase token validation failed: {str(e)}")
                raise exceptions.AuthenticationFailed('Token validation failed')
            
            # Get or create Django user profile
            user_profile = self._get_or_create_user_profile(supabase_user)
            
            # Wrap the user profile to make it compatible with Django auth
            wrapped_user = UserProfileWrapper(user_profile)
            
            return (wrapped_user, token)
            
        except exceptions.AuthenticationFailed:
            raise
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            raise exceptions.AuthenticationFailed(f'Authentication failed: {str(e)}')
    
    def _get_or_create_user_profile(self, supabase_user):
        """
        Get or create a UserProfile based on Supabase user data.
        """
        try:
            user_profile = UserProfile.objects.get(auth_user_id=supabase_user.id)
            logger.info(f"Found existing user profile: {user_profile.id}")
            
        except UserProfile.DoesNotExist:
            user_metadata = supabase_user.user_metadata or {}
            
            user_profile = UserProfile.objects.create(
                auth_user_id=supabase_user.id,
                user_role=user_metadata.get('role', 'tourist'),
                profile_status='active',
                is_complete=False
            )
            
            logger.info(f"Created new user profile: {user_profile.id}")
        
        return user_profile
    
    def authenticate_header(self, request):
        return 'Bearer'