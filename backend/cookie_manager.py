"""
NSE Cookie Manager
------------------
Manages NSE session cookies with a two-tier strategy:

1. **Environment variable** (preferred): Set `NSE_COOKIES` with a semicolon-separated
   cookie string from your browser's DevTools. Zero RAM cost, works on any host.

2. **Playwright fallback**: If `NSE_COOKIES` is not set, attempts to launch a headless
   Chromium browser to fetch cookies automatically. Requires ~300-500MB RAM.

Usage:
    from backend.cookie_manager import CookieManager

    cookie_str = await CookieManager.get_cookies()           # Returns cached or fresh cookies
    cookie_str = await CookieManager.get_cookies(force=True) # Forces a refresh
"""

import asyncio
import logging
import time
import os
from typing import Optional

# Ensure Playwright looks for browsers in the local directory (critical for Render)
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

logger = logging.getLogger(__name__)

# How long (seconds) cookies stay valid before auto-refresh
COOKIE_TTL_SECONDS = 90 * 60  # 90 minutes

# URLs to warm up in sequence before capturing cookies
WARMUP_SEQUENCE = [
    "https://www.nseindia.com",
    "https://www.nseindia.com/option-chain",
]


class CookieManager:
    """Thread-safe async singleton that manages NSE session cookies."""

    _cookie_string: Optional[str] = None
    _fetched_at: float = 0.0
    _lock: asyncio.Lock = asyncio.Lock()
    _playwright_available: Optional[bool] = None  # cached capability check
    _source: str = "none"  # Track where cookies came from: "env", "playwright", "none"

    @classmethod
    async def get_cookies(cls, force: bool = False) -> Optional[str]:
        """
        Return a valid NSE cookie string.

        Priority:
          1. NSE_COOKIES environment variable (always checked first on force/stale)
          2. Playwright headless browser (fallback)
          3. Previously cached cookies (last resort)

        Args:
            force: If True, bypass cache and refresh immediately.

        Returns:
            A semicolon-separated cookie string ready to use in the Cookie header,
            or None if all refresh attempts fail.
        """
        async with cls._lock:
            age = time.time() - cls._fetched_at
            is_stale = age >= COOKIE_TTL_SECONDS

            if not force and cls._cookie_string and not is_stale:
                logger.debug(f"Using cached NSE cookies (age: {age:.0f}s, source: {cls._source})")
                return cls._cookie_string

            reason = "forced refresh" if force else ("stale/expired" if is_stale else "first fetch")
            logger.info(f"Refreshing NSE cookies ({reason})...")

            # --- Strategy 1: Environment variable ---
            env_cookies = os.environ.get("NSE_COOKIES", "").strip()
            if env_cookies:
                cls._cookie_string = env_cookies
                cls._fetched_at = time.time()
                cls._source = "env"
                logger.info(f"Using NSE cookies from NSE_COOKIES env var ({len(env_cookies)} chars).")
                return cls._cookie_string

            # --- Strategy 2: Playwright headless browser ---
            new_cookies = await cls._fetch_via_playwright()
            if new_cookies:
                cls._cookie_string = new_cookies
                cls._fetched_at = time.time()
                cls._source = "playwright"
                logger.info("NSE cookies refreshed successfully via Playwright.")
                return cls._cookie_string

            # --- Fallback: reuse old cookies if they exist ---
            if cls._cookie_string:
                logger.warning("All refresh methods failed; reusing existing cookies.")
                return cls._cookie_string

            logger.error("Could not obtain NSE cookies via any method.")
            return None

    @classmethod
    async def _fetch_via_playwright(cls) -> Optional[str]:
        """Launch a headless Chromium browser, warm up NSE, and capture cookies."""
        try:
            from playwright.async_api import async_playwright, TimeoutError as PWTimeout
        except ImportError:
            if cls._playwright_available is not False:
                logger.warning(
                    "Playwright not installed. "
                    "Set NSE_COOKIES env var, or run: pip install playwright && playwright install chromium"
                )
                cls._playwright_available = False
            return None

        cls._playwright_available = True

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )

                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/151.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                    viewport={"width": 1280, "height": 800},
                    extra_http_headers={
                        "Accept-Language": "en-US,en;q=0.7",
                        "sec-gpc": "1",
                    },
                )

                page = await context.new_page()

                # Step through the warm-up sequence
                for url in WARMUP_SEQUENCE:
                    try:
                        logger.debug(f"Warming up: {url}")
                        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                        await asyncio.sleep(2)
                    except PWTimeout:
                        logger.warning(f"Timeout warming up {url}, continuing...")
                    except Exception as e:
                        logger.warning(f"Error warming up {url}: {e}, continuing...")

                # Capture all cookies from the context
                cookies = await context.cookies()
                await browser.close()

                if not cookies:
                    logger.warning("Playwright returned no cookies.")
                    return None

                cookie_str = "; ".join(
                    f"{c['name']}={c['value']}" for c in cookies
                )
                logger.info(f"Captured {len(cookies)} cookies from NSE.")
                return cookie_str

        except Exception as e:
            logger.error(f"Playwright browser session failed: {e}")
            return None

    @classmethod
    def invalidate(cls) -> None:
        """
        Mark cookies as invalid so the next call to get_cookies() triggers a refresh.
        Call this when you receive a non-200 response from NSE.
        """
        cls._fetched_at = 0.0
        logger.info("NSE cookie cache invalidated.")

    @classmethod
    def is_available(cls) -> bool:
        """Returns True if Playwright is installed and usable."""
        return cls._playwright_available is not False

    @classmethod
    def get_source(cls) -> str:
        """Returns the source of current cookies: 'env', 'playwright', or 'none'."""
        return cls._source
