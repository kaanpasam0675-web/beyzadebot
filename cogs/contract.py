import discord
from discord.ext import commands

import config


class Contract(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sozlesme")
    async def sozlesme_cmd(self, ctx):
        """Sahip: Botun bulunduğu TÜM sunuculara sözleşme gönderir."""
        if ctx.author.id != config.OWNER_DISCORD_ID:
            await ctx.send("❌ Bu komutu sadece bot sahibi kullanabilir.")
            return
        await ctx.send(f"📜 Sözleşme {len(self.bot.guilds)} sunucuya gönderiliyor...")
        lines = []
        for guild in self.bot.guilds:
            try:
                channel = await self.bot._find_contract_channel(guild)
                if channel is None:
                    lines.append(f"❌ {guild.name} — kanal yok")
                    continue
                await self.bot._send_contract(guild)
                lines.append(f"✅ {guild.name} — #{channel.name}")
            except Exception as e:
                lines.append(f"❌ {guild.name} — {type(e).__name__}: {e}")
        msg = "\n".join(lines) if lines else "Sunucu bulunamadı."
        await ctx.send(f"**Sonuç:**\n{msg}")

    @commands.hybrid_command(name="sozlesme-yenile")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def sozlesme_yenile_cmd(self, ctx):
        """Admin: Bu sunucuya sözleşme mesajını tekrar gönderir."""
        try:
            await self.bot._send_contract(ctx.guild)
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
        names = [c.name for c in self.bot.commands]
        await ctx.send(f"Kayıtlı komutlar ({len(names)}):\n{', '.join(sorted(names))}")


async def setup(bot):
    await bot.add_cog(Contract(bot))