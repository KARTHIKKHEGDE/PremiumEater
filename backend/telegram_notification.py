import requests
import os
import logging
from dotenv import load_dotenv
load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def check_and_notify_oi_changes(oi_data: list):
    """
    Checks each row for OI percentage changes above 30% and sends a Telegram notification.
    Expects oi_data to be a list of dicts as returned by scraper.py's process_data()['data'].
    """
    for row in oi_data:
        strike = row.get('strike')
        alerts = []
        for key, value in row.items():
            if key.startswith('call_pct_') or key.startswith('put_pct_'):
                try:
                    if abs(float(value)) >= 30:
                        alerts.append(f"{key}: {float(value):.2f}%")
                except Exception:
                    continue
        if alerts:
            msg = (
                f"⚠️ <b>OI Change Alert</b>\n"
                f"Strike: <b>{strike}</b>\n"
                + "\n".join(alerts)
            )
            send_telegram_message(msg)


# Simulated test data
test_oi_data = [
    {"strike": 5200, "call_pct_oi": 35, "put_pct_oi": 10},
    {"strike": 5250, "call_pct_oi": 5, "put_pct_oi": 32},
    {"strike": 5300, "call_pct_oi": 15, "put_pct_oi": 20},  # should not trigger
]

# Call your function with the test data
check_and_notify_oi_changes(test_oi_data)

