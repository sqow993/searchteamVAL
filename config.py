import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default_secret")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # https://xxx.onrender.com

DB_PATH = "valorant_bot.db"

WEBHOOK_PATH = "/webhook"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8080))

RANKS = [
    "Iron", "Bronze", "Silver", "Gold", "Platinum",
    "Diamond", "Ascendant", "Immortal", "Radiant"
]