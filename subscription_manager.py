import datetime
from functools import wraps
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from subscription.database import subscriptions_col, users_col, settings_col

def check_subscription(user_id, target_id='bot'):
    """
    Checks active subscriptions database records
    """
    now = datetime.datetime.utcnow()
    sub = subscriptions_col.find_one({
        "user_id": int(user_id),
        "target_id": target_id,
        "status": "active",
        "expiry_date": {"$gt": now}
    })
    if sub:
        return True
    
    sub_lifetime = subscriptions_col.find_one({
        "user_id": int(user_id),
        "target_id": target_id,
        "status": "active",
        "plan": "Lifetime"
    })
    return sub_lifetime is not None

def check_free_limit(user_id):
    """
    Calculates dynamic daily free tier balances.
    Resets automated count on date boundary changes.
    """
    settings = settings_col.find_one({"_id": "free_limits"})
    limit = settings.get("limit_per_day", 3) if settings else 3
    
    now = datetime.datetime.utcnow()
    today_str = now.strftime("%Y-%m-%d")
    
    user = users_col.find_one({"_id": int(user_id)})
    if not user:
        users_col.insert_one({
            "_id": int(user_id),
            "last_use_date": today_str,
            "free_uses_today": 0
        })
        user = {"last_use_date": today_str, "free_uses_today": 0}
        
    if user.get("last_use_date") != today_str:
        users_col.update_one(
            {"_id": int(user_id)},
            {"$set": {"last_use_date": today_str, "free_uses_today": 0}}
        )
        return True, limit
    
    current_uses = user.get("free_uses_today", 0)
    if current_uses < limit:
        return True, limit - current_uses
    return False, 0

def increment_free_use(user_id):
    now = datetime.datetime.utcnow()
    today_str = now.strftime("%Y-%m-%d")
    users_col.update_one(
        {"_id": int(user_id)},
        {
            "$inc": {"free_uses_today": 1},
            "$set": {"last_use_date": today_str}
        },
        upsert=True
    )

def premium_required(bot: telebot.TeleBot):
    """
    Reusable clean decorator to wrap telebot message/callback commands
    """
    def decorator(func):
        @wraps(func)
        def wrapper(message, *args, **kwargs):
            if isinstance(message, telebot.types.Message):
                user_id = message.from_user.id
                chat_id = message.chat.id
            elif isinstance(message, telebot.types.CallbackQuery):
                user_id = message.from_user.id
                chat_id = message.message.chat.id
            else:
                return func(message, *args, **kwargs)

            # Accept if admin bypass
            from subscription.database import is_admin
            if is_admin(user_id):
                return func(message, *args, **kwargs)

            # Check premium subscription for the bot
            if check_subscription(user_id, 'bot'):
                return func(message, *args, **kwargs)
            
            # Check free daily limits status
            allowed, remaining = check_free_limit(user_id)
            if allowed:
                increment_free_use(user_id)
                return func(message, *args, **kwargs)
            
            # Display plans overlay
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🌟 View Bot Premium Plans", callback_data="buy_bot_plans"))
            
            error_msg = (
                "⚠️ *Premium Content Locked!*\n\n"
                "You have reached your Free daily limit of requests.\n"
                "Upgrade to Premium for completely unlimited bot access!"
            )
            
            if isinstance(message, telebot.types.Message):
                bot.send_message(chat_id, error_msg, parse_mode="Markdown", reply_markup=markup)
            elif isinstance(message, telebot.types.CallbackQuery):
                bot.answer_callback_query(message.id, "Daily free limits reached! Subscribe to proceed.", show_alert=True)
                bot.send_message(chat_id, error_msg, parse_mode="Markdown", reply_markup=markup)
                
        return wrapper
    return decorator
