"""
Rate limiting service for per-app agent execution limits.
Uses in-memory fixed-window counters with thread-safe access.
"""
import time
import threading
from typing import Dict, NamedTuple, Optional
from dataclasses import dataclass


@dataclass
class RateLimitState:
    """Rate limit state for an app"""
    remaining: int
    reset_epoch: int
    limit: int


class RateLimitService:
    """
    Thread-safe in-memory rate limiter using fixed-window approach.
    Each app has a separate counter that resets every minute.
    """
    
    def __init__(self):
        # app_id -> {window_start_epoch_minute, count}
        self._counters: Dict[int, Dict[str, int]] = {}
        self._lock = threading.RLock()
        self._cleanup_threshold = 100  # Clean up when we have this many apps
    
    def check_and_consume(self, app_id: int, max_per_minute: int) -> RateLimitState:
        """
        Check if app can make a request and consume one if allowed.
        
        Args:
            app_id: The app identifier
            max_per_minute: Maximum requests per minute (0 = unlimited)
            
        Returns:
            RateLimitState with remaining count and reset time
        """
        if max_per_minute <= 0:
            # Unlimited - return a state indicating no limits
            return RateLimitState(
                remaining=-1,  # -1 indicates unlimited
                reset_epoch=int(time.time()) + 60,
                limit=max_per_minute
            )
        
        current_time = time.time()
        current_minute = int(current_time // 60)
        
        with self._lock:
            # Get or create counter for this app
            if app_id not in self._counters:
                self._counters[app_id] = {
                    'window_start': current_minute,
                    'count': 0
                }
            
            counter = self._counters[app_id]
            
            # Reset window if we're in a new minute
            if counter['window_start'] < current_minute:
                counter['window_start'] = current_minute
                counter['count'] = 0
            
            # Check if we can make the request
            if counter['count'] >= max_per_minute:
                # Rate limit exceeded
                reset_epoch = (current_minute + 1) * 60  # Next minute
                return RateLimitState(
                    remaining=0,
                    reset_epoch=reset_epoch,
                    limit=max_per_minute
                )
            
            # Consume one request
            counter['count'] += 1
            
            # Cleanup old entries if we have too many
            self._cleanup_if_needed()
            
            # Calculate remaining requests
            remaining = max_per_minute - counter['count']
            reset_epoch = (current_minute + 1) * 60  # Next minute
            
            return RateLimitState(
                remaining=remaining,
                reset_epoch=reset_epoch,
                limit=max_per_minute
            )
    
    def _cleanup_if_needed(self):
        """Clean up stale entries if we have too many apps tracked"""
        if len(self._counters) <= self._cleanup_threshold:
            return
        
        current_minute = int(time.time() // 60)
        stale_apps = []
        
        for app_id, counter in self._counters.items():
            # Remove entries older than 2 minutes
            if counter['window_start'] < current_minute - 1:
                stale_apps.append(app_id)
        
        for app_id in stale_apps:
            del self._counters[app_id]
    
    def get_app_state(self, app_id: int, max_per_minute: int) -> Optional[RateLimitState]:
        """
        Get current rate limit state without consuming a request.
        
        Args:
            app_id: The app identifier
            max_per_minute: Maximum requests per minute
            
        Returns:
            RateLimitState or None if app not tracked
        """
        if max_per_minute <= 0:
            return RateLimitState(
                remaining=-1,
                reset_epoch=int(time.time()) + 60,
                limit=max_per_minute
            )
        
        current_minute = int(time.time() // 60)
        
        with self._lock:
            if app_id not in self._counters:
                return None
            
            counter = self._counters[app_id]
            
            # Reset window if we're in a new minute
            if counter['window_start'] < current_minute:
                counter['window_start'] = current_minute
                counter['count'] = 0
            
            remaining = max_per_minute - counter['count']
            reset_epoch = (current_minute + 1) * 60
            
            return RateLimitState(
                remaining=max(0, remaining),
                reset_epoch=reset_epoch,
                limit=max_per_minute
            )


# Global instance
rate_limit_service = RateLimitService()
