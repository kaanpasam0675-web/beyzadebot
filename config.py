import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5000"))
AUTO_ROLE = os.getenv("AUTO_ROLE", "")
MOD_LOG_CHANNEL_ID = 1546444871856955392
AUTO_CHAT_CHANNEL_ID = 1546461055222292530

# Discord OAuth2 (Birden fazla sunucu admininin dashboard kullanımı için)
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
# OAuth dönüş adresi — Discord Developer Portal'da kayıtlı olanla aynı olmalı
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://127.0.0.1:5000/login/discord/callback")

# Bot davet izinleri — Discord otorizasyon ekranında listelenir (moderasyon + ses + kanal/rol yönetimi)
INVITE_URL = (
    f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}"
    "&permissions=1507532860663&scope=bot%20applications.commands"
)

PREFIX = "!"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")