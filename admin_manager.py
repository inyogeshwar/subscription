import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from subscription.database import (
    is_admin, add_admin_db, remove_admin_db, users_col, subscriptions_col, payments_col, channels_col, settings_col
)
from subscription.payment_manager import get_bot_plans
import datetime

def register_admin_handlers(bot: telebot.TeleBot):

    @bot.message_handler(commands=['admin'])
    def handle_admin_dashboard(message):
        if not is_admin(message.from_user.id):
            return
        
        total_users = users_col.count_documents({})
        active_subs = subscriptions_col.count_documents({"status": "active", "expiry_date": {"$gt": datetime.datetime.utcnow()}})
        expired_subs = subscriptions_col.count_documents({"status": "expired"})
        pending_payments = payments_col.count_documents({"status": "pending_approval"})
        
        approved_payments = payments_col.find({"status": "approved"})
        revenue = sum(p.get("amount", 0) for p in approved_payments)

        dash_text = (
            f"🛠️ *ADMINISTRATIVE PORTAL*\n\n"
            f"👥 *Total Bot Accounts:* {total_users}\n"
            f"🟢 *Active VIP Subscribers:* {active_subs}\n"
            f"🔴 *Expired Memberships:* {expired_subs}\n"
            f"⏳ *Unverified Payment Slips:* {pending_payments}\n"
            f"💰 *Net Collected Revenue:* ₹{revenue:,.2f}\n\n"
            f"👉 *Command List:*\n"
            f"🔹 /plans - Show Bot pricing packages\n"
            f"🔹 /users - List current memberships\n"
            f"🔹 /addchannel - Connect target Private Channel\n"
            f"🔹 /broadcast <text> - Global broadcast alert\n"
            f"🔹 /addadmin <id> - Add an Administrator\n"
            f"🔹 /removeadmin <id> - Revoke Administrative access"
        )
        bot.reply_to(message, dash_text, parse_mode="Markdown")

    @bot.message_handler(commands=['addadmin'])
    def handle_add_admin(message):
        if not is_admin(message.from_user.id):
            return
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Format: `/addadmin <user_id>`", parse_mode="Markdown")
            return
        try:
            target_id = int(parts[1])
            add_admin_db(target_id)
            bot.reply_to(message, f"✅ Account ID `{target_id}` added as administrator.", parse_mode="Markdown")
        except ValueError:
            bot.reply_to(message, "❌ Admin ID must be numeric.")

    @bot.message_handler(commands=['removeadmin'])
    def handle_remove_admin(message):
        if not is_admin(message.from_user.id):
            return
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Format: `/removeadmin <user_id>`", parse_mode="Markdown")
            return
        try:
            target_id = int(parts[1])
            remove_admin_db(target_id)
            bot.reply_to(message, f"✅ Account ID `{target_id}` removed from administration list.", parse_mode="Markdown")
        except ValueError:
            bot.reply_to(message, "❌ Admin ID must be numeric.")

    @bot.message_handler(commands=['plans'])
    def handle_plans_config(message):
        if not is_admin(message.from_user.id):
            return
        plans = get_bot_plans()
        plan_text = "💎 *Active Premium Bot Packages:*\n\n"
        for name, info in plans.items():
            plan_text += f"🔹 *{name}:* ₹{info['price']} ({info['days']} days)\n"
        bot.reply_to(message, plan_text, parse_mode="Markdown")

    @bot.message_handler(commands=['users'])
    def handle_list_users(message):
        if not is_admin(message.from_user.id):
            return
        subs = subscriptions_col.find({"status": "active"}).limit(30)
        res_text = "🟢 *Active Subscribers List (Max 30):*\n\n"
        count = 0
        for s in subs:
            count += 1
            res_text += f"👤 *User ID:* `{s['user_id']}` | *Service:* {s['target_id']} | *Plan:* {s['plan']} | *Exp:* {s['expiry_date'].strftime('%Y-%m-%d')}\n"
        if count == 0:
            res_text += "No records found."
        bot.reply_to(message, res_text, parse_mode="Markdown")

    @bot.message_handler(commands=['addchannel'])
    def handle_add_channel_start(message):
        if not is_admin(message.from_user.id):
            return
        users_col.update_one(
            {"_id": int(message.from_user.id)},
            {"$set": {"state": "waiting_for_channel_forward"}}
        )
        bot.reply_to(
            message,
            "📢 *Private Channel Addition Tool*\n\n"
            "Forward any message from your target Private Telegram Channel directly here.\n"
            "⚠️ *Pre-requisite:* Ensure this bot is already an administrator in that private channel with link generation rights.",
            parse_mode="Markdown"
        )

    # Strictly routes dynamic forwards when admin is in onboarding mode
    @bot.message_handler(func=lambda msg: users_col.find_one({"_id": msg.from_user.id, "state": "waiting_for_channel_forward"}) is not None)
    def handle_channel_forward_detect(message):
        users_col.update_one({"_id": int(message.from_user.id)}, {"$unset": {"state": ""}})
        
        if not message.forward_from_chat:
            bot.reply_to(message, "❌ Could not process. Please forward an actual message from the channel.")
            return

        chat = message.forward_from_chat
        if chat.type != "channel":
            bot.reply_to(message, f"❌ Detected type is '{chat.type}'. This utility only connects private channel entities.")
            return

        channel_id = chat.id
        channel_name = chat.title

        try:
            member_info = bot.get_chat_member(channel_id, bot.get_me().id)
            if member_info.status not in ["administrator", "creator"]:
                bot.reply_to(message, "❌ Verification failed. Bot is not configured as Administrator in channel.")
                return
        except Exception as e:
            bot.reply_to(message, f"❌ Integration check failed: `{str(e)}`.\nEnsure bot is added to private group/channel first.", parse_mode="Markdown")
            return

        default_chan_plans = {
            "Monthly": 199,
            "Yearly": 1499,
            "Lifetime": 3999
        }

        channels_col.update_one(
            {"_id": channel_id},
            {"$set": {
                "channel_name": channel_name,
                "description": chat.description or "Exclusive Private Premium Channel Access",
                "plans": default_chan_plans,
                "status": "active"
            }},
            upsert=True
        )

        bot.reply_to(
            message,
            f"✅ *Private Channel Linked Successfully!*\n\n"
            f"📢 *Name:* {channel_name}\n"
            f"🆔 *ID:* `{channel_id}`\n\n"
            f"🔗 *Deep link for users:*\n"
            f"`https://t.me/{bot.get_me().username}?start=sub_chan_{channel_id}`\n\n"
            f"Default plans registered automatically:\n"
            f"- Monthly: ₹199\n- Yearly: ₹1499\n- Lifetime: ₹3999\n"
            f"Adjust rates inside the `channels` collection if custom configurations are needed.",
            parse_mode="Markdown"
        )

    @bot.message_handler(commands=['broadcast'])
    def handle_broadcast(message):
        if not is_admin(message.from_user.id):
            return
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Format: `/broadcast <text>`", parse_mode="Markdown")
            return
        
        bc_msg = parts[1]
        all_users = users_col.find({})
        
        sent, failed = 0, 0
        for u in all_users:
            try:
                bot.send_message(u["_id"], bc_msg)
                sent += 1
            except Exception:
                failed += 1
                
        bot.reply_to(message, f"📢 *Broadcast Complete*\n\n✅ Sent: {sent}\n❌ Failed: {failed}", parse_mode="Markdown")
