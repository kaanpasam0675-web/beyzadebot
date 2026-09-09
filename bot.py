import os
import random
import sys
import threading
from datetime import datetime

import discord
from discord.ext import commands

import config
import database

BOT = None


def get_bot():
    global BOT
    return BOT


intents = discord.Intents.default()
intents.message_content = True
intents.members = True


VOICE_CHANNEL_ID = 1537215483168956498
LEVEL_UP_CHANNEL_ID = 1546441566397141074


class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=self._db_prefix,
            intents=intents,
            help_command=None,
        )

    async def _db_prefix(self, bot, message):
        if not message.guild:
            return "!"
        try:
            return database.get_prefix(message.guild.id)
        except Exception:
            return "!"

    async def setup_hook(self):
        await self.load_extension("cogs.moderation")
        await self.load_extension("cogs.fun")
        await self.load_extension("cogs.levels")
        await self.load_extension("cogs.tickets")
        await self.load_extension("cogs.custom")
        await self.tree.sync()

    async def on_ready(self):
        database.init_db()
        print(f"[OK] Bot giriş yaptı: {self.user} ({self.user.id})")
        print(f"[OK] Sunucu sayısı: {len(self.guilds)}")
        try:
            cog = self.get_cog("Custom")
            if cog is not None:
                await cog.sync_all(self)
        except Exception as e:
            print(f"[UYARI] Slash eşitleme başlatılamadı: {e}")
        await self._join_voice()

    async def _join_voice(self):
        try:
            log_path = os.path.join(os.path.dirname(__file__), "voice_join.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] _join_voice basladi\n")
            voice_channel = self.get_channel(VOICE_CHANNEL_ID)
            if voice_channel is not None and isinstance(voice_channel, discord.VoiceChannel):
                await voice_channel.connect()
                print(f"[OK] Ses kanalına bağlanıldı: {voice_channel.name}")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().isoformat()}] Baglandi: {voice_channel.name}\n")
            else:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().isoformat()}] Ses kanali bulunamadi veya VoiceChannel degil: {VOICE_CHANNEL_ID}\n")
        except Exception as e:
            print(f"[UYARI] Ses kanalına bağlanılamadı: {e}")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] HATA: {e}\n")

    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        prefix = database.get_prefix(message.guild.id)
        # XP kazanımı (seviye modülü tarafından değil, mesaj hook'u)
        try:
            level, leveled = database.add_xp(message.guild.id, message.author.id, 10)
            if leveled:
                embed = discord.Embed(
                    title="Seviye atladın!",
                    description=f"Tebrikler {message.author.mention}, **{level}. seviyeye** ulaştın!",
                    color=0x57F287,
                )
                target = self.get_channel(LEVEL_UP_CHANNEL_ID)
                if target is not None:
                    await target.send(embed=embed)
                else:
                    await message.channel.send(embed=embed)
        except Exception:
            pass
        if message.content.startswith(prefix):
            await self.process_commands(message)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        try:
            await ctx.send(f"⚠️ Komut hatası: `{type(error).__name__}: {error}`")
        except Exception:
            pass

    async def on_guild_join(self, guild):
        database.init_db()
        print(f"[OK] Yeni sunucuya katıldı: {guild.name} ({guild.id})")
        try:
            role = discord.utils.get(guild.roles, name="Beyzade Bot sahibi")
            if role is None:
                role = await guild.create_role(
                    name="Beyzade Bot sahibi",
                    reason="Beyzade Bot otomatik sahiplik rolü",
                )
                print(f"[OK] '{role.name}' rolü oluşturuldu: {guild.name}")
        except Exception as e:
            print(f"[UYARI] rol oluşturulamadı ({guild.name}): {e}")
        # Sunucu için tanımlı tag varsa botun o sunucudaki adını ayarla
        try:
            settings = database.get_guild_settings(guild.id)
            tag = (settings.get("bot_tag") or "").strip()
            if tag:
                new_nick = f"{tag} {self.user.name}"
                if guild.me.nick != new_nick:
                    await guild.me.edit(nick=new_nick)
                    print(f"[OK] Nickname '{new_nick}' olarak ayarlandı ({guild.name})")
        except Exception as e:
            print(f"[UYARI] nickname ayarlanamadı ({guild.name}): {e}")

    async def on_member_join(self, member):
        if member.bot:
            return
        try:
            settings = database.get_guild_settings(member.guild.id)
            if settings.get("auto_role"):
                role = member.guild.get_role(int(settings["auto_role"]))
                if role and role < member.guild.me.top_role:
                    await member.add_roles(role)
            if settings.get("welcome_channel"):
                channel = member.guild.get_channel(int(settings["welcome_channel"]))
                if channel:
                    text = (
                        settings.get("welcome_message")
                        or "Sunucumuza hoş geldin {mention}!"
                    ).replace("{mention}", member.mention).replace("{user}", member.name)
                    await channel.send(text)
        except Exception as e:
            print(f"[UYARI] karşılama/auto-rol hatası: {e}")

    async def _auto_role(self, member):
        try:
            settings = database.get_guild_settings(member.guild.id)
            if settings.get("auto_role"):
                role = member.guild.get_role(int(settings["auto_role"]))
                if role:
                    await member.add_roles(role)
        except Exception:
            pass


def run_bot():
    global BOT
    bot = Bot()
    BOT = bot
    try:
        bot.run(config.DISCORD_TOKEN)
    except discord.LoginFailure:
        print("[HATA] Token geçersiz! .env dosyasındaki DISCORD_TOKEN'u kontrol et.")
        sys.exit(1)
    except Exception as e:
        print(f"[HATA] Bot başlatılamadı: {e}")
        sys.exit(1)


def start_bot_thread():
    """Dashboard çalışırken botu ayrı thread'de başlatır."""
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    print("[OK] Başlatılıyor...")
    run_bot()