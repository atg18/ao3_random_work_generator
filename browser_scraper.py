"""
AO3 Browser-based scraper using Playwright.
Uses a PERSISTENT browser with multiple concurrent tabs.
Much faster than launching a new browser for each request.
"""

import asyncio
import random
import re
import threading
from typing import Dict, Any, List
from playwright.async_api import async_playwright, Browser, BrowserContext

# Configuration
MAX_CONCURRENT_SEARCHES = 3  # How many searches can run at once
BROWSER_TIMEOUT = 30000  # 30 seconds

# Global state
_playwright = None
_browser: Browser = None
_browser_lock = threading.Lock()
_semaphore = None

# Category mapping
CATEGORY_MAP = {
    "F/F": "116",
    "F/M": "22",
    "M/M": "23",
    "Multi": "2246",
    "Other": "24",
    "Gen": "21"
}


def build_search_url(tags: List[str], categories: List[str], fandom: str, page: int = 1) -> str:
    """Build AO3 search URL with proper encoding."""
    base = "https://archiveofourown.org/works/search?"
    params = ["work_search[language_id]=en", f"page={page}"]
    
    if tags:
        tag_str = ",".join(tags[:3])
        params.append(f"work_search[other_tag_names]={tag_str}")
    
    if fandom:
        clean = fandom.strip('"')
        params.append(f'work_search[fandom_names]="{clean}"')
    
    for cat in categories:
        if cat in CATEGORY_MAP:
            params.append(f"work_search[category_ids][]={CATEGORY_MAP[cat]}")
    
    return base + "&".join(params)


async def _get_browser():
    """Get or create the persistent browser instance."""
    global _playwright, _browser, _semaphore
    
    if _browser is None or not _browser.is_connected():
        if _playwright is None:
            _playwright = await async_playwright().start()
        
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=['--disable-dev-shm-usage', '--no-sandbox']
        )
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT_SEARCHES)
    
    return _browser


async def _extract_work_details(work_el) -> Dict[str, Any]:
    """Extract work details from a work blurb element."""
    title_el = await work_el.query_selector('h4.heading a')
    title = await title_el.text_content() if title_el else "Unknown"
    href = await title_el.get_attribute('href') if title_el else ""
    
    author_els = await work_el.query_selector_all('a[rel="author"]')
    authors = [await a.text_content() for a in author_els]
    author = ", ".join(authors) if authors else "Anonymous"
    
    rating_el = await work_el.query_selector('.rating span')
    rating = await rating_el.text_content() if rating_el else "?"
    
    words_el = await work_el.query_selector('dd.words')
    words = await words_el.text_content() if words_el else "Unknown"
    words = words.replace(",", "") if words else "Unknown"
    
    work_url = f"https://archiveofourown.org{href}" if href else ""
    
    return {
        "title": title.strip() if title else "Unknown",
        "author": author.strip() if author else "Anonymous",
        "url": work_url,
        "rating": rating.strip() if rating else "?",
        "word_count": words.strip() if words else "Unknown",
        "source": "live"
    }


def search_ao3_sync(tags: List[str], categories: List[str], fandom: str) -> Dict[str, Any]:
    """Synchronous wrapper for browser-based AO3 search."""
    with _browser_lock:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_search_ao3_async(tags, categories, fandom))
        finally:
            loop.close()


async def _search_ao3_async(tags: List[str], categories: List[str], fandom: str) -> Dict[str, Any]:
    """
    Perform AO3 search using a new browser context (tab).
    Uses semaphore to limit concurrent searches.
    """
    try:
        browser = await _get_browser()
        
        # Wait for a slot if all are busy
        async with _semaphore:
            # Create a new context (like a new incognito tab)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            
            try:
                # Step 1: Get first page to find total pages
                url = build_search_url(tags, categories, fandom, page=1)
                await page.goto(url, timeout=BROWSER_TIMEOUT)
                
                # Wait for content
                try:
                    await page.wait_for_selector('.work.blurb, h3.heading', timeout=15000)
                except:
                    return {"error": "AO3 page load timeout"}
                
                # Check for 0 results
                heading = await page.query_selector('h3.heading')
                if heading:
                    heading_text = await heading.text_content()
                    if heading_text and "0 Found" in heading_text:
                        return {"error": "No works found matching the selected filters."}
                    
                    match = re.search(r'of\s+([0-9,]+)\s+Works', heading_text or "")
                    if match:
                        total_works = int(match.group(1).replace(",", ""))
                        total_pages = (total_works + 19) // 20
                    else:
                        total_pages = 1
                else:
                    total_pages = 1
                
                # Step 2: Pick a random page (cap at 100 for speed)
                max_page = min(total_pages, 100)
                random_page = random.randint(1, max_page)
                
                # Store page 1 works in case random page times out
                page1_works = await page.query_selector_all('.work.blurb')
                
                if random_page > 1:
                    try:
                        url = build_search_url(tags, categories, fandom, page=random_page)
                        await page.goto(url, timeout=BROWSER_TIMEOUT)
                        await page.wait_for_selector('.work.blurb', timeout=15000)
                    except:
                        # Random page timed out - fallback to page 1 results
                        if page1_works:
                            work_el = random.choice(page1_works)
                            return await _extract_work_details(work_el)
                        return {"error": "AO3 page load timeout"}
                
                # Step 3: Extract works
                works = await page.query_selector_all('.work.blurb')
                
                if not works:
                    # Fallback to page 1 if current page is empty
                    if page1_works:
                        works = page1_works
                    else:
                        return {"error": "No works found on page"}
                
                work_el = random.choice(works)
                
                # Extract and return work details
                return await _extract_work_details(work_el)
                
            finally:
                await context.close()
                
    except Exception as e:
        return {"error": f"Browser error: {str(e)}"}
