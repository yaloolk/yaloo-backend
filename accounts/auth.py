from rest_framework.permissions import BasePermission
from rest_framework.exceptions import AuthenticationFailed
from .supabase_client import supabase

class SupabaseAuthPermission(BasePermission):
    """
    Validates JWT from Supabase for protected endpoints.
    """

    def has_permission(self, request, view):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise AuthenticationFailed("Authorization header missing")

        try:
            token = auth_header.split(" ")[1]
            user = supabase.auth.get_user(token)
            request.user = user.data  # attach Supabase user data
            return True
        except Exception:
            raise AuthenticationFailed("Invalid or expired token")
