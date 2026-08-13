"""
NSE Cookie Manager — Auto-Refresh Edition
------------------------------------------
Automatically fetches and refreshes NSE session cookies using curl_cffi
(the same TLS-fingerprint library the scraper uses). No Playwright needed.
No manual copy-paste. Cookies are refreshed every 90 minutes automatically.

Priority order:
  1. curl_cffi auto-fetch (visits NSE homepage + option-chain to get a session)
  2. NSE_COOKIES env var / .env file fallback (manual override)
  3. Previously cached cookies (last resort if all refreshes fail)

Usage:
    from backend.cookie_manager import CookieManager
    cookie_str = await CookieManager.get_cookies()
"""

import asyncio
import logging
import time
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── TTL ──────────────────────────────────────────────────────────────────────
COOKIE_TTL_SECONDS = 80 * 60   # refresh 10 min before NSE's 90-min expiry

# ── Warm-up sequence — must hit these in order to build a valid NSE session ──
WARMUP_SEQUENCE = [
    "https://www.nseindia.com",
    "https://www.nseindia.com/option-chain",
]

# ── Base headers that mirror a real Chrome 136 desktop browser ───────────────
_BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}


class CookieManager:
    """
    Thread-safe async singleton.
    Automatically keeps NSE session cookies fresh via curl_cffi.
    """

    _cookie_string: Optional[str] = None
    _fetched_at: float = 0.0
    _lock: asyncio.Lock = asyncio.Lock()
    _source: str = "none"

    # ── Public API ────────────────────────────────────────────────────────────

    @classmethod
    async def get_cookies(cls, force: bool = False) -> Optional[str]:
        """
        Return a valid NSE cookie string, refreshing automatically as needed.

        Args:
            force: If True, bypass the cache and fetch immediately.
        Returns:
            Semicolon-separated cookie string, or None if all methods fail.
        """
        async with cls._lock:
            age = time.time() - cls._fetched_at
            is_stale = age >= COOKIE_TTL_SECONDS

            if not force and cls._cookie_string and not is_stale:
                logger.debug(
                    f"Using cached NSE cookies "
                    f"(age={age:.0f}s, source={cls._source})"
                )
                return cls._cookie_string

            reason = (
                "forced" if force
                else ("stale" if is_stale else "first-fetch")
            )
            logger.info(f"Cookie refresh triggered ({reason})…")

            # ── Strategy 1: auto-fetch via curl_cffi ─────────────────────────
            fresh = await cls._fetch_via_curl_cffi()
            if fresh:
                cls._cookie_string = fresh
                cls._fetched_at = time.time()
                cls._source = "auto"
                logger.info(
                    f"✅ NSE cookies auto-refreshed via curl_cffi "
                    f"({len(fresh)} chars)."
                )
                return cls._cookie_string

            # ── Strategy 2: env var / .env override ──────────────────────────
            env_cookies = os.environ.get("NSE_COOKIES", "").strip()
            if env_cookies:
                cls._cookie_string = env_cookies
                cls._fetched_at = time.time()
                cls._source = "env"
                logger.info(
                    f"Using NSE_COOKIES env var ({len(env_cookies)} chars)."
                )
                return cls._cookie_string

            # ── Strategy 3: reuse stale cache rather than returning None ──────
            if cls._cookie_string:
                logger.warning(
                    "All refresh methods failed — reusing existing cookies."
                )
                return cls._cookie_string

            logger.error("Could not obtain NSE cookies via any method.")
            return None

    @classmethod
    def invalidate(cls) -> None:
        """Force a refresh on the next call to get_cookies()."""
        cls._fetched_at = 0.0
        logger.info("NSE cookie cache invalidated — will refresh on next request.")

    @classmethod
    def get_source(cls) -> str:
        """'auto', 'env', or 'none'."""
        return cls._source

    # ── Internal: curl_cffi auto-fetch ────────────────────────────────────────

    @classmethod
    async def _fetch_via_curl_cffi(cls) -> Optional[str]:
        """
        Open a curl_cffi session (impersonating Chrome 136), visit the NSE
        homepage then the option-chain page to collect all session cookies,
        and return them as a single semicolon-separated string.

        curl_cffi handles TLS fingerprinting automatically — NSE's WAF sees
        a real Chrome browser, not a Python script.
        """
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, cls._curl_cffi_sync)
            return result
        except Exception as e:
            logger.error(f"curl_cffi cookie fetch failed: {e}")
            return None

    @classmethod
    def _curl_cffi_sync(cls) -> Optional[str]:
        """Synchronous curl_cffi session — runs in a thread pool."""
        try:
            from curl_cffi import requests as curl_requests

            with curl_requests.Session(impersonate="chrome136") as session:
                # Step 1: hit the homepage to seed initial cookies
                try:
                    r1 = session.get(
                        "https://www.nseindia.com",
                        headers=_BASE_HEADERS,
                        timeout=20,
                        allow_redirects=True,
                    )
                    logger.debug(
                        f"NSE homepage: HTTP {r1.status_code}, "
                        f"cookies so far: {len(session.cookies)}"
                    )
                except Exception as e:
                    logger.warning(f"NSE homepage warmup failed: {e}")

                time.sleep(1.5)  # brief human-like pause

                # Step 2: hit option-chain to get the session/nsit cookie
                try:
                    headers2 = {
                        **_BASE_HEADERS,
                        "Referer": "https://www.nseindia.com/",
                        "sec-fetch-site": "same-origin",
                    }
                    r2 = session.get(
                        "https://www.nseindia.com/option-chain",
                        headers=headers2,
                        timeout=20,
                        allow_redirects=True,
                    )
                    logger.debug(
                        f"NSE option-chain: HTTP {r2.status_code}, "
                        f"cookies so far: {len(session.cookies)}"
                    )
                except Exception as e:
                    logger.warning(f"NSE option-chain warmup failed: {e}")

                time.sleep(1.0)

                # Collect all cookies from the session jar
                cookies = session.cookies
                if not cookies:
                    logger.warning("curl_cffi returned no cookies from NSE.")
                    return None

                cookie_str = "; ".join(
                    f"{name}={value}"
                    for name, value in cookies.items()
                )
                logger.info(
                    f"curl_cffi captured {len(list(cookies.items()))} "
                    f"cookies from NSE."
                )
                return cookie_str

        except ImportError:
            logger.error(
                "curl_cffi not installed. "
                "Run: pip install curl_cffi"
            )
            return None
        except Exception as e:
            logger.error(f"curl_cffi session error: {e}")
            return None
