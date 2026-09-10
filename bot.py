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
                f"**{role.name}** rolü oluşturuldu ve en üste taşındı.\n"
                "Rolü sunucu sahibine vererek yönetimi başlatabilirsiniz.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "❌ Rol oluşturulamadı!\n"
                "**Beyzade Bot** rolünün sunucu ayarlarından **en üste** taşınması gerekiyor.\n"
                "Yönetici ayarlar -> Roller -> Beyzade Bot rolünü en üste çekin, "
                "sonra tekrar butona tıklayın.",
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
        admin_roles = [r for r in guild.roles if r.permissions.administrator and r != guild.default_role]
        mentions = " ".join(r.mention for r in admin_roles) if admin_roles else ""
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
                "⚠️ **ÖNEMLİ:** Sözleşmeyi kabul etmeden önce, sunucu ayarlarından "
                "**Beyzade Bot** rolünü **en üste taşıyın**.\n"
                "Aksi takdirde rol oluşturulamaz ve bot bazı işlemleri yapamaz.\n\n"
                "Butona tıklayarak sözleşmeyi kabul edin."
            ),
            color=0x5865F2,
            timestamp=datetime.utcnow(),
        )
        embed.set_footer(text="Beyzade Bot • Sözleşme")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        view = ContractView(self)
        channel = await self._find_contract_channel(guild)
        if channel is None:
            print(f"[UYARI] Sözleşme gönderilecek kanal bulunamadı: {guild.name} ({guild.id})")
            return
        try:
            await channel.send(content=mentions, embed=embed, view=view)
            print(f"[OK] Sözleşme gönderildi: {guild.name} -> #{channel.name}")
        except Exception as e:
            print(f"[UYARI] sözleşme gönderilemedi ({guild.name}): {type(e).__name__}: {e}")

    async def _create_owner_role(self, guild):
        role_name = "Beyzade Bot sahibi"
        bot_member = guild.me
        bot_top_role = bot_member.top_role

        me_roles = [r for r in guild.me.roles if r != guild.default_role]
        if me_roles:
            my_highest = max(me_roles, key=lambda r: r.position)
            others = [r for r in guild.roles if r != guild.default_role and r != my_highest and not r.managed]
            if others:
                highest_other = max(others, key=lambda r: r.position)
                if highest_other.position >= my_highest.position:
                    return None

        existing = discord.utils.get(guild.roles, name=role_name)
        if existing:
            try:
                await guild.edit_role_positions({existing: len(guild.roles) - 1})
            except Exception:
                pass
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
            return role
        except Exception:
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
    async def sozlesme_cmd(self, ctx):
        """Sahip: Botun bulunduğu TÜM sunuculara sözleşme gönderir."""
        if ctx.author.id != config.OWNER_DISCORD_ID:
            await ctx.send("❌ Bu komutu sadece bot sahibi kullanabilir.")
            return
        await ctx.send(f"📜 Sözleşme {len(self.guilds)} sunucuya gönderiliyor...")
        lines = []
        for guild in self.guilds:
            try:
                channel = await self._find_contract_channel(guild)
                if channel is None:
                    lines.append(f"❌ {guild.name} — kanal yok")
                    continue
                await self._send_contract(guild)
                lines.append(f"✅ {guild.name} — #{channel.name}")
            except Exception as e:
                lines.append(f"❌ {guild.name} — {type(e).__name__}: {e}")
        msg = "\n".join(lines) if lines else "Sunucu bulunamadı."
        await ctx.send(f"**Sonuç:**\n{msg}")

    async def _find_contract_channel(self, guild):
        channel = guild.system_channel
        if channel is None:
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break
        return channel

    @commands.hybrid_command(name="sozlesme-yenile")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def sozlesme_yenile_cmd(self, ctx):
        """Admin: Bu sunucuya sözleşme mesajını tekrar gönderir."""
        try:
            await self._send_contract(ctx.guild)
            await ctx.send("📜 Sözleşme tekrar gönderildi.")
        except Exception as e:
            await ctx.send(f"❌ Hata: {e}")

    @commands.hybrid_command(name="rol-yukari")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def rol_yukari_cmd(self, ctx):
        """Admin: Beyzade Bot rolünü en üste taşır."""
        role = discord.utils.get(ctx.guild.roles, name="Beyzade Bot sahibi")
        if role is None:
            role = discord.utils.get(ctx.guild.roles, name="Beyzade Bot")
        if role is None:
            await ctx.send("❌ Bot rolü bulunamadı.")
            return
        try:
            await ctx.guild.edit_role_positions({role: len(ctx.guild.roles) - 1})
            await ctx.send(f"✅ **{role.name}** rolü en üste taşındı!")
        except Exception as e:
            await ctx.send(f"❌ Taşınamadı: {e}")

    @commands.command(name="debug-komutlar")
    async def debug_komutlar(self, ctx):
        """Sahip: Kayıtlı tüm prefix komutlarını listeler."""
        if ctx.author.id != config.OWNER_DISCORD_ID:
            return
        names = [c.name for c in self.commands]
        await ctx.send(f"Kayıtlı komutlar ({len(names)}):\n{', '.join(sorted(names))}")


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
