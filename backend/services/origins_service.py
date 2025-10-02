"""
Origins validation service for per-app CORS origin restrictions.
Handles origin pattern matching and validation logic.
"""
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from urllib.parse import urlparse

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OriginValidationResult:
    """Result of origin validation"""
    is_allowed: bool
    matched_pattern: Optional[str] = None
    error_message: Optional[str] = None


class OriginsService:
    """
    Service for validating request origins against app-configured allowed origins.
    Supports various pattern matching including wildcards and exact matches.
    """
    
    def __init__(self):
        # Cache compiled regex patterns for performance
        self._pattern_cache: Dict[str, re.Pattern] = {}
        self._cache_size_limit = 100
    
    def validate_origin(self, origin: str, allowed_origins: str) -> OriginValidationResult:
        """
        Validate if an origin is allowed based on the app's configuration.
        
        Args:
            origin: The origin to validate (e.g., "https://example.com")
            allowed_origins: Comma-separated list of allowed origin patterns
            
        Returns:
            OriginValidationResult with validation result and details
        """
        # If no origins are configured, allow all (open CORS)
        if not allowed_origins or allowed_origins.strip() == "":
            return OriginValidationResult(
                is_allowed=True,
                matched_pattern=None
            )
        
        # If no origin provided (e.g., direct API calls), allow
        if not origin:
            return OriginValidationResult(
                is_allowed=True,
                matched_pattern=None
            )
        
        # Parse allowed origins list
        allowed_patterns = self._parse_origins_list(allowed_origins)
        
        # Check each pattern
        for pattern in allowed_patterns:
            if self._match_origin(origin, pattern):
                return OriginValidationResult(
                    is_allowed=True,
                    matched_pattern=pattern
                )
        
        return OriginValidationResult(
            is_allowed=False,
            error_message=f"Origin '{origin}' is not in the allowed origins list"
        )
    
    def _parse_origins_list(self, origins: str) -> List[str]:
        """Parse comma-separated origins list and clean up entries."""
        if not origins:
            return []
        
        return [o.strip() for o in origins.split(",") if o.strip()]
    
    def _match_origin(self, origin: str, pattern: str) -> bool:
        """
        Check if an origin matches a pattern.
        
        Supports:
        - Exact matches: https://example.com
        - Wildcard subdomains: https://*.example.com
        - Protocol wildcards: *://example.com  
        - Port wildcards: https://example.com:*
        - Full wildcards: *
        
        Args:
            origin: The origin to check
            pattern: The pattern to match against
            
        Returns:
            bool: True if origin matches the pattern
        """
        # Handle universal wildcard
        if pattern == "*":
            return True
        
        # Handle exact match
        if origin.lower() == pattern.lower():
            return True
        
        # Use cached regex pattern or compile new one
        regex_pattern = self._get_compiled_pattern(pattern)
        if regex_pattern:
            try:
                return bool(regex_pattern.match(origin.lower()))
            except re.error as e:
                logger.warning(f"Regex error matching origin '{origin}' against pattern '{pattern}': {e}")
                return False
        
        return False
    
    def _get_compiled_pattern(self, pattern: str) -> Optional[re.Pattern]:
        """Get compiled regex pattern from cache or compile new one."""
        pattern_lower = pattern.lower()
        
        if pattern_lower in self._pattern_cache:
            return self._pattern_cache[pattern_lower]
        
        # Clean cache if it gets too large
        if len(self._pattern_cache) >= self._cache_size_limit:
            self._pattern_cache.clear()
        
        try:
            regex_pattern = self._pattern_to_regex(pattern_lower)
            compiled = re.compile(regex_pattern)
            self._pattern_cache[pattern_lower] = compiled
            return compiled
        except re.error as e:
            logger.warning(f"Invalid regex pattern '{pattern}': {e}")
            return None
    
    def _pattern_to_regex(self, pattern: str) -> str:
        """Convert an origin pattern to a regex pattern."""
        # Escape special regex characters except * which we'll handle
        escaped = re.escape(pattern)
        
        # Replace escaped wildcards with regex patterns
        # \* becomes .* (match any characters)
        regex_pattern = escaped.replace(r"\*", ".*")
        
        # Ensure full match from start to end
        return f"^{regex_pattern}$"
    
    def validate_origins_format(self, origins: str) -> Dict[str, Any]:
        """
        Validate the format of origins configuration string.
        
        Args:
            origins: Comma-separated list of origin patterns
            
        Returns:
            Dict with validation result and details
        """
        if not origins or origins.strip() == "":
            return {
                "is_valid": True,
                "message": "Empty origins (allows all)",
                "parsed_origins": []
            }
        
        try:
            origins_list = self._parse_origins_list(origins)
            invalid_patterns = []
            
            for origin in origins_list:
                if not self._validate_single_origin_pattern(origin):
                    invalid_patterns.append(origin)
            
            if invalid_patterns:
                return {
                    "is_valid": False,
                    "message": f"Invalid origin patterns: {', '.join(invalid_patterns)}",
                    "parsed_origins": origins_list,
                    "invalid_patterns": invalid_patterns
                }
            
            return {
                "is_valid": True,
                "message": f"Valid origins configuration with {len(origins_list)} patterns",
                "parsed_origins": origins_list
            }
            
        except Exception as e:
            return {
                "is_valid": False,
                "message": f"Error parsing origins: {str(e)}",
                "parsed_origins": []
            }
    
    def _validate_single_origin_pattern(self, pattern: str) -> bool:
        """Validate a single origin pattern format."""
        if pattern == "*":
            return True
        
        # Basic URL structure validation
        if not (pattern.startswith("http://") or 
                pattern.startswith("https://") or 
                pattern.startswith("*://")):
            return False
        
        # Try to parse as URL (with wildcard handling)
        try:
            test_pattern = pattern.replace("*", "test")
            parsed = urlparse(test_pattern)
            return bool(parsed.netloc)
        except Exception:
            return False
    
    def get_origins_suggestions(self, current_origins: str) -> List[str]:
        """
        Get suggestions for common origin patterns.
        
        Args:
            current_origins: Current origins configuration
            
        Returns:
            List of suggested origin patterns
        """
        suggestions = [
            "https://localhost:3000",  # Common dev server
            "https://localhost:8080",  # Another common dev server
            "https://*.vercel.app",    # Vercel deployments
            "https://*.netlify.app",   # Netlify deployments
            "https://*.github.io",     # GitHub Pages
            "*"                        # Allow all (not recommended for production)
        ]
        
        # Filter out patterns that are already configured
        if current_origins:
            current_list = self._parse_origins_list(current_origins)
            suggestions = [s for s in suggestions if s not in current_list]
        
        return suggestions


# Global instance
origins_service = OriginsService()