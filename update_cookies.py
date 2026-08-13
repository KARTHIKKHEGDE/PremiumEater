"""
update_cookies.py  —  NSE Cookie Updater for PremiumEater
-----------------------------------------------------------
Run this script whenever NSE data stops loading (cookies expire ~every 90 min).

HOW TO GET FRESH NSE COOKIES:
  1. Open Chrome/Firefox and go to https://www.nseindia.com/option-chain
  2. Press F12 -> Network tab -> reload the page
  3. Click any request that hits nseindia.com (e.g. option-chain-v3?)
  4. In the Headers tab, find "cookie:" under Request Headers
  5. Copy EVERYTHING after "cookie: " and paste it when prompted

This script:
  - Saves cookies to .env (NSE_COOKIES=...)
  - Updates HARDCODED_COOKIE in backend/cookie_manager.py
  - If the server is running, injects cookies live via /api/set-cookies
    so you don't need to restart.
"""

import re
import sys
import json
from pathlib import Path

try:
    import urllib.request as urllib_request
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

ROOT = Path(__file__).parent
SERVER_URL = "http://localhost:8000"

print("=" * 65)
print("  NSE Cookie Updater for PremiumEater")
print("=" * 65)
print()
print("Get fresh cookies from Chrome/Firefox DevTools:")
print("  1. Open https://www.nseindia.com/option-chain")
print("  2. F12 -> Network -> click any NSE request -> Headers tab")
print("  3. Find 'cookie:' under Request Headers")
print("  4. Copy everything AFTER 'cookie: '")
print()
print("Paste cookie string below and press Enter:")
print("-" * 65)
cookie_str = input().strip()

if not cookie_str:
    print("No input. Exiting.")
    sys.exit(1)

if cookie_str.lower().startswith("cookie:"):
    cookie_str = cookie_str[7:].strip()

print(f"\nCookie length: {len(cookie_str)} chars")

if len(cookie_str) < 50:
    ans = input("That looks very short. Continue anyway? (y/n): ").strip().lower()
    if ans != 'y':
        sys.exit(1)

# 1. Update .env
env_path = ROOT / ".env"
env_content = ""
if env_path.exists():
    env_content = env_path.read_text(encoding="utf-8")

if "NSE_COOKIES=" in env_content:
    # Replace the existing line (handle very long single-line values)
    lines = env_content.splitlines(keepends=True)
    new_lines = []
    for line in lines:
        if line.startswith("NSE_COOKIES="):
            new_lines.append(f"NSE_COOKIES={cookie_str}\n")
        else:
            new_lines.append(line)
    env_content = "".join(new_lines)
else:
    env_content += f"\nNSE_COOKIES={cookie_str}\n"

env_path.write_text(env_content, encoding="utf-8")
print(f"[OK] Saved to {env_path}")

# 2. Update HARDCODED_COOKIE in cookie_manager.py
cm_path = ROOT / "backend" / "cookie_manager.py"
if cm_path.exists():
    cm_content = cm_path.read_text(encoding="utf-8")
    cm_content = re.sub(
        r'^HARDCODED_COOKIE\s*=\s*"[^"]*"[^\n]*$',
        f'HARDCODED_COOKIE = "{cookie_str}"  # updated by update_cookies.py',
        cm_content,
        flags=re.MULTILINE,
    )
    cm_path.write_text(cm_content, encoding="utf-8")
    print(f"[OK] Updated HARDCODED_COOKIE in backend/cookie_manager.py")

# 3. Inject into running server (no restart needed)
if HAS_URLLIB:
    try:
        payload = json.dumps({"cookies": cookie_str}).encode("utf-8")
        req = urllib_request.Request(
            f"{SERVER_URL}/api/set-cookies",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib_request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
        print(f"[OK] Injected into running server: {result.get('message', 'done')}")
    except Exception as e:
        print(f"[INFO] Server not running or unreachable ({e}) — cookies saved to .env for next startup.")

print()
print("Done! The app will use the new cookies on the next scrape cycle (every 30s).")
print("If the server is not running, start it with:")
print("  venv\\Scripts\\python.exe -m uvicorn main:app --reload")
