"""
API Client module with advanced features:
- Connection pooling via requests.Session()
- Retry logic with exponential backoff
- Response caching with TTL
- Type hints
- Structured logging
"""

import requests
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global session for connection pooling
_session: Optional[requests.Session] = None
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_DIR = Path('cache')


def get_session() -> requests.Session:
    """
    Get or create a session with connection pooling and retry strategy.
    Uses HTTPAdapter with Retry strategy for automatic retries.
    """
    global _session
    
    if _session is None:
        _session = requests.Session()
        
        # Retry strategy: exponential backoff
        retry_strategy = Retry(
            total=3,  # Total retries
            status_forcelist=[429, 500, 502, 503, 504],  # Retry on these status codes
            allowed_methods=["HEAD", "GET", "POST", "OPTIONS"],  # Updated parameter name
            backoff_factor=1  # Exponential backoff: 1s, 2s, 4s
        )
        
        # Mount adapter to both http and https
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        _session.mount("http://", adapter)
        _session.mount("https://", adapter)
        
        logger.info("✅ Created session with connection pooling and retry strategy")
    
    return _session


def _init_cache_dir() -> None:
    """Create cache directory if it doesn't exist."""
    CACHE_DIR.mkdir(exist_ok=True)


def _get_cache_key(url: str, params: Optional[Dict] = None) -> str:
    """Generate cache key from URL and params."""
    if params:
        params_str = json.dumps(params, sort_keys=True)
        return f"{url}_{hash(params_str)}"
    return url


def _is_cache_valid(cache_key: str, ttl_seconds: int = 3600) -> bool:
    """Check if cache entry is still valid."""
    if cache_key not in _cache:
        return False
    
    cached_data = _cache[cache_key]
    timestamp = cached_data.get('timestamp')
    
    if timestamp is None:
        return False
    
    age = (datetime.now() - timestamp).total_seconds()
    is_valid = age < ttl_seconds
    
    if not is_valid:
        logger.debug(f"Cache expired for {cache_key}: {age:.0f}s old (TTL: {ttl_seconds}s)")
    
    return is_valid


def get_json(
    url: str,
    params: Optional[Dict] = None,
    timeout: int = 10,
    use_cache: bool = True,
    cache_ttl: int = 3600,
    headers: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    GET request with retry logic, connection pooling, and caching.
    
    Args:
        url: Request URL
        params: Query parameters
        timeout: Request timeout in seconds
        use_cache: Whether to use cache
        cache_ttl: Cache TTL in seconds (default 1 hour)
        headers: Custom headers
        
    Returns:
        JSON response as dict
        
    Raises:
        requests.RequestException: If request fails after retries
    """
    cache_key = _get_cache_key(url, params)
    
    # Check cache
    if use_cache and _is_cache_valid(cache_key, cache_ttl):
        logger.debug(f"Cache hit for {url}")
        return _cache[cache_key]['data']
    
    session = get_session()
    
    try:
        logger.debug(f"GET {url} (params: {params})")
        response = session.get(url, params=params, timeout=timeout, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        # Store in cache
        if use_cache:
            _cache[cache_key] = {
                'data': data,
                'timestamp': datetime.now(),
                'status_code': response.status_code
            }
            logger.debug(f"Cached response for {url} (TTL: {cache_ttl}s)")
        
        return data
        
    except requests.exceptions.Timeout:
        logger.error(f"Timeout on GET {url}")
        raise
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error {e.response.status_code} on GET {url}: {e.response.text}")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error on GET {url}: {e}")
        raise


def post_json(
    url: str,
    json_data: Dict[str, Any],
    timeout: int = 10,
    headers: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    POST request with retry logic and connection pooling.
    
    Args:
        url: Request URL
        json_data: JSON body
        timeout: Request timeout in seconds
        headers: Custom headers
        
    Returns:
        JSON response as dict
        
    Raises:
        requests.RequestException: If request fails after retries
    """
    session = get_session()
    
    try:
        logger.debug(f"POST {url}")
        response = session.post(url, json=json_data, timeout=timeout, headers=headers)
        response.raise_for_status()
        
        return response.json()
        
    except requests.exceptions.Timeout:
        logger.error(f"Timeout on POST {url}")
        raise
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error {e.response.status_code} on POST {url}")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error on POST {url}: {e}")
        raise


def clear_cache() -> None:
    """Clear all cached data."""
    global _cache
    _cache.clear()
    logger.info("Cache cleared")


def cache_stats() -> Dict[str, int]:
    """Get cache statistics."""
    return {
        'entries': len(_cache),
        'expired': sum(1 for k in _cache if not _is_cache_valid(k))
    }


# Initialize cache directory on import
_init_cache_dir()
