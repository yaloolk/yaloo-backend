# accounts/redis_utils.py

import json
import redis
from django.conf import settings
from django.core.cache import cache
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

# Initialize Redis client directly (for operations not supported by Django cache)
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=int(settings.REDIS_DB),
    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
    decode_responses=True,  # Auto-decode bytes to strings
    socket_connect_timeout=5,
    socket_timeout=5,
)


class RedisCache:
    """Redis caching utilities for Yaloo"""
    
    # Cache key prefixes
    USER_PROFILE_KEY = "user_profile:{user_id}"
    USER_STATS_KEY = "user_stats:{user_id}"
    USER_LANGUAGES_KEY = "user_languages:{user_id}"
    USER_INTERESTS_KEY = "user_interests:{user_id}"
    USER_GALLERY_KEY = "user_gallery:{user_id}"
    ONLINE_USERS_KEY = "online_users"
    USER_SESSION_KEY = "session:{user_id}:{device_id}"
    RATE_LIMIT_KEY = "rate_limit:{action}:{user_id}"
    
    # TTL values (in seconds)
    PROFILE_TTL = 3600  # 1 hour
    STATS_TTL = 1800    # 30 minutes
    LANGUAGES_TTL = 3600
    INTERESTS_TTL = 1800
    GALLERY_TTL = 600   # 10 minutes
    SESSION_TTL = 86400  # 24 hours
    ONLINE_TTL = 300    # 5 minutes
    
    @staticmethod
    def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user profile from cache
        Returns None if not cached
        """
        try:
            key = RedisCache.USER_PROFILE_KEY.format(user_id=user_id)
            cached_data = cache.get(key)
            
            if cached_data:
                logger.debug(f"✅ Cache HIT for user profile: {user_id}")
                return json.loads(cached_data) if isinstance(cached_data, str) else cached_data
            
            logger.debug(f"❌ Cache MISS for user profile: {user_id}")
            return None
        except Exception as e:
            logger.error(f"Redis get error for user {user_id}: {e}")
            return None
    
    @staticmethod
    def set_user_profile(user_id: str, profile_data: Dict[str, Any], ttl: int = PROFILE_TTL):
        """
        Cache user profile data
        """
        try:
            key = RedisCache.USER_PROFILE_KEY.format(user_id=user_id)
            # Serialize to JSON string for consistent storage
            cache.set(key, json.dumps(profile_data), timeout=ttl)
            logger.debug(f"✅ Cached user profile: {user_id} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Redis set error for user {user_id}: {e}")
            return False
    
    @staticmethod
    def invalidate_user_profile(user_id: str):
        """
        Clear user profile from cache (call this when profile is updated)
        """
        try:
            key = RedisCache.USER_PROFILE_KEY.format(user_id=user_id)
            cache.delete(key)
            logger.debug(f"🗑️ Invalidated cache for user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Redis delete error for user {user_id}: {e}")
            return False
    
    @staticmethod
    def invalidate_all_user_data(user_id: str):
        """
        Invalidate ALL cached data for a user (profile, stats, languages, etc.)
        Call this when user makes significant updates
        """
        try:
            keys_to_delete = [
                RedisCache.USER_PROFILE_KEY.format(user_id=user_id),
                RedisCache.USER_STATS_KEY.format(user_id=user_id),
                RedisCache.USER_LANGUAGES_KEY.format(user_id=user_id),
                RedisCache.USER_INTERESTS_KEY.format(user_id=user_id),
                RedisCache.USER_GALLERY_KEY.format(user_id=user_id),
            ]
            cache.delete_many(keys_to_delete)
            logger.debug(f"🗑️ Invalidated ALL cache for user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Redis bulk delete error for user {user_id}: {e}")
            return False
    
    # ==================== USER STATS ====================
    
    @staticmethod
    def get_user_stats(user_id: str) -> Optional[Dict[str, Any]]:
        """Get user statistics from cache"""
        try:
            key = RedisCache.USER_STATS_KEY.format(user_id=user_id)
            cached_data = cache.get(key)
            if cached_data:
                return json.loads(cached_data) if isinstance(cached_data, str) else cached_data
            return None
        except Exception as e:
            logger.error(f"Error getting stats for user {user_id}: {e}")
            return None
    
    @staticmethod
    def set_user_stats(user_id: str, stats_data: Dict[str, Any]):
        """Cache user statistics"""
        try:
            key = RedisCache.USER_STATS_KEY.format(user_id=user_id)
            cache.set(key, json.dumps(stats_data), timeout=RedisCache.STATS_TTL)
            return True
        except Exception as e:
            logger.error(f"Error caching stats for user {user_id}: {e}")
            return False
    
    # ==================== USER LANGUAGES ====================
    
    @staticmethod
    def get_user_languages(user_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get user languages from cache"""
        try:
            key = RedisCache.USER_LANGUAGES_KEY.format(user_id=user_id)
            cached_data = cache.get(key)
            if cached_data:
                return json.loads(cached_data) if isinstance(cached_data, str) else cached_data
            return None
        except Exception as e:
            logger.error(f"Error getting languages for user {user_id}: {e}")
            return None
    
    @staticmethod
    def set_user_languages(user_id: str, languages_data: List[Dict[str, Any]]):
        """Cache user languages"""
        try:
            key = RedisCache.USER_LANGUAGES_KEY.format(user_id=user_id)
            cache.set(key, json.dumps(languages_data), timeout=RedisCache.LANGUAGES_TTL)
            return True
        except Exception as e:
            logger.error(f"Error caching languages for user {user_id}: {e}")
            return False
    
    # ==================== USER INTERESTS ====================
    
    @staticmethod
    def get_user_interests(user_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get user interests from cache"""
        try:
            key = RedisCache.USER_INTERESTS_KEY.format(user_id=user_id)
            cached_data = cache.get(key)
            if cached_data:
                return json.loads(cached_data) if isinstance(cached_data, str) else cached_data
            return None
        except Exception as e:
            logger.error(f"Error getting interests for user {user_id}: {e}")
            return None
    
    @staticmethod
    def set_user_interests(user_id: str, interests_data: List[Dict[str, Any]]):
        """Cache user interests"""
        try:
            key = RedisCache.USER_INTERESTS_KEY.format(user_id=user_id)
            cache.set(key, json.dumps(interests_data), timeout=RedisCache.INTERESTS_TTL)
            return True
        except Exception as e:
            logger.error(f"Error caching interests for user {user_id}: {e}")
            return False
    
    # ==================== USER GALLERY ====================
    
    @staticmethod
    def get_user_gallery(user_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get user gallery photos from cache"""
        try:
            key = RedisCache.USER_GALLERY_KEY.format(user_id=user_id)
            cached_data = cache.get(key)
            if cached_data:
                return json.loads(cached_data) if isinstance(cached_data, str) else cached_data
            return None
        except Exception as e:
            logger.error(f"Error getting gallery for user {user_id}: {e}")
            return None
    
    @staticmethod
    def set_user_gallery(user_id: str, gallery_data: List[Dict[str, Any]]):
        """Cache user gallery photos"""
        try:
            key = RedisCache.USER_GALLERY_KEY.format(user_id=user_id)
            cache.set(key, json.dumps(gallery_data), timeout=RedisCache.GALLERY_TTL)
            return True
        except Exception as e:
            logger.error(f"Error caching gallery for user {user_id}: {e}")
            return False
    
    # ==================== ONLINE PRESENCE ====================
    
    @staticmethod
    def set_user_online(user_id: str):
        """Mark user as online"""
        try:
            # Use sorted set with timestamp as score
            import time
            redis_client.zadd(RedisCache.ONLINE_USERS_KEY, {user_id: time.time()})
            # Also set individual key for quick check
            redis_client.setex(f"online:{user_id}", RedisCache.ONLINE_TTL, '1')
            logger.debug(f"🟢 User {user_id} marked as online")
            return True
        except Exception as e:
            logger.error(f"Error setting user {user_id} online: {e}")
            return False
    
    @staticmethod
    def is_user_online(user_id: str) -> bool:
        """Check if user is online"""
        try:
            return redis_client.exists(f"online:{user_id}") == 1
        except Exception as e:
            logger.error(f"Error checking online status for {user_id}: {e}")
            return False
    
    @staticmethod
    def get_online_users() -> List[str]:
        """Get all currently online users"""
        try:
            import time
            current_time = time.time()
            # Remove users inactive for more than 5 minutes
            redis_client.zremrangebyscore(
                RedisCache.ONLINE_USERS_KEY,
                0,
                current_time - RedisCache.ONLINE_TTL
            )
            # Get remaining online users
            online_users = redis_client.zrange(RedisCache.ONLINE_USERS_KEY, 0, -1)
            return list(online_users)
        except Exception as e:
            logger.error(f"Error getting online users: {e}")
            return []
    
    # ==================== RATE LIMITING ====================
    
    @staticmethod
    def check_rate_limit(user_id: str, action: str, max_requests: int = 100, window: int = 3600) -> bool:
        """
        Check if user has exceeded rate limit
        Returns True if request is allowed, False if rate limit exceeded
        """
        try:
            key = RedisCache.RATE_LIMIT_KEY.format(action=action, user_id=user_id)
            current = redis_client.incr(key)
            
            # Set expiry on first request
            if current == 1:
                redis_client.expire(key, window)
            
            is_allowed = current <= max_requests
            
            if not is_allowed:
                logger.warning(f"⚠️ Rate limit exceeded for user {user_id} on action '{action}'")
            
            return is_allowed
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return True  # Allow request on error to avoid blocking users
    
    # ==================== SESSION MANAGEMENT ====================
    
    @staticmethod
    def store_user_session(user_id: str, device_id: str, session_data: Dict[str, Any]):
        """Store user session with device tracking"""
        try:
            key = RedisCache.USER_SESSION_KEY.format(user_id=user_id, device_id=device_id)
            redis_client.hset(key, mapping=session_data)
            redis_client.expire(key, RedisCache.SESSION_TTL)
            return True
        except Exception as e:
            logger.error(f"Error storing session: {e}")
            return False
    
    @staticmethod
    def get_active_sessions(user_id: str) -> List[Dict[str, Any]]:
        """Get all active sessions for a user"""
        try:
            pattern = RedisCache.USER_SESSION_KEY.format(user_id=user_id, device_id='*')
            keys = redis_client.keys(pattern)
            sessions = []
            for key in keys:
                session_data = redis_client.hgetall(key)
                if session_data:
                    sessions.append(session_data)
            return sessions
        except Exception as e:
            logger.error(f"Error getting sessions: {e}")
            return []
    
    # ==================== HEALTH CHECK ====================
    
    @staticmethod
    def health_check() -> Dict[str, Any]:
        """Check Redis connection health"""
        try:
            redis_client.ping()
            return {
                'status': 'healthy',
                'connected': True,
                'message': 'Redis is operational'
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'connected': False,
                'message': f'Redis error: {str(e)}'
            }