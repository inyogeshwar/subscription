import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
UPI_ID = os.getenv("UPI_ID", "your-upi-id@bank")
CONTACT_USERNAME = os.getenv("CONTACT_USERNAME", "admin_username")

admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = []
if admin_ids_str:
    try:
        ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
    except ValueError:
        ADMIN_IDS = []

# Fallback default plans for local startup validation
DEFAULT_BOT_PLANS = {
    "Daily": {"price": 10, "days": 1},
    "Weekly": {"price": 49, "days": 7},
    "Monthly": {"price": 149, "days": 30},
    "Yearly": {"price": 999, "days": 365},
    "Lifetime": {"price": 2999, "days": 9999}
}
