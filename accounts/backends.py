# accounts/backends.py

class UserProfileWrapper:
    """
    Wrapper class to make UserProfile compatible with Django's authentication system.
    This avoids modifying the database model.
    """
    
    def __init__(self, user_profile):
        self._user_profile = user_profile
    
    def __getattr__(self, name):
        """Delegate attribute access to the wrapped UserProfile"""
        return getattr(self._user_profile, name)
    
    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_anonymous(self):
        return False
    
    @property
    def is_active(self):
        return self._user_profile.profile_status == 'active'
    
    @property
    def is_staff(self):
        return self._user_profile.user_role == 'admin'
    
    @property
    def is_superuser(self):
        return self._user_profile.user_role == 'admin'
    
    def get_username(self):
        return str(self._user_profile.auth_user_id)
    
    def has_perm(self, perm, obj=None):
        return self.is_staff
    
    def has_perms(self, perm_list, obj=None):
        return self.is_staff
    
    def has_module_perms(self, app_label):
        return self.is_staff
    
    # Expose the original UserProfile object
    @property
    def user_profile(self):
        return self._user_profile