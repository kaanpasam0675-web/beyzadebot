import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5000"))
AUTO_ROLE = os.getenv("AUTO_ROLE", "")
MOD_LOG_CHANNEL_ID = 1546444871856955392
AUTO_CHAT_CHANNEL_ID = 1547601582160617523

# Discord OAuth2 (Birden fazla sunucu admininin dashboard kullanımı için)
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
# OAuth dönüş adresi — Discord Developer Portal'da kayıtlı olanla aynı olmalı
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://127.0.0.1:5000/login/discord/callback")

# Bot sahibinin Discord kullanıcı ID'si (sadece bu kişi tam erişime sahip olur)
OWNER_DISCORD_ID = int(os.getenv("OWNER_DISCORD_ID", "1486064551869943828"))

# Sahip gibi tam erişime sahip ek kullanıcı ID'leri (dashboard + bot komutları)
EXTRA_AUTHORIZED_IDS = [int(x.strip()) for x in os.getenv("EXTRA_AUTHORIZED_IDS", "1526291312557555722").split(",") if x.strip().isdigit()]


def is_authorized(user_id):
    """Sahip veya yetkili ek kullanıcı mı?"""
    return user_id == OWNER_DISCORD_ID or user_id in EXTRA_AUTHORIZED_IDS

# Bot davet izinleri — Discord otorizasyon ekranında listelenir (moderasyon + ses + kanal/rol yönetimi)
INVITE_URL = (
    f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}"
    "&permissions=1507532860663&scope=bot%20applications.commands"
)

PREFIX = "!"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")

# Google Gemini AI sohbet (https://aistudio.google.com -> Get API key)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")