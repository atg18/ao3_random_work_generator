"""
Search result caching layer with staleness tracking.
Stores results in a JSON file with timestamps for TTL management.
"""

import json
import os
import hashlib
import time
from typing import Optional, Dict, Any, List

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
CACHE_FILE = os.path.join(CACHE_DIR, 'search_results.json')
DEFAULT_TTL_SECONDS = 3600  # 1 hour


def _ensure_cache_dir():
    """Create cache directory if it doesn't exist."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)


def get_cache_key(tags: List[str], categories: List[str], fandom: str) -> str:
    """
    Generate a normalized, deterministic cache key from search parameters.
    Sorts lists to ensure ['A', 'B'] == ['B', 'A'].
    """
    normalized = {
        'tags': sorted([t.lower().strip() for t in tags]) if tags else [],
        'categories': sorted(categories) if categories else [],
        'fandom': fandom.lower().strip() if fandom else ''
    }
    key_str = json.dumps(normalized, sort_keys=True)
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]


def _load_cache() -> Dict[str, Any]:
    """Load the entire cache file."""
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_cache(cache: Dict[str, Any]):
    """Save the entire cache file."""
    _ensure_cache_dir()
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f)
    except IOError:
        pass  # Fail silently - caching is best-effort


def get_cached_results(cache_key: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached results for a given key.
    
    Returns:
        dict with 'results' and 'stale' flag, or None if no cache exists.
        Results are marked stale if older than TTL but still returned.
    """
    cache = _load_cache()
    entry = cache.get(cache_key)
    
    if not entry:
        return None
    
    results = entry.get('results')
    timestamp = entry.get('timestamp', 0)
    age = time.time() - timestamp
    is_stale = age > ttl_seconds
    
    return {
        'results': results,
        'stale': is_stale,
        'age_seconds': int(age)
    }


def set_cached_results(cache_key: str, results: List[Dict[str, Any]]):
    """
    Store search results in cache with current timestamp.
    
    Args:
        cache_key: The normalized cache key
        results: List of work results to cache
    """
    cache = _load_cache()
    cache[cache_key] = {
        'results': results,
        'timestamp': time.time()
    }
    _save_cache(cache)


def clear_cache():
    """Clear all cached results."""
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
