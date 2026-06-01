import datetime
from bson.objectid import ObjectId
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from subscription.database import (
    users_col, payments_col, subscriptions_col, channels_col, settings_col, log_event, is_admin
)
from subscription.qr_generator import generate_upi_qr
from subscription.config import UPI_ID, CONTACT_USERNAME, ADMIN_IDS

def get_bot_plans():
    doc = settings_col.find_one({"_id": "bot_plans"})
    return doc["plans"] if doc else {}

def show_bot_plans_keyboard():
    plans = get_bot_plans()
    markup = InlineKeyboardMarkup()
    for plan_name, info in plans.items():
        price = info["price"]
        markup.add(InlineKeyboardButton(f"✨ {plan_name} - ₹{price}", callback_data=f"select_plan:bot:{plan_name}"))
    return markup

def show_channel_plans_keyboard(channel_id):
    channel = channels_col.find_one({"_id": int(channel_id)})
    if not channel or not channel.get("plans"):
        return None
    markup = InlineKeyboardMarkup()
    for plan_name, price in channel["plans"].items():
        markup.add(InlineKeyboardButton(f"⚡ {plan_name} - ₹{price}", callback_data=f"select_plan:chan:{channel_id}:{plan_name}"))
    return markup

def initiate_payment(bot: telebot.TeleBot, user_id, chat_id, target_type, target_id, plan_name):
    if target_type == "bot":
        plans = get_bot_plans()
        price = plans.get(plan_name, {}).get("price", 0)
        display_name = "Bot Premium"
    else:
        channel = channels_col.find_one({"_id": int(target_id)})
        price = channel["plans"].get(plan_name, 0) if channel else 0
        display_name = channel.get("channel_name", "Private Channel") if channel else "Private Channel"

    if price <= 0:
        bot.send_message(chat_id, "❌ Error retrieving selected pricing matrix. Contact support.")
        return

    payment_id = ObjectId()
    payments_col.insert_one({
        "_id": payment_id,
        "user_id": int(user_id),
        "target_type": target_type,
        "target_id": target_id,
        "plan": plan_name,
        "amount": price,
        "status": "pending_upload",
        "timestamp": datetime.datetime.utcnow()
    })

    # Put user in active payment pipeline state
    users_col.update_one(
        {"_id": int(user_id)},
        {"$set": {
            "current_payment_id": str(payment_id),
            "state": "waiting_for_payment_screenshot"
        }},
        upsert=True
    )

    qr_img = generate_upi_qr(UPI_ID, price, label=f"SUB_{user_id}")
    caption = (
        f"💳 *UPI Instant Payment Gateway*\n\n"
        f"🔹 *Service:* {display_name}\n"
        f"🔹 *Plan:* {plan_name}\n"
        f"🔹 *Total Amount:* ₹{price}\n"
        f"🔹 *Payment Address (UPI ID):* `{UPI_ID}`\n\n"
        f"👉 *Instructions:*\n"
        f"1. Scan the QR code or send amount to our business UPI ID.\n"
        f"2. Take a transaction confirmation screenshot.\n"
        f"3. *Send the screenshot photo directly to this chat* to initiate admin review."
    )
    bot.send_photo(chat_id, photo=qr_img, caption=caption, parse_mode="Markdown")

def handle_screenshot_upload(bot: telebot.TeleBot, message: telebot.types.Message):
    user_id = message.from_user.id
    user_doc = users_col.find_one({"_id": int(user_id)})
    
    if not user_doc or user_doc.get("state") != "waiting_for_payment_screenshot":
        return False

    payment_id_str = user_doc.get("current_payment_id")
    if not payment_id_str:
        return False

    if not message.photo:
        bot.reply_to(message, "⚠️ Waiting for payment screenshot. Please send the receipt as a *Photo*.")
        return True

    file_id = message.photo[-1].file_id
    payment_id = ObjectId(payment_id_str)
    
    payments_col.update_one(
        {"_id": payment_id},
        {"$set": {
            "status": "pending_approval",
            "screenshot_file_id": file_id,
            "timestamp": datetime.datetime.utcnow()
        }}
    )

    # Clean active transaction states safely
    users_col.update_one(
        {"_id": int(user_id)},
        {"$unset": {"state": "", "current_payment_id": ""}}
    )

    bot.reply_to(
        message, 
        "✅ *Screenshot successfully loaded!*\nOur verification team is validating your transfer. You will be notified instantly once confirmed.",
        parse_mode="Markdown"
    )

    # Inform registered admins
    payment_doc = payments_col.find_one({"_id": payment_id})
    target_name = "Bot Premium"
    if payment_doc.get("target_type") == "chan":
        chan = channels_col.find_one({"_id": int(payment_doc["target_id"])})
        target_name = f"Channel: {chan['channel_name']}" if chan else "Channel"

    admin_caption = (
        f"🔔 *NEW MANUAL PAYMENT REVIEW*\n\n"
        f"👤 *User:* {message.from_user.first_name} (@{message.from_user.username or 'N/A'})\n"
        f"🆔 *ID:* `{user_id}`\n"
        f"📦 *Product:* {target_name}\n"
        f"💎 *Plan Chosen:* {payment_doc['plan']}\n"
        f"💰 *Transaction Value:* ₹{payment_doc['amount']}\n"
    )

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ Approve", callback_data=f"admin_pay:approve:{payment_id_str}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"admin_pay:reject:{payment_id_str}")
    )

    for admin_id in ADMIN_IDS:
        try:
            bot.send_photo(admin_id, photo=file_id, caption=admin_caption, reply_markup=markup, parse_mode="Markdown")
        except Exception as e:
            log_event("error", f"Payment review submission error for Admin {admin_id}", str(e))
            
    return True

def process_admin_action(bot: telebot.TeleBot, call: telebot.types.CallbackQuery):
    data_parts = call.data.split(":")
    action = data_parts[1]
    payment_id_str = data_parts[2]

    payment_id = ObjectId(payment_id_str)
    payment = payments_col.find_one({"_id": payment_id})

    if not payment:
        bot.answer_callback_query(call.id, "Payment record not found.", show_alert=True)
        return

    if payment["status"] != "pending_approval":
        bot.answer_callback_query(call.id, f"Already processed: {payment['status']}", show_alert=True)
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
        return

    user_id = payment["user_id"]
    target_type = payment["target_type"]
    target_id = payment["target_id"]
    plan_name = payment["plan"]

    if action == "approve":
        days = 30
        if target_type == "bot":
            plans = get_bot_plans()
            days = plans.get(plan_name, {}).get("days", 30)
        else:
            mapping = {"Daily": 1, "Weekly": 7, "Monthly": 30, "Yearly": 365, "Lifetime": 9999}
            days = mapping.get(plan_name, 30)

        expiry_date = datetime.datetime.utcnow() + datetime.timedelta(days=days)

        payments_col.update_one({"_id": payment_id}, {"$set": {"status": "approved"}})

        # Record or extend existing membership metrics
        subscriptions_col.update_one(
            {"user_id": int(user_id), "target_id": target_id},
            {"$set": {
                "plan": plan_name,
                "start_date": datetime.datetime.utcnow(),
                "expiry_date": expiry_date,
                "status": "active",
                "notified_24h": False,
                "notified_1h": False
            }},
            upsert=True
        )

        log_event("info", f"Verified transaction {plan_name} for subscriber {user_id}")
        bot.answer_callback_query(call.id, "Subscription Activated!")
        
        bot.edit_message_caption(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            caption=call.message.caption + "\n\n🟢 *APPROVED BY ADMIN*",
            reply_markup=None,
            parse_mode="Markdown"
        )

        if target_type == "bot":
            bot.send_message(
                user_id,
                f"🎉 *Subscription Activated!*\n\n"
                f"Your *Bot Premium* features are now unlocked.\n"
                f"📅 *Expiry:* {expiry_date.strftime('%Y-%m-%d %H:%M UTC')}",
                parse_mode="Markdown"
            )
        else:
            try:
                invite_expiry = int(datetime.datetime.utcnow().timestamp()) + 86400 # Link valid 24h
                invite = bot.create_chat_invite_link(
                    chat_id=int(target_id),
                    expire_date=invite_expiry,
                    member_limit=1
                )
                invite_link = invite.invite_link
                
                chan = channels_col.find_one({"_id": int(target_id)})
                chan_name = chan["channel_name"] if chan else "Private Channel"

                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🔗 Enter Private Channel", url=invite_link))

                bot.send_message(
                    user_id,
                    f"🎉 *Channel Access Activated!*\n\n"
                    f"You have been successfully added as a subscriber to *{chan_name}*.\n"
                    f"📅 *Expiry:* {expiry_date.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                    f"👉 Use the single-use invite button below to join:",
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
            except Exception as e:
                log_event("error", f"Single-use link failed for {target_id}", str(e))
                bot.send_message(
                    user_id,
                    f"⚠️ *Payment Confirmed!* However, we could not generate an invite link automatically.\n"
                    f"Please contact support: @{CONTACT_USERNAME} with screenshot for manual entry.",
                    parse_mode="Markdown"
                )

    elif action == "reject":
        payments_col.update_one({"_id": payment_id}, {"$set": {"status": "rejected"}})
        bot.answer_callback_query(call.id, "Payment Rejected.")
        
        bot.edit_message_caption(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            caption=call.message.caption + "\n\n🔴 *REJECTED BY ADMIN*",
            reply_markup=None,
            parse_mode="Markdown"
        )

        bot.send_message(
            user_id,
            f"❌ *Transaction Validation Failed*\n\n"
            f"The uploaded screenshot has been declined by validators. Direct queries to support @{CONTACT_USERNAME}.",
            parse_mode="Markdown"
        )

def process_start_deep_link(bot: telebot.TeleBot, message: telebot.types.Message):
    """
    Parses deep link referrals for private channel options.
    Exits gracefully and passes to normal bot behavior if not matching format.
    """
    text = message.text
    if not text.startswith("/start "):
        return False
        
    param = text.split(" ")[1]
    if not param.startswith("sub_chan_"):
        return False
        
    try:
        channel_id = int(param.replace("sub_chan_", ""))
    except ValueError:
        return False

    channel = channels_col.find_one({"_id": channel_id})
    if not channel:
        bot.send_message(message.chat.id, "❌ Specified private subscription channel not found in database registry.")
        return True

    markup = show_channel_plans_keyboard(channel_id)
    if not markup:
        bot.send_message(message.chat.id, "❌ Channel plans have not been configured yet.")
        return True

    intro = (
        f"📢 *Premium Channel Membership*\n\n"
        f"🚪 *Channel:* {channel['channel_name']}\n"
        f"📝 *Description:* {channel.get('description', '')}\n\n"
        f"👉 Purchase a subscription membership package below to proceed:"
    )
    bot.send_message(message.chat.id, intro, reply_markup=markup, parse_mode="Markdown")
    return True

def register_payment_handlers(bot: telebot.TeleBot):
    """
    Registers payment events inside TeleBot handler stack.
    """
    @bot.callback_query_handler(func=lambda call: call.data == "buy_bot_plans")
    def handle_buy_bot_plans(call: telebot.types.CallbackQuery):
        markup = show_bot_plans_keyboard()
        bot.send_message(
            call.message.chat.id,
            "🌟 *Choose your Bot Premium Membership plan:*",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("buy_chan_plans:"))
    def handle_buy_chan_plans(call: telebot.types.CallbackQuery):
        channel_id = int(call.data.split(":")[1])
        markup = show_channel_plans_keyboard(channel_id)
        if not markup:
            bot.send_message(call.message.chat.id, "❌ Channel subscription packages missing.")
            return
            
        bot.send_message(
            call.message.chat.id,
            "⚡ *Select Channel Membership Package:*",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("select_plan:"))
    def handle_select_plan(call: telebot.types.CallbackQuery):
        parts = call.data.split(":")
        target_type = parts[1]
        
        if target_type == "bot":
            plan_name = parts[2]
            initiate_payment(bot, call.from_user.id, call.message.chat.id, "bot", "bot", plan_name)
        else:
            channel_id = int(parts[2])
            plan_name = parts[3]
            initiate_payment(bot, call.from_user.id, call.message.chat.id, "chan", channel_id, plan_name)
            
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_pay:"))
    def handle_admin_payment_button(call: telebot.types.CallbackQuery):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Unauthorized.", show_alert=True)
            return
        process_admin_action(bot, call)

    # Strictly capture photos only if user has active "waiting_for_payment_screenshot" status
    @bot.message_handler(content_types=['photo'], func=lambda msg: users_col.find_one({"_id": msg.from_user.id, "state": "waiting_for_payment_screenshot"}) is not None)
    def handle_screenshot_photo(message):
        handle_screenshot_upload(bot, message)
