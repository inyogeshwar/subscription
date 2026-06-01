import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from subscription.database import subscriptions_col, channels_col, log_event
from subscription.config import CONTACT_USERNAME

def start_expiry_scheduler(bot: telebot.TeleBot):
    scheduler = BackgroundScheduler()
    
    def check_expirations():
        now = datetime.datetime.utcnow()
        
        # 1. PROCESS ACTIVE EXPIRATIONS
        expired_subs = subscriptions_col.find({
            "status": "active",
            "expiry_date": {"$lte": now}
        })
        
        for sub in expired_subs:
            user_id = sub["user_id"]
            target_id = sub["target_id"]
            plan = sub["plan"]
            
            if plan == "Lifetime":
                continue

            subscriptions_col.update_one(
                {"_id": sub["_id"]},
                {"$set": {"status": "expired"}}
            )

            if target_id == "bot":
                try:
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("🌟 Renew Premium Subscription", callback_data="buy_bot_plans"))
                    bot.send_message(
                        user_id,
                        "🚨 *Your Premium Subscription has expired!*\n\n"
                        "Daily limits have returned. Renew now for uninterrupted service.",
                        reply_markup=markup,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    log_event("error", f"Bot-level expiration delivery fail {user_id}", str(e))
            else:
                chan = channels_col.find_one({"_id": int(target_id)})
                chan_name = chan["channel_name"] if chan else "Private Channel"
                
                try:
                    # Banning then immediately unbanning safely revokes active private links and kicks user from channel
                    bot.ban_chat_member(chat_id=int(target_id), user_id=user_id)
                    bot.unban_chat_member(chat_id=int(target_id), user_id=user_id, only_if_banned=True)
                    
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("⚡ Renew Membership", callback_data=f"buy_chan_plans:{target_id}"))
                    
                    bot.send_message(
                        user_id,
                        f"🚨 *Your Membership subscription to '{chan_name}' has expired!*\n\n"
                        f"You have been removed from the channel. To rejoin, click below to renew:",
                        reply_markup=markup,
                        parse_mode="Markdown"
                    )
                    log_event("info", f"User {user_id} removed from channel {target_id} due to expiry.")
                except Exception as e:
                    log_event("error", f"Expel user failed {user_id} from private channel {target_id}", str(e))
                    try:
                        bot.send_message(
                            user_id,
                            f"⚠️ *Your subscription to '{chan_name}' has expired.* Contact support @{CONTACT_USERNAME} to manage updates.",
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass

        # 2. 24-HOUR RENEWAL REMINDER
        rem_24_start = now + datetime.timedelta(hours=23)
        rem_24_end = now + datetime.timedelta(hours=24)
        
        subs_24h = subscriptions_col.find({
            "status": "active",
            "expiry_date": {"$gte": rem_24_start, "$lte": rem_24_end},
            "notified_24h": {"$ne": True}
        })
        
        for sub in subs_24h:
            user_id = sub["user_id"]
            target_id = sub["target_id"]
            subscriptions_col.update_one({"_id": sub["_id"]}, {"$set": {"notified_24h": True}})
            try:
                markup = InlineKeyboardMarkup()
                if target_id == "bot":
                    markup.add(InlineKeyboardButton("🌟 Extend Premium", callback_data="buy_bot_plans"))
                    bot.send_message(
                        user_id,
                        "⏳ *Renewal Alert!*\n\nYour premium bot access expires in *24 hours*.",
                        reply_markup=markup,
                        parse_mode="Markdown"
                    )
                else:
                    chan = channels_col.find_one({"_id": int(target_id)})
                    chan_name = chan["channel_name"] if chan else "Private Channel"
                    markup.add(InlineKeyboardButton("⚡ Extend Membership", callback_data=f"buy_chan_plans:{target_id}"))
                    bot.send_message(
                        user_id,
                        f"⏳ *Renewal Alert!*\n\nYour membership access to *'{chan_name}'* expires in *24 hours*.",
                        reply_markup=markup,
                        parse_mode="Markdown"
                    )
            except Exception as e:
                log_event("error", f"24h reminder notification failure to {user_id}", str(e))

        # 3. 1-HOUR RENEWAL REMINDER
        rem_1_start = now + datetime.timedelta(minutes=50)
        rem_1_end = now + datetime.timedelta(hours=1)
        
        subs_1h = subscriptions_col.find({
            "status": "active",
            "expiry_date": {"$gte": rem_1_start, "$lte": rem_1_end},
            "notified_1h": {"$ne": True}
        })
        
        for sub in subs_1h:
            user_id = sub["user_id"]
            target_id = sub["target_id"]
            subscriptions_col.update_one({"_id": sub["_id"]}, {"$set": {"notified_1h": True}})
            try:
                markup = InlineKeyboardMarkup()
                if target_id == "bot":
                    markup.add(InlineKeyboardButton("🌟 Extend Premium Now", callback_data="buy_bot_plans"))
                    bot.send_message(
                        user_id,
                        "⏳ *Urgent Renewal Alert!*\n\nYour Premium features will expire in *1 hour*.",
                        reply_markup=markup,
                        parse_mode="Markdown"
                    )
                else:
                    chan = channels_col.find_one({"_id": int(target_id)})
                    chan_name = chan["channel_name"] if chan else "Private Channel"
                    markup.add(InlineKeyboardButton("⚡ Extend Membership Now", callback_data=f"buy_chan_plans:{target_id}"))
                    bot.send_message(
                        user_id,
                        f"⏳ *Urgent Renewal Alert!*\n\nYour access to channel *'{chan_name}'* expires in *1 hour*.",
                        reply_markup=markup,
                        parse_mode="Markdown"
                    )
            except Exception as e:
                log_event("error", f"1h reminder notification failure to {user_id}", str(e))

    scheduler.add_job(check_expirations, "interval", seconds=60)
    scheduler.start()
    return scheduler
