"""
AO3 Browser-based scraper using Playwright.
Uses a headless Chromium browser to bypass Cloudflare protections.
Includes a request queue to limit concurrent browser instances.
"""

import asyncio
import random
import re
from typing import Dict, Any, List, Optional
from playwright.async_api import async_playwright, Browser, Page
import threading

# Global lock for one-at-a-time processing
_browser_lock = threading.Lock()
_browser = None
_playwright = None

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
        tag_str = ",".join(tags[:3])  # Limit to 3 tags
        params.append(f"work_search[other_tag_names]={tag_str}")
    
    if fandom:
        # Quote fandom to handle special chars like (TV)
        clean = fandom.strip('"')
        params.append(f'work_search[fandom_names]="{clean}"')
    
    for cat in categories:
        if cat in CATEGORY_MAP:
            params.append(f"work_search[category_ids][]={CATEGORY_MAP[cat]}")
    
    return base + "&".join(params)


def search_ao3_sync(tags: List[str], categories: List[str], fandom: str) -> Dict[str, Any]:
    """
    Synchronous wrapper for browser-based AO3 search.
    Uses a lock to ensure only one browser instance runs at a time.
    """
    with _browser_lock:
        return asyncio.run(_search_ao3_async(tags, categories, fandom))


async def _search_ao3_async(tags: List[str], categories: List[str], fandom: str) -> Dict[str, Any]:
    """
    Perform AO3 search using Playwright headless browser.
    Returns a random work from the results.
    """
    playwright = None
    browser = None
    
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Set a realistic user agent
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        
        # Step 1: Get first page to find total pages
        url = build_search_url(tags, categories, fandom, page=1)
        await page.goto(url, timeout=30000)
        
        # Wait for content (either works or "0 Found")
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
            
            # Extract total pages
            match = re.search(r'of\s+([0-9,]+)\s+Works', heading_text or "")
            if match:
                total_works = int(match.group(1).replace(",", ""))
                total_pages = (total_works + 19) // 20  # ceil division
            else:
                total_pages = 1
        else:
            total_pages = 1
        
        # Step 2: Pick a random page (cap at 100 for speed)
        max_page = min(total_pages, 100)
        random_page = random.randint(1, max_page)
        
        # If not on the random page, navigate to it
        if random_page > 1:
            url = build_search_url(tags, categories, fandom, page=random_page)
            await page.goto(url, timeout=30000)
            await page.wait_for_selector('.work.blurb', timeout=15000)
        
        # Step 3: Extract works from the page
        works = await page.query_selector_all('.work.blurb')
        
        if not works:
            return {"error": "No works found on page"}
        
        # Pick a random work
        work_el = random.choice(works)
        
        # Extract work details
        title_el = await work_el.query_selector('h4.heading a')
        title = await title_el.text_content() if title_el else "Unknown"
        href = await title_el.get_attribute('href') if title_el else ""
        
        author_els = await work_el.query_selector_all('a[rel="author"]')
        authors = []
        for a in author_els:
            authors.append(await a.text_content())
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
        
    except Exception as e:
        return {"error": f"Browser error: {str(e)}"}
    
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
