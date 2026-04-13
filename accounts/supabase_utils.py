# accounts/supabase_utils.py

from supabase import create_client
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def get_supabase_client(use_service_role=False):
    """
    Get Supabase client instance.
    
    Args:
        use_service_role: If True, use service role key (bypasses RLS)
    
    Returns:
        Supabase client instance
    """
    key = settings.SUPABASE_SERVICE_ROLE_KEY if use_service_role else settings.SUPABASE_ANON_KEY
    return create_client(settings.SUPABASE_URL, key)


def verify_supabase_token(token):
    """
    Verify a Supabase JWT token.
    
    Args:
        token: JWT token string
    
    Returns:
        Supabase user object if valid, None otherwise
    """
    try:
        supabase = get_supabase_client()
        user_response = supabase.auth.get_user(token)
        
        if user_response and user_response.user:
            return user_response.user
        
        return None
        
    except Exception as e:
        logger.error(f"Token verification failed: {str(e)}")
        return None


def upload_file_to_supabase(file, bucket_name, file_path):
    """
    Upload a file to Supabase Storage.
    
    Args:
        file: File object to upload
        bucket_name: Name of the storage bucket
        file_path: Path where file should be stored (e.g., 'profiles/user123.jpg')
    
    Returns:
        Public URL of uploaded file or None if failed
    """
    try:
        supabase = get_supabase_client(use_service_role=True)
        
        # Upload file
        response = supabase.storage.from_(bucket_name).upload(
            path=file_path,
            file=file,
            file_options={"content-type": file.content_type}
        )
        
        # Get public URL
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)
        
        logger.info(f"File uploaded successfully: {file_path}")
        return public_url
        
    except Exception as e:
        logger.error(f"File upload failed: {str(e)}")
        return None


def delete_file_from_supabase(bucket_name, file_path):
    """
    Delete a file from Supabase Storage.
    
    Args:
        bucket_name: Name of the storage bucket
        file_path: Path of file to delete
    
    Returns:
        True if successful, False otherwise
    """
    try:
        supabase = get_supabase_client(use_service_role=True)
        supabase.storage.from_(bucket_name).remove([file_path])
        
        logger.info(f"File deleted successfully: {file_path}")
        return True
        
    except Exception as e:
        logger.error(f"File deletion failed: {str(e)}")
        return False


def create_supabase_user(email, password, user_metadata=None):
    """
    Create a new user in Supabase Auth (admin function).
    
    Args:
        email: User email
        password: User password
        user_metadata: Additional user metadata (e.g., {'role': 'tourist'})
    
    Returns:
        User object if successful, None otherwise
    """
    try:
        supabase = get_supabase_client(use_service_role=True)
        
        response = supabase.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": user_metadata or {}
        })
        
        logger.info(f"User created successfully: {email}")
        return response.user
        
    except Exception as e:
        logger.error(f"User creation failed: {str(e)}")
        return None