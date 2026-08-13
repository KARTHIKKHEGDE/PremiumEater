from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
import os
import json
import locale
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from backend.scraper import WebScraper

# Load .env before anything else so NSE_COOKIES etc. are available
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Set up locale for number formatting
try:
    locale.setlocale(locale.LC_ALL, 'en_IN.UTF-8')
except Exception:
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except Exception:
        locale.setlocale(locale.LC_ALL, '')

# ---------------------------------------------------------------------------
# In-memory data cache — populated by the background scraper task
# ---------------------------------------------------------------------------
_cached_data: Dict[str, Any] = {}
_cache_lock = asyncio.Lock()
_scraper_task: Optional[asyncio.Task] = None

SCRAPE_INTERVAL_SECONDS = int(os.environ.get("SCRAPE_INTERVAL", "30"))

OI_URL = "https://www.nseindia.com/option-chain"


async def _background_scraper():
    """Continuously scrape NSE data in the background and update the cache."""
    global _cached_data
    while True:
        try:
            logger.info("Background scraper: fetching NSE data...")
            result = await WebScraper.scrape_oi_data(OI_URL)
            async with _cache_lock:
                _cached_data = result
            status = result.get("status", "unknown")
            logger.info(f"Background scraper: fetch complete (status={status})")
        except Exception as e:
            logger.exception(f"Background scraper error: {e}")
        await asyncio.sleep(SCRAPE_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Lifespan — start / stop the background scraper
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scraper_task
    logger.info("Starting background NSE scraper task...")
    _scraper_task = asyncio.create_task(_background_scraper())
    yield
    # Shutdown
    if _scraper_task:
        _scraper_task.cancel()
        try:
            await _scraper_task
        except asyncio.CancelledError:
            pass
    logger.info("Background scraper stopped.")


# Initialize FastAPI
app = FastAPI(title="OI Change Tracker", lifespan=lifespan)

# Configure templates with custom filters
templates = Jinja2Templates(directory="frontend/templates")


# Add custom Jinja2 filters
def format_number(value, decimal_places=0):
    try:
        if value is None:
            return ""
        if isinstance(value, (int, float)):
            return f"{value:,.{decimal_places}f}"
        return value
    except (ValueError, TypeError):
        return value


templates.env.filters['number_format'] = format_number

# Mount static files
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the UI instantly from the cache. Never blocks on NSE."""
    async with _cache_lock:
        data = dict(_cached_data)  # shallow copy

    if data.get("status") == "success":
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "request": request,
                "oi_data": data.get("oi_data", []),
                "current_price": data.get("current_price", 0),
                "atm_strike": data.get("atm_strike", 0),
                "timestamp": data.get("timestamp", "—"),
                "expiry_date": data.get("expiry_date"),
                "last_updated": data.get("last_updated", ""),
                "pcr": data.get("pcr", 0),
                "total_call_oi": data.get("total_call_oi", 0),
                "total_put_oi": data.get("total_put_oi", 0),
                "data_available": True,
            },
        )
    else:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "request": request,
                "oi_data": [],
                "current_price": 0,
                "atm_strike": 0,
                "timestamp": "—",
                "expiry_date": None,
                "last_updated": "",
                "pcr": 0,
                "total_call_oi": 0,
                "total_put_oi": 0,
                "data_available": False,
                "error_message": data.get("message", "Waiting for first data fetch..."),
            },
        )


@app.get("/api/data")
async def api_data():
    """Return cached OI data as JSON for AJAX polling."""
    async with _cache_lock:
        data = dict(_cached_data)
    return JSONResponse(content=data)


# ---------------------------------------------------------------------------
# Cookie injection endpoint — update NSE cookies without restarting the server
# ---------------------------------------------------------------------------
class CookiePayload(BaseModel):
    cookies: str


@app.post("/api/set-cookies")
async def set_cookies(payload: CookiePayload):
    """
    Inject fresh NSE session cookies into the running app without a restart.

    Usage (from browser console or curl):
        curl -X POST http://localhost:8000/api/set-cookies \\
             -H "Content-Type: application/json" \\
             -d '{"cookies": "YOUR_COOKIE_STRING_HERE"}'
    """
    from backend.cookie_manager import CookieManager
    import time
    if not payload.cookies or len(payload.cookies) < 20:
        return JSONResponse({"status": "error", "message": "Cookie string too short"}, status_code=400)
    CookieManager._cookie_string = payload.cookies
    CookieManager._fetched_at = time.time()
    CookieManager._source = "api"
    logger.info(f"Cookies updated via /api/set-cookies ({len(payload.cookies)} chars)")
    return {"status": "ok", "message": f"Cookies updated ({len(payload.cookies)} chars). Next scrape will use them."}


# Health check endpoint for hosting platforms
@app.get("/health")
async def health_check():
    from backend.cookie_manager import CookieManager
    import time
    async with _cache_lock:
        has_data = _cached_data.get("status") == "success"
    cookie_age = int(time.time() - CookieManager._fetched_at)
    return {
        "status": "healthy",
        "has_data": has_data,
        "cookie_source": CookieManager._source,
        "cookie_age_seconds": cookie_age,
        "timestamp": datetime.now().isoformat(),
    }


# Graceful error handling for NSE API issues
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error: {str(exc)}")
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={"request": request, "error": "Service temporarily unavailable. Please try again later."},
        status_code=500,
    )


if __name__ == "__main__":
    import uvicorn
    # Get port from environment variable (for hosting platforms) or use default
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    # Log startup information
    logger.info(f"Starting NSE OI Tracker on {host}:{port}")
    uvicorn.run("main:app", host=host, port=port, log_level="info")
