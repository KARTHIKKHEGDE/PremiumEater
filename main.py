from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
import json
import locale
import logging
from datetime import datetime
from backend.scraper import WebScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Set up locale for number formatting
try:
    locale.setlocale(locale.LC_ALL, 'en_IN.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except:
        locale.setlocale(locale.LC_ALL, '')

# Initialize FastAPI
app = FastAPI(title="OI Change Tracker")

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

# Your specific URL with OI data
OI_URL = "https://www.nseindia.com/option-chain"  # Replace with your actual OI data URL

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        # Scrape the OI data automatically
        result = await WebScraper.scrape_oi_data(OI_URL)
        if result.get('status') == 'error':
            raise Exception(result.get('message', 'Failed to fetch OI data'))
            
        return templates.TemplateResponse(
            "index.html", 
            {
                "request": request,
                "oi_data": result.get('oi_data', []),
                "current_price": result.get('current_price', 0),
                "atm_strike": result.get('atm_strike', 0),
                "timestamp": result.get('timestamp', datetime.now().strftime("%H:%M:%S")),
                "expiry_date": result.get('expiry_date', None),
                "last_updated": result.get('last_updated', '')
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "error.html", 
            {
                "request": request,
                "error": str(e)
            },
            status_code=500
        )

# Health check endpoint for hosting platforms
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Graceful error handling for NSE API issues
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Global error: {str(exc)}")
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "error": "Service temporarily unavailable. Please try again later."},
        status_code=500
    )

if __name__ == "__main__":
    import uvicorn
    # Get port from environment variable (for hosting platforms) or use default
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    # Log startup information
    logging.info(f"Starting NSE OI Tracker on {host}:{port}")
    uvicorn.run("main:app", host=host, port=port, log_level="info")
