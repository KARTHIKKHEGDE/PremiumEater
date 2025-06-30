import httpx
import pandas as pd
import random
import logging
import os
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta
import json
import asyncio

class WebScraper:
    # Class variables to maintain state between refreshes
    last_oi_data = {}
    oi_history = {}
    SYMBOL = "NIFTY"
    STRIKES_TO_SHOW = 3  # Number of strikes above and below ATM
    OI_CHANGE_INTERVALS_MIN = (5, 10, 15, 30, 60, 120)
    
    # User agents to avoid blocking
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/119.0"
    ]
    
    @staticmethod
    async def fetch_nse_data() -> Tuple[Optional[pd.DataFrame], Optional[float], Optional[datetime.date]]:
        """Fetch option chain data from NSE with retry logic and better error handling"""
        home_url = "https://www.nseindia.com"
        option_chain_url = "https://www.nseindia.com/option-chain"
        api_url = f"https://www.nseindia.com/api/option-chain-indices?symbol={WebScraper.SYMBOL}"
        
        # Use proxy if available (for hosting platforms)
        proxy = os.environ.get("HTTP_PROXY", None)
        
        headers = {
            "User-Agent": random.choice(WebScraper.USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Referer": "https://www.nseindia.com/option-chain",
            "DNT": "1",
            "Pragma": "no-cache"
        }
        
        # Retry parameters
        max_retries = 3
        retry_delay = 2  # seconds
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                # Configure client with proxy if available
                client_args = {
                    "follow_redirects": True,
                    "timeout": 30.0
                }
                if proxy:
                    client_args["proxies"] = {
                        "http://": proxy, 
                        "https://": proxy
                    }
                    logging.info(f"Using proxy: {proxy}")
                
                logging.info(f"NSE API Attempt {attempt+1}/{max_retries}")
                
                async with httpx.AsyncClient(**client_args) as client:
                    # First, get the main page to set cookies
                    home_resp = await client.get(home_url, headers=headers, timeout=15)
                    if home_resp.status_code != 200:
                        logging.warning(f"Failed to connect to NSE home page: {home_resp.status_code}")
                        await asyncio.sleep(retry_delay)
                        continue
                    
                    # Wait to avoid rate limiting
                    await asyncio.sleep(1)
                    
                    # Visit the option chain page to set more cookies
                    oc_resp = await client.get(option_chain_url, headers=headers, timeout=15)
                    if oc_resp.status_code != 200:
                        logging.warning(f"Failed to connect to option chain page: {oc_resp.status_code}")
                        await asyncio.sleep(retry_delay)
                        continue
                    
                    # Wait again before API call
                    await asyncio.sleep(1)
                    
                    # Add special headers for API request
                    api_headers = headers.copy()
                    api_headers['Accept'] = 'application/json'
                    api_headers['X-Requested-With'] = 'XMLHttpRequest'
                    
                    # Finally request the API data
                    response = await client.get(api_url, headers=api_headers, timeout=15)
                    
                    if response.status_code != 200:
                        logging.warning(f"NSE API Error: {response.status_code}")
                        await asyncio.sleep(retry_delay)
                        continue
                    
                    # Try to decode the content correctly
                    try:
                        # Force encoding to utf-8
                        response.encoding = 'utf-8'
                        
                        # Parse JSON normally
                        data = response.json()
                        
                    except Exception as json_error:
                        logging.error(f"JSON Parse Error: {str(json_error)}")
                        await asyncio.sleep(retry_delay)
                        continue
                    
                    # Process the data
                    if 'filtered' not in data:
                        if 'records' in data and 'data' in data['records']:
                            # Alternative data format
                            logging.info("Using alternative data format...")
                            rawop = pd.DataFrame(data['records']['data']).fillna(0)
                        else:
                            logging.warning("NSE data format changed or invalid.")
                            await asyncio.sleep(retry_delay)
                            continue
                    else:
                        # Standard format
                        rawop = pd.DataFrame(data['filtered']['data']).fillna(0)
                    
                    current_price = data['records']['underlyingValue']
                    
                    # Get expiry date
                    expiry_date = None
                    if 'expiryDates' in data['records'] and len(data['records']['expiryDates']) > 0:
                        expiry_str = data['records']['expiryDates'][0]  # First (nearest) expiry
                        try:
                            expiry_date = datetime.strptime(expiry_str, "%d-%b-%Y").date()
                        except ValueError:
                            # If date format is different
                            try:
                                expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
                            except ValueError:
                                expiry_date = None
                    
                    logging.info(f"Successfully fetched option chain. Current {WebScraper.SYMBOL}: {current_price}")
                    return rawop, current_price, expiry_date
                    
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_exception = e
                logging.warning(f"Network error on attempt {attempt+1}: {str(e)}")
                await asyncio.sleep(retry_delay)
                continue
                
            except Exception as e:
                last_exception = e
                logging.error(f"Unexpected error on attempt {attempt+1}: {str(e)}")
                await asyncio.sleep(retry_delay)
                continue
                
        # If we get here, all retries failed
        logging.error(f"All {max_retries} attempts failed. Last error: {str(last_exception)}")
        return None, None, None
    
    @staticmethod
    def get_atm_strike(current_price):
        """Calculate the At-The-Money strike price"""
        strike_diff = 50 if WebScraper.SYMBOL == "NIFTY" else 100
        return round(current_price / strike_diff) * strike_diff
    
    @staticmethod
    def process_data(rawop, current_price, expiry_date):
        """Process option chain data and update history"""
        current_time = datetime.now()
        
        if rawop is None or current_price is None:
            return None
        
        # Get ATM strike
        atm_strike = WebScraper.get_atm_strike(current_price)
        
        # Filter strikes around ATM
        strike_range = []
        strike_diff = 50 if WebScraper.SYMBOL == "NIFTY" else 100
        for i in range(-WebScraper.STRIKES_TO_SHOW, WebScraper.STRIKES_TO_SHOW + 1):
            strike_range.append(atm_strike + (i * strike_diff))
        
        # Get relevant data
        filtered_data = []
        
        for _, row in rawop.iterrows():
            strike = row['strikePrice']
            
            if strike in strike_range:
                # Process call options
                call_oi = 0
                call_oi_change = 0
                
                if 'CE' in row and row['CE'] != 0:
                    ce = row['CE']
                    if isinstance(ce, dict):
                        call_oi = ce.get('openInterest', 0)
                        prev_call_oi = WebScraper.last_oi_data.get((strike, "CALL"), call_oi)
                        call_oi_change = call_oi - prev_call_oi
                        WebScraper.last_oi_data[(strike, "CALL")] = call_oi
                        
                        # Update history for percentage calculations
                        call_key = f"{strike}_CE"
                        if call_key not in WebScraper.oi_history:
                            WebScraper.oi_history[call_key] = []
                        WebScraper.oi_history[call_key].append({
                            'timestamp': current_time,
                            'oi': call_oi
                        })
                
                # Process put options
                put_oi = 0
                put_oi_change = 0
                
                if 'PE' in row and row['PE'] != 0:
                    pe = row['PE']
                    if isinstance(pe, dict):
                        put_oi = pe.get('openInterest', 0)
                        prev_put_oi = WebScraper.last_oi_data.get((strike, "PUT"), put_oi)
                        put_oi_change = put_oi - prev_put_oi
                        WebScraper.last_oi_data[(strike, "PUT")] = put_oi
                        
                        # Update history for percentage calculations
                        put_key = f"{strike}_PE"
                        if put_key not in WebScraper.oi_history:
                            WebScraper.oi_history[put_key] = []
                        WebScraper.oi_history[put_key].append({
                            'timestamp': current_time,
                            'oi': put_oi
                        })
                
                # Add to filtered data
                filtered_data.append({
                    'strike': strike,
                    'is_atm': strike == atm_strike,
                    'call_oi': call_oi,
                    'call_oi_change': call_oi_change,
                    'put_oi': put_oi,
                    'put_oi_change': put_oi_change
                })
        
        # Calculate percentage changes for various time intervals
        for item in filtered_data:
            strike = item['strike']
            call_key = f"{strike}_CE"
            put_key = f"{strike}_PE"
            
            # Calculate percentage changes for calls
            if call_key in WebScraper.oi_history:
                current_call_oi = item['call_oi']
                for interval in WebScraper.OI_CHANGE_INTERVALS_MIN:
                    past_time = current_time - timedelta(minutes=interval)
                    past_entries = [entry for entry in WebScraper.oi_history[call_key] if entry['timestamp'] <= past_time]
                    
                    if past_entries:
                        past_entry = sorted(past_entries, key=lambda x: x['timestamp'], reverse=True)[0]
                        past_oi = past_entry['oi']
                        
                        if past_oi > 0:
                            pct_change = ((current_call_oi - past_oi) / past_oi) * 100
                            item[f'call_pct_{interval}m'] = pct_change
            
            # Calculate percentage changes for puts
            if put_key in WebScraper.oi_history:
                current_put_oi = item['put_oi']
                for interval in WebScraper.OI_CHANGE_INTERVALS_MIN:
                    past_time = current_time - timedelta(minutes=interval)
                    past_entries = [entry for entry in WebScraper.oi_history[put_key] if entry['timestamp'] <= past_time]
                    
                    if past_entries:
                        past_entry = sorted(past_entries, key=lambda x: x['timestamp'], reverse=True)[0]
                        past_oi = past_entry['oi']
                        
                        if past_oi > 0:
                            pct_change = ((current_put_oi - past_oi) / past_oi) * 100
                            item[f'put_pct_{interval}m'] = pct_change
        
        # Clean up old history (keep only last 40 minutes)
        cutoff_time = current_time - timedelta(minutes=40)
        for key in WebScraper.oi_history:
            WebScraper.oi_history[key] = [entry for entry in WebScraper.oi_history[key] if entry['timestamp'] >= cutoff_time]
        
        # Sort by strike price
        filtered_data.sort(key=lambda x: x['strike'])
        
        # Calculate Put-Call Ratio (PCR) for top 5 strikes
        # Sort by strike price and get all 7 strikes (3 above and 3 below ATM + ATM)
        sorted_data = sorted(filtered_data, key=lambda x: x['strike'])
        
        # Get ATM index
        atm_index = next((i for i, item in enumerate(sorted_data) if item['is_atm']), len(sorted_data) // 2)
        
        # Get 3 strikes below and 3 above ATM (total 7 strikes including ATM)
        start_idx = max(0, atm_index - 3)
        end_idx = min(len(sorted_data), atm_index + 4)  # +4 to include ATM and 3 above
        
        # Ensure we have exactly 7 strikes if possible
        if (end_idx - start_idx) < 7 and end_idx < len(sorted_data):
            end_idx = min(len(sorted_data), start_idx + 7)
        elif (end_idx - start_idx) < 7:
            start_idx = max(0, end_idx - 7)
            
        selected_strikes = sorted_data[start_idx:end_idx]
        
        call_oi_total = int(sum(float(item['call_oi']) for item in selected_strikes))
        put_oi_total = int(sum(float(item['put_oi']) for item in selected_strikes))
        pcr = round(put_oi_total / call_oi_total, 2) if call_oi_total > 0 else 0
        
        # Debug output
        print("\n=== PCR Calculation (7 Strikes) ===")
        print(f"Selected Strikes: {[item['strike'] for item in selected_strikes]}")
        print(f"ATM Strike: {next((item['strike'] for item in selected_strikes if item['is_atm']), 'N/A')}")
        print(f"Call OIs: {[item['call_oi'] for item in selected_strikes]}")
        print(f"Put OIs: {[item['put_oi'] for item in selected_strikes]}")
        print(f"Total Call OI: {call_oi_total}")
        print(f"Total Put OI: {put_oi_total}")
        print(f"PCR: {pcr}")
        print("================================\n")
        
        # Ensure all numeric values are JSON serializable
        result = {
            'data': filtered_data,
            'current_price': float(current_price) if current_price else 0,
            'atm_strike': int(atm_strike) if atm_strike else 0,
            'timestamp': current_time.strftime("%H:%M:%S"),
            'pcr': float(pcr),
            'total_call_oi': int(call_oi_total),
            'total_put_oi': int(put_oi_total)
        }
        
        if expiry_date:
            if isinstance(expiry_date, str):
                result['expiry_date'] = expiry_date
            else:
                result['expiry_date'] = expiry_date.strftime("%d-%b-%Y") if hasattr(expiry_date, 'strftime') else str(expiry_date)
        else:
            result['expiry_date'] = None
            
        return result
    
    @staticmethod
    async def scrape_oi_data(url: str) -> Dict[str, Any]:
        """Main method to scrape OI data from NSE"""
        try:
            # Fetch data from NSE
            rawop, current_price, expiry_date = await WebScraper.fetch_nse_data()
            
            if rawop is None:
                return {
                    'status': 'error',
                    'message': "Failed to fetch data from NSE"
                }
            
            # Process the data
            processed_data = WebScraper.process_data(rawop, current_price, expiry_date)
            
            if not processed_data:
                return {
                    'status': 'error',
                    'message': "Failed to process data"
                }
            
            # Prepare response with all data
            response = {
                'status': 'success',
                'oi_data': processed_data.get('data', []),
                'current_price': float(processed_data.get('current_price', 0)),
                'atm_strike': int(processed_data.get('atm_strike', 0)),
                'timestamp': processed_data.get('timestamp', datetime.now().strftime("%H:%M:%S")),
                'expiry_date': processed_data.get('expiry_date'),
                'pcr': float(processed_data.get('pcr', 0)),
                'total_call_oi': int(processed_data.get('total_call_oi', 0)),
                'total_put_oi': int(processed_data.get('total_put_oi', 0)),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Debug output
            print("\n=== Final Response ===")
            print(json.dumps(response, indent=2, default=str))
            print("====================\n")
            
            return response
        
        except Exception as e:
            logging.exception("Error in scrape_oi_data")
            return {
                'status': 'error',
                'message': f"Failed to fetch OI data: {str(e)}"
            }
