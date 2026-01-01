"""
AO3 search service with robust request handling.
Implements: connection pooling, retries with exponential backoff, longer timeouts, caching.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import random
import re
import math
import time
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

# Import cache module
from search_cache import get_cache_key, get_cached_results, set_cached_results

AO3_BASE_URL = "https://archiveofourown.org"
SEARCH_URL = "https://archiveofourown.org/works/search"

# Timeouts - increased for AO3's slow responses
TIMEOUT = 60  # seconds

# Retry configuration
MAX_RETRIES = 3
BACKOFF_FACTOR = 2  # exponential backoff: 2s, 4s, 8s
REQUEST_DELAY = 1.0  # seconds between requests

# User-Agent header
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# Category IDs
CATEGORY_MAP = {
    "F/F": "116",
    "F/M": "22",
    "M/M": "23",
    "Multi": "2246",
    "Other": "24",
    "Gen": "21"
}

# Global session for connection pooling
_session = None

def get_session() -> requests.Session:
    """Get or create session with connection pooling and retry logic."""
    global _session
    if _session is None:
        _session = requests.Session()
        retry = Retry(total=MAX_RETRIES, backoff_factor=BACKOFF_FACTOR, 
                      status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        _session.mount("https://", adapter)
        _session.headers.update(HEADERS)
    return _session


class AO3ErrorType(Enum):
    """Classification of AO3 errors for fallback logic."""
    NONE = "none"
    TIMEOUT = "timeout"
    EMPTY_RESPONSE = "empty_response"
    NETWORK_ERROR = "network_error"
    PARSE_ERROR = "parse_error"
    HTTP_ERROR = "http_error"


def build_search_params(tags, categories, fandom_filter, page=1):
    """Constructs the query parameters for the AO3 search URL."""
    return {
        "commit": "Search",
        "work_search[query]": "",
        "work_search[other_tag_names]": ",".join(tags) if tags else "",
        "work_search[fandom_names]": f'"{fandom_filter.strip('"' )}"' if fandom_filter else "",
        "work_search[category_ids][]": [CATEGORY_MAP[c] for c in categories if c in CATEGORY_MAP],
        "work_search[language_id]": "en",
        "page": page
    }


def get_page_count(tags, categories, fandom_filter) -> Tuple[int, AO3ErrorType]:
    """
    Queries AO3 to find the total number of pages for the given filters.
    
    Returns:
        Tuple of (page_count, error_type)
        - page_count: Total pages (1+), 0 if no results, -1 on error
        - error_type: Classification of any error that occurred
    """
    params = build_search_params(tags, categories, fandom_filter, page=1)
    
    try:
        session = get_session()
        response = session.get(
            SEARCH_URL, 
            params=params, 
            timeout=TIMEOUT
        )
        
        if response.status_code != 200:
            print(f"Error fetching page count: Status {response.status_code}")
            return -1, AO3ErrorType.HTTP_ERROR

        # Check for empty response
        if len(response.content) == 0:
            return -1, AO3ErrorType.EMPTY_RESPONSE

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Check for "0 Found"
        heading = soup.find("h3", class_="heading")
        if heading and "0 Found" in heading.text:
            return 0, AO3ErrorType.NONE

        # Extract total works count from text like "1 - 20 of 1,234 Works"
        meta_group = soup.find("h3", class_="heading")
        if meta_group:
            text = meta_group.get_text().strip()
            match = re.search(r'of\s+([0-9,]+)\s+Works', text)
            if match:
                total_works = int(match.group(1).replace(",", ""))
                # Calculate total pages: ceil(total_works / 20)
                return math.ceil(total_works / 20), AO3ErrorType.NONE
        
        # If the text format is different (e.g., single page result), assume 1 page
        return 1, AO3ErrorType.NONE
        
    except requests.exceptions.Timeout:
        print("AO3 page count request timed out")
        return -1, AO3ErrorType.TIMEOUT
    except requests.exceptions.RequestException as e:
        print(f"Network error in get_page_count: {e}")
        return -1, AO3ErrorType.NETWORK_ERROR
    except Exception as e:
        print(f"Parse error in get_page_count: {e}")
        return -1, AO3ErrorType.PARSE_ERROR


def fetch_random_work(tags, categories, fandom_filter, total_pages) -> Tuple[Optional[Dict[str, Any]], AO3ErrorType]:
    """
    Selects a random page, fetches it, and picks a random work from that page.
    
    Returns:
        Tuple of (work_dict or None, error_type)
    """
    # Cap pages at 200 to prevent timeouts from deep pagination
    max_page = min(total_pages, 200)
    random_page = random.randint(1, max_page)
    
    params = build_search_params(tags, categories, fandom_filter, page=random_page)

    try:
        # Rate limiting delay
        time.sleep(REQUEST_DELAY)
        
        session = get_session()
        response = session.get(
            SEARCH_URL, 
            params=params, 
            timeout=TIMEOUT
        )
        
        if response.status_code != 200:
            return None, AO3ErrorType.HTTP_ERROR

        if len(response.content) == 0:
            return None, AO3ErrorType.EMPTY_RESPONSE

        soup = BeautifulSoup(response.text, 'html.parser')
        work_blurbs = soup.find_all("li", class_="work")

        if not work_blurbs:
            return None, AO3ErrorType.PARSE_ERROR

        valid_works = []
        for work in work_blurbs:
            try:
                # Basic scraping safety checks
                heading = work.find("h4", class_="heading")
                if not heading: continue
                
                link = heading.find("a")
                if not link: continue
                
                work_id = link['href'].split("/")[-1]
                # Ensure it's a work ID and not a series or user link
                if not work_id.isdigit(): continue 

                # Author extraction
                author_tags = heading.find_all("a", rel="author")
                author = ", ".join([a.text for a in author_tags]) if author_tags else "Anonymous"

                # Word Count extraction
                stats = work.find("dl", class_="stats")
                words = "Unknown"
                if stats:
                    word_dd = stats.find("dd", class_="words")
                    if word_dd: words = word_dd.text.replace(",", "")

                # Rating extraction
                req_tags = work.find("ul", class_="required-tags")
                rating = "?"
                if req_tags:
                    rating_span = req_tags.find("span", class_="rating")
                    if rating_span:
                        rating = rating_span.get_text().strip()

                valid_works.append({
                    "title": link.text,
                    "author": author,
                    "url": f"{AO3_BASE_URL}/works/{work_id}",
                    "rating": rating,
                    "word_count": words
                })
            except Exception:
                continue

        if not valid_works:
            return None, AO3ErrorType.PARSE_ERROR

        return random.choice(valid_works), AO3ErrorType.NONE

    except requests.exceptions.Timeout:
        print("AO3 fetch work request timed out")
        return None, AO3ErrorType.TIMEOUT
    except requests.exceptions.RequestException as e:
        print(f"Network error in fetch_random_work: {e}")
        return None, AO3ErrorType.NETWORK_ERROR
    except Exception as e:
        print(f"Exception in fetch_random_work: {e}")
        return None, AO3ErrorType.PARSE_ERROR


def get_random_work_with_fallback(tags: List[str], categories: List[str], fandom: str) -> Dict[str, Any]:
    """
    Main orchestration function with cascading fallback.
    
    Flow:
    1. Try live AO3 search (fast timeout)
    2. On AO3 error → try cached results
    3. If no cache → try web search fallback
    
    Returns:
        Dict with keys:
        - result: The work dict (or None)
        - source: "live" | "cache" | "indexed"
        - stale: True if cached results are past TTL
        - error: Error message if all fallbacks fail
        - fallback_reason: Why fallback was used (e.g., "ao3_timeout")
    """
    cache_key = get_cache_key(tags, categories, fandom)
    
    # Step 1: Try live AO3
    page_count, page_error = get_page_count(tags, categories, fandom)
    
    if page_error == AO3ErrorType.NONE and page_count > 0:
        work, work_error = fetch_random_work(tags, categories, fandom, page_count)
        
        if work_error == AO3ErrorType.NONE and work:
            # Success! Cache and return
            set_cached_results(cache_key, [work])
            return {
                "result": work,
                "source": "live",
                "stale": False,
                "error": None,
                "fallback_reason": None
            }
        
        # Work fetch failed - use fallback
        fallback_reason = _error_to_reason(work_error)
    elif page_count == 0:
        # No results found - this is not an error, just empty
        return {
            "result": None,
            "source": "live",
            "stale": False,
            "error": "No works found matching the selected filters.",
            "fallback_reason": None
        }
    else:
        # Page count failed - use fallback
        fallback_reason = _error_to_reason(page_error)
    
    # Step 2: Try cached results
    cached = get_cached_results(cache_key)
    if cached and cached.get('results'):
        results = cached['results']
        work = random.choice(results) if isinstance(results, list) else results
        return {
            "result": work,
            "source": "cache",
            "stale": cached.get('stale', True),
            "error": None,
            "fallback_reason": fallback_reason
        }
    
    # No more fallbacks - return error
    return {
        "result": None,
        "source": None,
        "stale": False,
        "error": "AO3 is currently slow or unavailable. Please try again in a few moments.",
        "fallback_reason": fallback_reason
    }


def _error_to_reason(error_type: AO3ErrorType) -> str:
    """Convert error type to user-friendly fallback reason."""
    mapping = {
        AO3ErrorType.TIMEOUT: "ao3_timeout",
        AO3ErrorType.EMPTY_RESPONSE: "ao3_empty_response",
        AO3ErrorType.NETWORK_ERROR: "network_error",
        AO3ErrorType.HTTP_ERROR: "ao3_http_error",
        AO3ErrorType.PARSE_ERROR: "ao3_parse_error",
    }
    return mapping.get(error_type, "unknown_error")