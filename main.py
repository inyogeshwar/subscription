import threading
import telebot
from flask import Flask
from subscription.config import BOT_TOKEN
from subscription.database import init_db
from subscription.payment_manager import register_payment_handlers, process_start_deep_link
from subscription.admin_manager import register_admin_handlers
from subscription.expiry_scheduler import start_expiry_scheduler
from subscription.subscription_manager import premium_required

# Flask Server Configuration
app = Flask(__name__)

@app.route('/')
def health_check():
    return {"status": "operational", "system": "Premium Subscription System"}, 200

def run_flask_server():
    app.run(host="0.0.0.0", port=5000)

# Initialize Botanical core engine
bot = telebot.TeleBot(BOT_TOKEN)

# DB Schema and static initialization
init_db()

# Start background cron operations
start_expiry_scheduler(bot)

# Register subscription mechanics handlers
register_payment_handlers(bot)
register_admin_handlers(bot)


# --- EXAMPLES OF EXISTING BOT COMMANDS ---

@bot.message_handler(commands=['start'])
def handle_bot_start(message):
    # 1. First, attempt to parse for channel referral deep links.
    # If it is a deep link, the system will process pricing tables and return True.
    if process_start_deep_link(bot, message):
        return
    
    # 2. Otherwise, safe bypass logic: Execute your existing bot behavior code down here
    bot.reply_to(
        message, 
        "👋 Welcome to our Multi-functional Bot!\n\n"
        "✨ Type /buy to purchase premium features access\n"
        "✨ Type any protected bot command like /imagine, /download or /chat to begin."
    )

# Any commands added below are completely protected by check_subscription checking
@bot.message_handler(commands=['imagine', 'download', 'chat', 'generate'])
@premium_required(bot)
def handle_premium_commands(message):
    cmd_name = message.text.split()[0]
    bot.reply_to(message, f"⚡ *[Premium Active]* Processing request for command `{cmd_name}`...")


if __name__ == "__main__":
    # Start Keep-Alive web framework in Background
    t = threading.Thread(target=run_flask_server, daemon=True)
    t.start()
    
    # Start Non-blocking Infinity Polling interface
    print("Bot is successfully listening for updates...")
    bot.infinity_polling()
