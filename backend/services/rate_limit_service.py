"""
Rate limiting service for per-app agent execution limits.
Uses in-memory fixed-window counters with thread-safe access.
"""
import os
import time
import threading
from typing import Dict, NamedTuple, Optional, Any
from dataclasses import dataclass

from utils.logger import get_logger

logger = get_logger(__name__)


def _env_positive_int(name: str, default: int) -> int:
    """Parse a positive int env var; a malformed or non-positive value falls back to ``default``."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        logger.warning("Invalid integer for %s=%r; using default %s", name, raw, default)
        return default
    if value <= 0:
        logger.warning("%s=%s must be positive; using default %s", name, value, default)
        return default
    return value

# Hard cap on the number of distinct keys tracked by the key-namespace limiter
# (check_and_consume_key), e.g. one entry per distinct client IP hitting a
# discovery endpoint. Without a cap, an attacker rotating IPs could grow this
# dict without bound. Once the cap is reached, *new* keys share a single
# overflow bucket (still rate-limited, just coarser) instead of being tracked
# individually. Env override lets ops tune it without a code change.
DEFAULT_KEY_NAMESPACE_MAX_TRACKED_KEYS = _env_positive_int("A2A_DISCOVERY_MAX_TRACKED_KEYS", 100000)

# The shared overflow bucket (see above) gets its own, wider budget instead of
# reusing a single caller's `max_per_minute` as-is: `max_per_minute * multiplier`.
# Without this, once the tracked-key cap is reached every *distinct new* caller
# for the rest of the window would share one caller's worth of budget, which
# would effectively lock out all of them (fail-closed in the worst possible way).
# Multiplying gives the overflow bucket room proportional to how many callers it
# is expected to absorb, while still being bounded (fail-closed by design, not
# unlimited). Env override lets ops tune it without a code change.
DEFAULT_KEY_NAMESPACE_OVERFLOW_MULTIPLIER = _env_positive_int("A2A_DISCOVERY_OVERFLOW_MULTIPLIER", 100)

# Sentinel key used once the per-key-namespace tracked-key cap is reached.
_OVERFLOW_KEY = "__overflow__"


@dataclass
class RateLimitState:
    """Rate limit state for an app"""
    remaining: int
    reset_epoch: int
    limit: int
    exceeded: bool = False


class RateLimitService:
    """
    Thread-safe in-memory rate limiter using fixed-window approach.
    Each app has a separate counter that resets every minute.
    """
    
    def __init__(
        self,
        key_namespace_max_tracked_keys: int = DEFAULT_KEY_NAMESPACE_MAX_TRACKED_KEYS,
        key_namespace_overflow_multiplier: int = DEFAULT_KEY_NAMESPACE_OVERFLOW_MULTIPLIER,
    ):
        # app_id -> {window_start_epoch_minute, count}
        self._counters: Dict[int, Dict[str, int]] = {}
        self._lock = threading.RLock()
        self._cleanup_threshold = 100  # Clean up when we have this many apps

        # Separate namespace for arbitrary string keys (e.g. per-IP discovery limits),
        # with its OWN lock so this traffic can never contend with, block, or in any
        # way interact with the per-app `_lock`/`_counters` above.
        #
        # Unlike `_counters` (one window_start per app_id, swept entry-by-entry),
        # all keys in this namespace share a single global window. On rollover the
        # whole dict is replaced in O(1) (the old dict is simply dropped and garbage
        # collected), instead of scanning every entry — so cleanup cost is paid at
        # most once per window, not once per insert. Memory is further bounded by
        # `_key_namespace_max_tracked_keys`: once that many distinct keys are seen in
        # a window, any *new* key is folded into a shared overflow bucket (still
        # rate-limited, just coarser, with its own wider budget — see
        # `_key_namespace_overflow_multiplier`) rather than growing the dict without
        # bound.
        #
        # The window boundary is tracked with `time.monotonic()`, not `time.time()`:
        # this namespace's fixed-window rollover must never jump backwards or skip
        # forward because of a wall-clock adjustment (NTP sync, DST, manual change).
        # `reset_epoch`/`Retry-After` shown to callers are still computed from
        # `time.time()`, since those are wall-clock values callers compare against.
        self._key_lock = threading.RLock()
        self._key_namespace_max_tracked_keys = key_namespace_max_tracked_keys
        self._key_namespace_overflow_multiplier = max(1, key_namespace_overflow_multiplier)
        self._key_window_start = int(time.monotonic() // 60)
        self._key_counts: Dict[str, int] = {}
        self._key_overflow_logged_window: Optional[int] = None
        self._key_overflow_denied_count = 0

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
                    limit=max_per_minute,
                    exceeded=True,
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
    
    def check_and_consume_key(self, key: str, max_per_minute: int) -> RateLimitState:
        """
        Check if an arbitrary string key can make a request and consume one if allowed.

        This uses a separate counter namespace (own lock, own dict) from
        `check_and_consume` (app_id-keyed), so callers such as the A2A discovery
        limiter (per client IP) can never drain, collide with, or contend on the lock
        for an app's `agent_rate_limit` budget.

        Unlike the per-app counters, every key in this namespace shares one global
        fixed window: on rollover the whole counts dict is replaced in O(1) rather
        than scanned entry-by-entry, so the only per-window cost is the eventual
        garbage collection of the old dict (paid once per window, not once per call).

        To keep memory bounded against an attacker rotating through many distinct
        keys (e.g. IPs), once `_key_namespace_max_tracked_keys` distinct keys have
        been seen in the current window, any *new* key is folded into a single
        shared overflow bucket for the rest of that window. This is a deliberate
        **fail-closed** design: once the cap is reached, truly new callers get a
        coarser, shared budget rather than an unbounded individual one. That shared
        budget is not simply `max_per_minute` — scaled naively, one caller's budget
        would effectively lock out every other caller sharing the bucket for the rest
        of the window — so the overflow bucket's own budget is
        `max_per_minute * _key_namespace_overflow_multiplier`
        (`A2A_DISCOVERY_OVERFLOW_MULTIPLIER`, default 100). A WARNING that the cap was
        reached is logged at most once per window; a second WARNING, logged once at
        the *next* rollover (i.e. covering the just-ended window), reports how many
        requests the overflow bucket denied, if any.

        Args:
            key: The namespaced key identifying the caller (e.g. "a2a_discovery:1.2.3.4").
            max_per_minute: Maximum requests per minute (<= 0 = unlimited).

        Returns:
            RateLimitState with remaining count and reset time.
        """
        if max_per_minute <= 0:
            return RateLimitState(
                remaining=-1,
                reset_epoch=int(time.time()) + 60,
                limit=max_per_minute
            )

        # Window boundary uses the monotonic clock so a wall-clock jump can never
        # skip or repeat a rollover. Headers shown to callers still use time.time().
        current_minute = int(time.monotonic() // 60)
        wall_minute = int(time.time() // 60)
        reset_epoch = (wall_minute + 1) * 60

        with self._key_lock:
            # Rollover: O(1) wholesale reset instead of an O(n) per-key scan.
            if current_minute > self._key_window_start:
                if self._key_overflow_denied_count > 0:
                    logger.warning(
                        f"Rate limit key-namespace overflow bucket denied "
                        f"{self._key_overflow_denied_count} request(s) in the previous window."
                    )
                self._key_window_start = current_minute
                self._key_counts = {}
                self._key_overflow_logged_window = None
                self._key_overflow_denied_count = 0

            effective_key = key
            is_overflow = False
            if key not in self._key_counts and len(self._key_counts) >= self._key_namespace_max_tracked_keys:
                # Either this key is new since the cap was reached, or it was
                # already folded into the overflow bucket earlier in this window
                # (its own slot was never created, so it lands here again).
                effective_key = _OVERFLOW_KEY
                is_overflow = True
                if self._key_overflow_logged_window != current_minute:
                    self._key_overflow_logged_window = current_minute
                    logger.warning(
                        f"Rate limit key-namespace tracked-key cap "
                        f"({self._key_namespace_max_tracked_keys}) reached; "
                        f"new keys share a coarser overflow bucket for this window."
                    )

            effective_limit = (
                max_per_minute * self._key_namespace_overflow_multiplier if is_overflow else max_per_minute
            )

            count = self._key_counts.get(effective_key, 0)

            if count >= effective_limit:
                if is_overflow:
                    self._key_overflow_denied_count += 1
                return RateLimitState(
                    remaining=0,
                    reset_epoch=reset_epoch,
                    limit=effective_limit,
                    exceeded=True,
                )

            count += 1
            self._key_counts[effective_key] = count

            return RateLimitState(
                remaining=effective_limit - count,
                reset_epoch=reset_epoch,
                limit=effective_limit
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
    
    def get_app_usage_stats(self, app_id: int, max_per_minute: int) -> Dict[str, any]:
        """
        Get detailed usage statistics for an app to calculate stress level.
        
        Args:
            app_id: The app identifier
            max_per_minute: Maximum requests per minute
            
        Returns:
            Dictionary with usage statistics and stress metrics
        """
        if max_per_minute <= 0:
            return {
                'usage_percentage': 0,
                'stress_level': 'unlimited',
                'current_usage': 0,
                'limit': max_per_minute,
                'remaining': -1,
                'reset_in_seconds': 60,
                'is_over_limit': False
            }
        
        current_time = time.time()
        current_minute = int(current_time // 60)
        
        with self._lock:
            if app_id not in self._counters:
                return {
                    'usage_percentage': 0,
                    'stress_level': 'low',
                    'current_usage': 0,
                    'limit': max_per_minute,
                    'remaining': max_per_minute,
                    'reset_in_seconds': 60,
                    'is_over_limit': False
                }
            
            counter = self._counters[app_id]
            
            # Reset window if we're in a new minute
            if counter['window_start'] < current_minute:
                counter['window_start'] = current_minute
                counter['count'] = 0
            
            current_usage = counter['count']
            remaining = max(0, max_per_minute - current_usage)
            usage_percentage = (current_usage / max_per_minute) * 100 if max_per_minute > 0 else 0
            is_over_limit = current_usage > max_per_minute
            
            # Calculate stress level
            if usage_percentage >= 95:
                stress_level = 'critical'
            elif usage_percentage >= 80:
                stress_level = 'high'
            elif usage_percentage >= 50:
                stress_level = 'moderate'
            else:
                stress_level = 'low'
            
            # Calculate seconds until reset
            reset_epoch = (current_minute + 1) * 60
            reset_in_seconds = max(0, reset_epoch - int(current_time))
            
            return {
                'usage_percentage': round(usage_percentage, 1),
                'stress_level': stress_level,
                'current_usage': current_usage,
                'limit': max_per_minute,
                'remaining': remaining,
                'reset_in_seconds': reset_in_seconds,
                'is_over_limit': is_over_limit
            }


# Global instance
rate_limit_service = RateLimitService()
