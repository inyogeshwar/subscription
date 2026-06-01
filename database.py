from pymongo import MongoClient
from subscription.config import MONGO_URI, ADMIN_IDS
import datetime

client = MongoClient(MONGO_URI)
db = client["telegram_subscription_system"]

users_col = db["users"]
subscriptions_col = db["subscriptions"]
payments_col = db["payments"]
admins_col = db["admins"]
settings_col = db["settings"]
logs_col = db["logs"]
channels_col = db["channels"]

def init_db():
    # Sync static admins defined in Config with database administrators collection
    for admin_id in ADMIN_IDS:
        admins_col.update_one({"_id": admin_id}, {"$set": {"_id": admin_id}}, upsert=True)
    
    # Initialize basic bot plans configuration if not exists
    if not settings_col.find_one({"_id": "bot_plans"}):
        from subscription.config import DEFAULT_BOT_PLANS
        settings_col.insert_one({"_id": "bot_plans", "plans": DEFAULT_BOT_PLANS})
    
    # Initialize basic free requests daily limit configurations
    if not settings_col.find_one({"_id": "free_limits"}):
        settings_col.insert_one({"_id": "free_limits", "limit_per_day": 3})

def is_admin(user_id):
    return admins_col.find_one({"_id": int(user_id)}) is not None

def add_admin_db(user_id):
    admins_col.update_one({"_id": int(user_id)}, {"$set": {"_id": int(user_id)}}, upsert=True)

def remove_admin_db(user_id):
    admins_col.delete_one({"_id": int(user_id)})

def log_event(level, message, detail=None):
    logs_col.insert_one({
        "timestamp": datetime.datetime.utcnow(),
        "level": level,
        "message": message,
        "detail": detail
    })
