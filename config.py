import os
from dotenv import load_dotenv

load_dotenv()


# ===== Telegram Bot =====
BOT_TOKEN = os.getenv("BOT_TOKEN")


# ===== Webhook (Render) =====
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default_secret")
WEBHOOK_PATH = "/webhook"

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8080))


# ===== База данных (Supabase PostgreSQL) =====
DATABASE_URL = os.getenv("DATABASE_URL")


# ===== Ранги Valorant =====
RANKS = [
    "Iron 1", "Iron 2", "Iron 3",
    "Bronze 1", "Bronze 2", "Bronze 3",
    "Silver 1", "Silver 2", "Silver 3",
    "Gold 1", "Gold 2", "Gold 3",
    "Platinum 1", "Platinum 2", "Platinum 3",
    "Diamond 1", "Diamond 2", "Diamond 3",
    "Ascendant 1", "Ascendant 2", "Ascendant 3",
    "Immortal 1", "Immortal 2", "Immortal 3",
    "Radiant",
]


# ===== Поиск =====
RANK_TOLERANCE = 2