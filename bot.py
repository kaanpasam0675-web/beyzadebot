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


class ContractView(discord.ui.View):
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.bot = bot_instance

    @discord.ui.button(label="Kabul Et", style=discord.ButtonStyle.success, custom_id="contract_accept")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Bu komut sadece sunucularda kullanılabilir.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        role = await self.bot._create_owner_role(guild)
        await self.bot._apply_tag(guild)
        if role:
            await interaction.followup.send(
                "Sözleşme kabul edildi! ✅\n"
                f"**{role.name}** rolü oluşturuldu ve rol sırasının en üstüne taşındı.\n"
                "Rolü sunucu sahibine vererek yönetimi başlatabilirsiniz.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "Sözleşme kabul edildi ancak rol oluşturulurken hata oluştu. "
                "Lütfen botun yetkilerini kontrol edin.",
                ephemeral=True,
            )


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
        self.add_view(ContractView(self))
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
        await self._send_contract(guild)

    async def _send_contract(self, guild):
        embed = discord.Embed(
            title="Beyzade Bot Kullanım Sözleşmesi",
            description=(
                "Botu sunucunuza ekleyerek aşağıdaki şartları kabul etmiş sayılırsınız:\n\n"
                "1️⃣ Bot yalnızca sunucu yönetim amaçlı kullanılır.\n"
                "2️⃣ Bot verileri (komut, ayar, ticket vb.) sunucu sahibi tarafından yönetilir.\n"
                "3️⃣ Botun amacı dışı kullanımı yasaktır.\n"
                "4️⃣ Verileriniz (sunucu ID, komut kayıtları) bot yönetim amaçlı saklanır.\n"
                "5️⃣ Dashboard erişimi yalnızca sunucu adminlerine açıktır.\n"
                "6️⃣ Bot sahibi, kötüye kullanım tespitinde botu sunucudan çıkarma hakkına sahiptir.\n\n"
                "Aşağıdaki butona tıklayarak sözleşmeyi kabul edin.\n"
                "Kabul edildiğinde **yönetici yetkilerine sahip rol** oluşturulacak ve "
                "sunucu rol sırasının en üstüne taşınacaktır."
            ),
            color=0x5865F2,
            timestamp=datetime.utcnow(),
        )
        embed.set_footer(text="Beyzade Bot • Sözleşme")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        view = ContractView(self)
        channel = guild.system_channel
        if channel is None:
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break
        if channel is None:
            print(f"[UYARI] Sözleşme gönderilecek kanal bulunamadı: {guild.name}")
            return
        try:
            await channel.send(embed=embed, view=view)
            print(f"[OK] Sözleşme gönderildi: {guild.name} -> #{channel.name}")
        except Exception as e:
            print(f"[UYARI] gönderilemedi ({guild.name}): {e}")

    async def _create_owner_role(self, guild):
        role_name = "Beyzade Bot sahibi"
        existing = discord.utils.get(guild.roles, name=role_name)
        if existing:
            try:
                await guild.edit_role_positions({existing: len(guild.roles) - 1})
                print(f"[OK] Rol zaten var, en üste taşındı: {guild.name}")
            except Exception as e:
                print(f"[UYARI] rol taşınamadı ({guild.name}): {e}")
            return existing
        try:
            role = await guild.create_role(
                name=role_name,
                permissions=discord.Permissions(administrator=True),
                reason="Beyzade Bot sözleşme kabulü",
                hoist=True,
                mentionable=True,
            )
            await guild.edit_role_positions({role: len(guild.roles) - 1})
            print(f"[OK] '{role.name}' rolü oluşturuldu + en üste taşındı: {guild.name}")
            return role
        except Exception as e:
            print(f"[UYARI] rol oluşturulamadı ({guild.name}): {e}")
            return None

    async def _apply_tag(self, guild):
        try:
            settings = database.get_guild_settings(guild.id)
            tag = (settings.get("bot_tag") or "").strip()
            if tag:
                new_nick = f"{tag} {self.user.name}"
                if guild.me.nick != new_nick:
                    await guild.me.edit(nick=new_nick)
        except Exception:
            pass

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

    @commands.command(name="sozlesme")
    @commands.is_owner()
    async def sozlesme_cmd(self, ctx):
        """Sahip: Botun bulunduğu TÜM sunuculara sözleşme gönderir."""
        await ctx.send(f"📜 Sözleşme {len(self.guilds)} sunucuya gönderiliyor...")
        sent = 0
        failed = 0
        for guild in self.guilds:
            try:
                await self._send_contract(guild)
                sent += 1
            except Exception:
                failed += 1
        await ctx.send(f"✅ Tamamlandı: {sent} başarılı, {failed} başarısız.")

    @commands.command(name="sozlesme-kabul")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def sozlesme_kabul_cmd(self, ctx):
        """Admin: Sözleşmeyi kabul edip yönetici rolünü oluşturur."""
        role = await self._create_owner_role(ctx.guild)
        await self._apply_tag(ctx.guild)
        if role:
            await ctx.send(
                f"✅ Sözleşme kabul edildi! **{role.name}** rolü oluşturuldu ve en üste taşındı."
            )
        else:
            await ctx.send("❌ Rol oluşturulurken hata oluştu. Bot yetkilerini kontrol edin.")


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
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    print("[OK] Başlatılıyor...")
    run_bot()
