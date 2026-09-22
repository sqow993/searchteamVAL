import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default_secret")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # https://xxx.onrender.com
RIOT_API_KEY = os.getenv("RIOT_API_KEY", "RGAPI-b14180a7-8b57-4a5d-8e68-174e4f095f69")

DB_PATH = "valorant_bot.db"

WEBHOOK_PATH = "/webhook"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8080))

RANKS = [
    "Iron", "Bronze", "Silver", "Gold", "Platinum",
    "Diamond", "Ascendant", "Immortal", "Radiant"
]