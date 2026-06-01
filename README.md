# Telegram Premium Subscription & Private Channel Management Bot

A drop-in subscription database engine and private channel access manager built with Python (`pyTelegramBotAPI`), MongoDB Atlas, `APScheduler`, and `Flask`.

This system operates simultaneously in two modes:
1. **Bot Feature Paywall:** Limits normal bot commands to a configurable number of free uses per day, offering unlimited access for active Premium subscribers.
2. **Private Channel Membership Manager:** Sells entry links to unlimited private channels with varying pricing tiers, and automatically removes users when their subscription expires.

---

## Architecture Flow

### A. Bot Feature Protection Flow
```text
User sends /imagine -> Bot checks subscription -> 
  [Active] -> Executes command
  [Free Tier] -> Uses daily balance -> Executes command
  [Limit Reached] -> Displays Bot Premium Plans -> Generates UPI QR -> 
    User uploads screenshot -> Admin approves -> Subscription activated.

B. Private Channel Referral Flow

User opens link https://t.me/Bot?start=sub_chan_-100xxxxxxxx ->
  Bot displays channel description & packages -> User chooses Plan -> 
  Bot displays QR code -> User uploads screenshot -> Admin approves -> 
  Bot generates unique, single-use, 24-hour expiring invite link ->
  User joins -> System bans and unbans user instantly when subscription expires.

Prerequisites

1.  Telegram Bot Token: Obtained from @BotFather.
2.  MongoDB Atlas URI: A standard MongoDB Atlas cluster connection string
    (mongodb+srv://...).
3.  Business UPI ID: Any active Indian UPI Address (e.g., merchant@upi or
    name@bank) to generate real-time dynamic payment QR codes.
4.  Target Private Channels: You must add the bot to your private channels as an
    Administrator with Manage Invite Links and Ban Users privileges.

Configuration

Create a .env file in the root directory:

BOT_TOKEN=1234567890:ABCdefGhIJKLMNOPQ
MONGO_URI=mongodb+srv://admin:password@cluster.mongodb.net/database
ADMIN_IDS=123456789,987654321
UPI_ID=your-upi-id@bank
CONTACT_USERNAME=YourAdminUsername

Note: Ensure ADMIN_IDS is a comma-separated list of numeric Telegram User IDs
(without spaces).

Setup & Local Execution

1. Clone & Install Dependencies

Ensure you have Python 3.10+ installed.

python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

2. Connect Your Private Channels

1.  Start your bot.
2.  Log in as an administrator (your ID must be in ADMIN_IDS).
3.  Send the command /addchannel.
4.  Forward any message from the target private channel to the bot.
5.  The bot will automatically detect the Channel ID, verify its own admin
    status inside the channel, and configure standard pricing structures
    (Monthly: ₹199, Yearly: ₹1499, Lifetime: ₹3999).
6.  Copy the generated deep link to share with users.

3. Edit Pricing Plans

  - Bot Premium Plans: Can be directly updated inside the MongoDB settings
    collection under the document _id: "bot_plans".
  - Private Channel Pricing: Can be custom configured on a per-channel basis in
    the MongoDB channels collection.

Admin Commands

These commands are strictly restricted to IDs specified in ADMIN_IDS or added
via /addadmin:

  - /admin - Displays global metrics, active revenue, pending payments, and
    active subscribers.
  - /plans - Shows active pricing packages configured for the bot.
  - /users - Queries active VIP subscription lists.
  - /addchannel - Connects a private channel to the database.
  - /broadcast <msg> - Sends a global notification to all registered users.
  - /addadmin <user_id> - Grants admin permissions to a new user.
  - /removeadmin <user_id> - Revokes administrative privileges.


---

### 2. `Dockerfile`

For containerized cloud hosting environments (such as Render, Railway, AWS, or local Docker daemons), use this `Dockerfile`:

```dockerfile
# Use official lightweight Python image
FROM python:3.10-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies needed for Pillow/imaging compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python package requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source files to working directory
COPY . .

# Expose port for Flask Keep-Alive framework/Webhooks
EXPOSE 5000

# Execute command to start the application
CMD ["python", "main.py"]

3. docker-compose.yml

This setup provides multi-container environment configurations:

version: '3.8'

services:
  telegram_bot:
    build: .
    container_name: subscription_bot
    restart: always
    ports:
      - "5000:5000"
    env_file:
      - .env
    volumes:
      - .:/app

Deploy using docker-compose:

docker compose up -d --build

4. VPS Deployment (using systemd)

For deployment on a dedicated Linux VPS (Ubuntu/Debian), use systemd to manage
the process and keep it running in the background.

Step 1: Place code on VPS

Clone your code to your server directory (e.g.,
/home/ubuntu/telegram-subscription-bot).

Step 2: Initialize Virtual Environment

cd /home/ubuntu/telegram-subscription-bot
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

Step 3: Create System Service

Create a systemd unit configuration file:

sudo nano /etc/systemd/system/subscription.service

Paste the following configurations:

[Unit]
Description=Telegram Subscription and Channel Manager Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/telegram-subscription-bot
ExecStart=/home/ubuntu/telegram-subscription-bot/venv/bin/python main.py
Restart=always
RestartSec=5
EnvironmentFile=/home/ubuntu/telegram-subscription-bot/.env

[Install]
WantedBy=multi-user.target

Note: Adjust User and directory pathways based on your specific VPS operating
environment.

Step 4: Start and Enable the Service

# Reload systemd manager configurations
sudo systemctl daemon-reload

# Enable service to automatically start on boot
sudo systemctl enable subscription.service

# Start the service
sudo systemctl start subscription.service

# Verify the operational status
sudo systemctl status subscription.service

Step 5: Monitor Logs

To inspect live operating log metrics of your running bot:

journalctl -u subscription.service -f -n 100
