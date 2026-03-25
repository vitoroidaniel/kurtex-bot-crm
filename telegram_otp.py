# telegram_otp.py
import os
from telegram import Bot

# Read bot token and admin chat ID from environment variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment variables")

# Create a single Bot instance
bot = Bot(token=TELEGRAM_BOT_TOKEN)

def send_otp(telegram_id: int, code: str):
    """
    Sends a one-time code to a user's Telegram ID.
    """
    try:
        bot.send_message(chat_id=telegram_id, text=f"Your login code: {code}")
        return True
    except Exception as e:
        print(f"Failed to send OTP: {e}")
        return False
