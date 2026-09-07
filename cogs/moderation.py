import asyncio

import discord
from discord import app_commands
from discord.ext import commands

import config
import database


def mod_only():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_messages:
            return True
        raise commands.MissingPermissions(["manage_messages"])

    return commands.check(predicate)


class Moderation(commands.Cog):
    ACTION_EMOJI = {
        "temizle": "🗑️", "kick": "👢", "ban": "🔨", "unban": "✅",
        "uyar": "⚠️", "sustur": "🔇", "unsustur": "🔊", "kilit": "🔒",
        "unkilit": "🔓", "rol": "🎖️",
    }

    def __init__(self, bot):
        self.bot = bot

    async def _post_mod_embed(self, ctx, action, target_name, reason=""):
        channel = self.bot.get_channel(config.MOD_LOG_CHANNEL_ID)
        if channel is None:
            return None
        emoji = self.ACTION_EMOJI.get(action, "🛠️")
        embed = discord.Embed(
            title="Yeni işlem uygulandı!",
            description=f"{emoji} **{action}**",
            color=0xFEE75C,
        )
        embed.add_field(name="Hedef", value=target_name or "—", inline=True)
        embed.add_field(name="Uygulayan Yetkili", value=ctx.author.mention, inline=True)
        if reason:
            embed.add_field(name="Sebep", value=reason[:1024], inline=False)
        return await channel.send(embed=embed)

    async def _mod_log(self, ctx, action, target_id, target_name, reason=""):
        log_id = database.add_mod_log(
            ctx.guild.id, action, target_id, target_name,
            (ctx.author.id, ctx.author.name), reason,
        )
        message = await self._post_mod_embed(ctx, action, target_name, reason)
        if message is not None:
            database.update_mod_log_message(log_id, message.id)

    @commands.hybrid_command(name="help", aliases=["yardim"])
    async def help(self, ctx):
        prefix = database.get_prefix(ctx.guild.id)
        embed = discord.Embed(
            title="Bot Komutları",
            description=f"Prefix: **{prefix}**\nKomutlardan önce prefix kullan. Örn: `{prefix}temizle 10`\nÇoğu komut slash (`/`) ile de çalışır.",
            color=0x5865F2,
        )
        embed.add_field(
            name="Moderasyon",
            value=(
                f"`{prefix}sil <adet>` - Mesaj sil\n"
                f"`{prefix}kick <kullanıcı> [sebep]` - Kullanıcıyı at\n"
                f"`{prefix}ban <kullanıcı> [sebep]` - Kullanıcıyı yasakla\n"
                f"`{prefix}unban <id>` - Yasağı kaldır\n"
                f"`{prefix}uyar <kullanıcı> <sebep>` - Uyarı ver\n"
                f"`{prefix}uyarilar <kullanıcı>` - Uyarıları listele\n"
                f"`{prefix}uyari-sil <id>` - Uyarı sil\n"
                f"`{prefix}sustur <kullanıcı> <dk>` - Geçici susturma\n"
                f"`{prefix}unsustur <kullanıcı>` - Susturmayı kaldır\n"
                f"`{prefix}kilit` - Kanalı kilitler\n"
                f"`{prefix}unkilit` - Kanalı açar\n"
                f"`{prefix}rol <kullanıcı> <rol>` - Rol verir/kaldırır\n"
                f"`{prefix}prefix <yeni>` - Prefix değiştir"
            ),
            inline=False,
        )
        embed.add_field(
            name="Eğlence / Oyun",
            value=(
                f"`{prefix}zar` - Zar at\n"
                f"`{prefix}yazi-tura` - Yazı tura\n"
                f"`{prefix}8ball <soru>` - Sihirli 8 top\n"
                f"`{prefix}topluluk` - Sunucu bilgisi\n"
                f"`{prefix}bsahip` - Bot sahibi ve aktiflik"
            ),
            inline=False,
        )
        embed.add_field(
            name="Seviye",
            value=(
                f"`{prefix}seviye [kullanıcı]` - Seviyenizi gör\n"
                f"`{prefix}top` - Liderlik tablosu"
            ),
            inline=False,
        )
        embed.add_field(
            name="Ticket",
            value=f"`{prefix}ticket-kur` - Bilet paneli kur (butonla bilet)\n`{prefix}ticket` - Bilet açar",
            inline=False,
        )
        embed.add_field(
            name="Özel Komutlar",
            value=(
                "Dashboard üzerinden eklediğiniz komutlar otomatik çalışır.\n"
                "Örn: özel komut `selam` ise `{prefix}selam` veya `/selam` yazın."
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="sil", aliases=["temizle"])
    @mod_only()
    async def purge(self, ctx, amount: int = 10):
        amount = max(1, min(amount, 200))
        deleted = await ctx.channel.purge(limit=amount + 1)
        message_count = len(deleted) - 1
        await self._mod_log(
            ctx, "temizle", ctx.channel.id, f"#{ctx.channel.name}", f"{message_count} mesaj",
        )
        msg = await ctx.send(f"🗑️ **{message_count}** mesaj silindi.")
        await msg.delete(delay=3)

    @commands.hybrid_command(name="kick", aliases=["at"])
    @mod_only()
    async def kick(self, ctx, member: discord.Member, *, reason: str = "Sebep belirtilmedi"):
        if member == ctx.author:
            return await ctx.send("Kendini atamazsın!")
        await member.kick(reason=f"{ctx.author} -> {reason}")
        await self._mod_log(ctx, "kick", member.id, member.name, reason)
        await ctx.send(f"👢 {member.mention} sunucudan atıldı. (`{reason}`)")

    @commands.hybrid_command(name="ban")
    @mod_only()
    async def ban(self, ctx, member: discord.User, *, reason: str = "Sebep belirtilmedi"):
        await ctx.guild.ban(member, reason=f"{ctx.author} -> {reason}")
        await self._mod_log(ctx, "ban", member.id, member.name, reason)
        await ctx.send(f"🔨 {member.mention} yasaklandı. (`{reason}`)")

    @commands.hybrid_command(name="unban")
    @mod_only()
    async def unban(self, ctx, user_id: int):
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user)
            await self._mod_log(ctx, "unban", user.id, user.name, "")
            await ctx.send(f"✅ {user} yasağı kaldırıldı.")
        except discord.NotFound:
            await ctx.send("Yasaklı kullanıcı bulunamadı.")
        except Exception as e:
            await ctx.send(f"Hata oluştu: {e}")

    @commands.hybrid_command(name="uyar", aliases=["warn"])
    @mod_only()
    async def warn(self, ctx, member: discord.Member, *, reason: str):
        wid = database.add_warning(ctx.guild.id, member.id, ctx.author.id, reason)
        warns = database.get_warnings(ctx.guild.id, member.id)
        await self._mod_log(ctx, "uyar", member.id, member.name, reason)
        embed = discord.Embed(
            title="Uyarı verildi",
            description=f"**Kullanıcı:** {member.mention}\n**Sebep:** {reason}\n**Toplam uyarı:** {len(warns)}",
            color=0xFEE75C,
        )
        embed.set_footer(text=f"Uyarı ID: {wid}")
        await ctx.send(embed=embed)
        try:
            await member.send(f"⚠️ **{ctx.guild.name}** sunucusunda uyarı aldın: {reason}")
        except Exception:
            pass

    @commands.hybrid_command(name="uyarilar", aliases=["warnings"])
    async def warning_list(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        warns = database.get_warnings(ctx.guild.id, member.id)
        if not warns:
            return await ctx.send(f"{member.mention} için uyarı yok.")
        embed = discord.Embed(
            title=f"{member.display_name} - Uyarılar ({len(warns)})",
            color=0xFEE75C,
        )
        for w in warns[:10]:
            mod = self.bot.get_user(w["moderator_id"])
            embed.add_field(
                name=f"#{w['id']}",
                value=f"{w['reason']}\n✍️ {mod or 'Bilinmeyen'}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="uyari-sil", aliases=["delwarn"])
    @mod_only()
    async def del_warn(self, ctx, warning_id: int):
        if database.delete_warning(warning_id):
            await ctx.send(f"✅ #{warning_id} numaralı uyarı silindi.")
        else:
            await ctx.send("Uyarı bulunamadı.")

    @commands.hybrid_command(name="sustur", aliases=["mute"])
    @mod_only()
    async def mute(self, ctx, member: discord.Member, minutes: int = 10):
        if minutes <= 0:
            return await ctx.send("Dakika 0'dan büyük olmalı.")
        await self._mod_log(ctx, "sustur", member.id, member.name, f"{minutes} dakika")
        muted = discord.utils.get(ctx.guild.roles, name="Muted")
        if muted is None or muted.position >= ctx.guild.me.top_role.position:
            muted = await ctx.guild.create_role(name="Muted")
            for channel in ctx.guild.channels:
                try:
                    await channel.set_permissions(
                        muted, send_messages=False, speak=False, add_reactions=False
                    )
                except Exception:
                    pass
        await member.add_roles(muted, reason=f"Susturma: {ctx.author}")
        embed = discord.Embed(
            title="Susturuldu",
            description=f"{member.mention} **{minutes}** dakika susturuldu.",
            color=0xED4245,
        )
        await ctx.send(embed=embed)
        await asyncio.sleep(minutes * 60)
        if muted in member.roles:
            await member.remove_roles(muted)

    @commands.hybrid_command(name="unsustur", aliases=["unmute"])
    @mod_only()
    async def unmute(self, ctx, member: discord.Member):
        muted = discord.utils.get(ctx.guild.roles, name="Muted")
        if muted and muted in member.roles:
            await member.remove_roles(muted)
            await self._mod_log(ctx, "unsustur", member.id, member.name, "")
            await ctx.send(f"✅ {member.mention} susturması kaldırıldı.")
        else:
            await ctx.send("Bu kullanıcı susturulmuş görünmüyor.")

    @commands.hybrid_command(name="prefix")
    @mod_only()
    async def set_prefix(self, ctx, new_prefix: str):
        if len(new_prefix) > 5:
            return await ctx.send("Prefix en fazla 5 karakter olabilir.")
        database.set_prefix(ctx.guild.id, new_prefix)
        await ctx.send(f"✅ Prefix **{new_prefix}** olarak değiştirildi.")

    @commands.hybrid_command(name="kilit", description="Mevcut kanalı herkes için kitler")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await self._mod_log(ctx, "kilit", channel.id, f"#{channel.name}", "")
        embed = discord.Embed(
            title="🔒 Kanal kilitlendi",
            description=f"{channel.mention} kanalı kilitlendi.",
            color=0xFEE75C,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="unkilit", description="Kitli kanalı herkese açar")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, send_messages=None)
        await self._mod_log(ctx, "unkilit", channel.id, f"#{channel.name}", "")
        embed = discord.Embed(
            title="🔓 Kanal açıldı",
            description=f"{channel.mention} kanalı açıldı.",
            color=0x57F287,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rol", aliases=["role"], description="Belirtilen kullanıcıya rol verir veya kaldırır")
    @commands.has_permissions(manage_roles=True)
    async def role(self, ctx, member: discord.Member, role: discord.Role):
        if role >= ctx.guild.me.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("Bu rolü veremem (yetkim yetmiyor).")
        if role in member.roles:
            await member.remove_roles(role, reason=f"Rol kaldırıldı: {ctx.author}")
            action_desc = "kaldırıldı"
            await self._mod_log(ctx, "rol", member.id, f"{member.name} ({role.name} kaldırıldı)", "")
        else:
            await member.add_roles(role, reason=f"Rol verildi: {ctx.author}")
            action_desc = "verildi"
            await self._mod_log(ctx, "rol", member.id, f"{member.name} ({role.name} verildi)", "")
        await ctx.send(f"✅ {member.mention} adlı kullanıcıya **@{role.name}** rolü {action_desc}.")

    @commands.hybrid_command(name="otomatik-rol", aliases=["autorole"])
    @commands.has_permissions(administrator=True)
    async def auto_role(self, ctx, role: discord.Role):
        database.set_auto_role(ctx.guild.id, role.id)
        embed = discord.Embed(
            title="Otomatik rol ayarlandı",
            description=f"Sunucuya katılanlara **@{role.name}** rolü verilecek.",
            color=0x57F287,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="otomatik-rol-kapat", aliases=["autorole-kapat"])
    @commands.has_permissions(administrator=True)
    async def disable_auto_role(self, ctx):
        database.set_auto_role(ctx.guild.id, 0)
        await ctx.send("✅ Otomatik rol kapatıldı.")

    @commands.hybrid_command(name="karsilama", aliases=["welcome"])
    @commands.has_permissions(administrator=True)
    async def welcome(self, ctx, channel: discord.TextChannel = None, *, message: str = None):
        if channel is None:
            return await ctx.send("Kullanım: `!karsilama <#kanal> <mesaj>`\nMesajda `{mention}` ve `{user}` kullanabilirsin.")
        database.set_welcome(ctx.guild.id, channel.id, message or "")
        embed = discord.Embed(
            title="Karşılama mesajı ayarlandı",
            description=f"**Kanal:** {channel.mention}\n**Mesaj:** {message or 'Varsayılan mesaj kullanılacak'}",
            color=0x57F287,
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Moderation(bot))