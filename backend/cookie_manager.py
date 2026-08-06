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

# --- HARDCODED COOKIE ---
# Paste your NSE cookie string inside the quotes below
HARDCODED_COOKIE = "browse-url=%2Fmarket-data%2Fclosing-auction-session; AKA_A2=A; _abck=DA0EA27AA4F463B429FB3AC865AC6FF4~0~YAAQtJUjFxZDkqSfAQAAJHD01xCY4WDx2u0n7quFxRQSoP2z9rzqaURDEA7WB7hjj8rMQMyncom9ZzvcIXDnv+YvydQczeZDb4ZIN9Ddex1ZVKepEcQvEani0o+UL4b1TR7PbxF8TIafVk7N41uNjd19MVvVREPvu4dYT8C9gccJgMr+UiIFNfIe/2ByZoQqCjU3J8jXdm2/E5J28nLYA8/T06PWZgYJxqtS7yGylzt83Nn473tPCB5XDiGWG1B1/ouaVBMsdHyENDer1/4YGQSh1RP2sZ4CJv2kGtqPnCZc+x+60/jnM9cYrRGbUQeHhJKKb661afoqDQ6HDZKKwWf2NpVbJ1lF8ZWbsVKXHQgUg1OMWIGuVw/08QNIQdAcUbDlpG4Tgl21y4PkplPs8CblBTa53fmDc5qw5s94zrTgvXa5sB8IFfH2sR+Bk0xUx9EqsBpefbX/ERAvYxVVl5rAUGmYvZB+PGmULcr1pBeSndHkfJ4+BJqbIE73Q0iZrODZfJp7qm1brfoiIdlrGSTLm76lX0Kitk4Gmh4qIsthdzOFV0DmLSMVbaFMywZpJLC21gbzBKKr3Tv5r3db87J0I0/7HGTr1VofJDeWn+S88YV9teNBgdnklj74ueRtvtoYouoKyQ6zDMvzEuN/qnFwDyUQx7fOV1I4TwVm3Yijwik8PBiRYNQc2Hf68mzXblG3~-1~-1~-1~AAQAAAAG%2f%2f%2f%2f%2f2eAmmTUyQ1O2g1NTIKTO%2fAaWhb0DWbvDNs6MA5Ro3f%2fXskvBcXQrZ75CshfxjdpYcNWDZHlNRWqKLALJCrmW7DwNNM+hiegI2nB+FnUR75MPsqJiV2KG6%2f2Aht0yxEiAFtTw7M%3d~-1; bm_mi=7A5A66C6474FBE9C51963064CC7F865D~YAAQtJUjF+FEkqSfAQAAD5H01wDH0BSxvskWQrhpTguAHMPDZrZshP2ByWu3flj6TsfTU/2vqCAtyur2kZiytbLsO0hgqwgP6JOPnEHt1JAecOn0O9A57e8PatM87IMJhn7CJv6mwh+FCdzT2y9j7sYYxoXOvvqnL30RQbEijM1DwOABHn2ep5Ou0MKmPW+4P/c8fE/Ae5wWLS55WUdp6QNDmhNuQ6BArdkahTcdKtlJPe11b7UBTRrPbURHeRYTK4vZFdPeQLCT/ObTFelyBnZOh/7vrQJ/6LY8WGo4PdgRAVlBSNHcPBkk0BevlzcbpKvVpTLsaBvfhR+W~1; bm_sz=592BBFD86B42CCDC978A3BFBE45B153B~YAAQtJUjF+NEkqSfAQAAD5H01wDeEwfuq4wbefPc0mci5NUaA0/UiWizcNDBo4JcJyWxXvnN/8FaY+VUv9s1bR/h9gYXlncT2CkIS99KOHax8g2aGnP04J+O7e3NUdBd09iY+zdFMEb6lyzzCyfKeAvZ6ul+RWk3R88MVxL95ObdEAA8CdlR4Zm/JJ/5ed780YVYPd8IYzaWVp+LvIpTn3UrGmvhxjpB2n0drYv2T/zKqeUKtZWU0CQozUUxJbRYHQE7oyvzZbszWyA9MB/DfjPuq8P7AiF55ARq2z9UYN+SQ5A3gLHefRRSzRvQskXDUpoq8AsUSJGjCn0jVhh5W2v5brVcNgzjiTeF/rOhnAwc3UtHnQO0uZUObpaRt+JBwSj+txijxR8bXXSknhlys0joom0XTjtR4h3r0r6oBW0RDzIFBeOYSUZGPXKax2NI9E0=~3486772~4405045; ak_bmsc=EDE797A72FF7714F72790D4074D0B298~000000000000000000000000000000~YAAQtJUjFwBFkqSfAQAACJL01wC/gH+JHR7vRGpi/cO5bfp51Z4CKdyaYAHxpTc4+LWqxb1m81SCNeGyBaexcN/dLWOMPIX2D2qryW73ZPOmIL8VdMDEb9vqVxMywwYtzQ5pIsLlKM7p1Jw9yZLZQ5Xywzw0ariLx5P82M5YkMRYFo6jmj7k44WKf/7ogGBKoh/0n4+pSW+answNLQBGE+ja2mpIs/u7jNN3auRdZTJ+GhIMTt+MxA6jmthLQ/Na6aonV3YHgeU+7agT7y6VUn1wKhNKh6vaVBvJ0x6k8qT9km+sgA4aSCkeRgp9IZAxDFrJhEmY/yMPHhY17F9p+NrksWdCX2ZGgAMQqs+mmhGbBoTcjMzqAAQqWL0IrTW9ESJ549IQFjHHynsldrgBe3THBjw7Qi1apNUyuPeTMGMN2qiQxPtZ8t2bITaSWJZS5d8Rq/IInvf3B+WL1BGDLQR63NcLFTXxTjvW3TDCWLZkV4Fe8mh9sWMkSehpxl0D4D4Lld0=; bm_sv=26FA9A37601EAB9B9CEE126EE272F1D8~YAAQtJUjF0JFkqSfAQAACJX01wBAAxqhJFNpAimAg/JFfM9QyIM7X8T1yI8H4v6TNmKrXtBLGb47NIwT18krl+/e9KbogrKnCzwzjzyhNfsARl7wYKv5CWIukNwcWNdmqc5tDHOxiY4YP8M8wJRK2UWDJrTkQa5cOGmZgKnDpMOP1uWY/23kZ/3i5tNQsKZL+laXQKS6bn9XbfmGwfn1hchJelIEOeSd2oDqPPFXYNWXirHaw4wOLZZVeTJOqG5nZ9vW~1"


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

            # --- Strategy 1: Hardcoded or Environment variable ---
            env_cookies = HARDCODED_COOKIE.strip() or os.environ.get("NSE_COOKIES", "").strip()
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
