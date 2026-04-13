# accounts/permissions.py

from rest_framework import permissions


class IsTourist(permissions.BasePermission):
    """
    Permission class to check if user is a tourist.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and 
            hasattr(request.user, 'user_role') and 
            request.user.user_role == 'tourist'
        )


class IsGuide(permissions.BasePermission):
    """
    Permission class to check if user is a guide.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and 
            hasattr(request.user, 'user_role') and 
            request.user.user_role == 'guide'
        )


class IsHost(permissions.BasePermission):
    """
    Permission class to check if user is a host.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and 
            hasattr(request.user, 'user_role') and 
            request.user.user_role == 'host'
        )


class IsVerifiedGuide(permissions.BasePermission):
    """
    Permission class to check if user is a verified guide.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and 
            hasattr(request.user, 'user_role') and 
            request.user.user_role == 'guide' and
            hasattr(request.user, 'guide_profile') and
            request.user.guide_profile.verification_status == 'verified'
        )


class IsVerifiedHost(permissions.BasePermission):
    """
    Permission class to check if user is a verified host.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and 
            hasattr(request.user, 'user_role') and 
            request.user.user_role == 'host' and
            hasattr(request.user, 'host_profile') and
            request.user.host_profile.verification_status == 'verified'
        )


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to only allow owners to edit their own data.
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions are only allowed to the owner
        if hasattr(obj, 'user_profile'):
            return obj.user_profile == request.user
        
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        return False


class IsAdminUser(permissions.BasePermission):
    """
    Permission class to check if user is an admin.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and 
            hasattr(request.user, 'user_role') and 
            request.user.user_role == 'admin'
        )