import random

import discord
from discord.ext import commands


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.started_at = discord.utils.utcnow()

    @commands.hybrid_command(name="zar", aliases=["dice"])
    async def roll(self, ctx, sides: int = 6):
        if sides < 2 or sides > 10_000:
            return await ctx.send("Zar yüzeyi 2 ile 10000 arasında olmalı.")
        result = random.randint(1, sides)
        embed = discord.Embed(
            title="🎲 Zar atıldı!",
            description=f"**{ctx.author.mention}** → **{result}** (1-{sides})",
            color=0x57F287,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="yazi-tura", aliases=["coin", "yazitura"])
    async def coin(self, ctx):
        result = random.choice(["Yazı", "Tura"])
        embed = discord.Embed(
            title="🪙 Para atıldı!",
            description=f"**{ctx.author.mention}** → **{result}**",
            color=0xFEE75C,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="8ball", aliases=["sihirli-top"])
    async def eight_ball(self, ctx, *, question: str):
        answers = [
            "Kesinlikle evet!",
            "Görünüşe göre evet.",
            "Hmm, duruma bağlı.",
            "Şu an söyleyemem, tekrar dene.",
            "Cevap saklı, unut gitsin.",
            "Hayır, hiç sanmıyorum.",
            "Kesinlikle hayır!",
            "Belki... biraz daha düşün.",
            "Kaynaklarım hayır diyor.",
            "Evet, ama emin ol!",
        ]
        embed = discord.Embed(
            title="🎱 Sihirli 8 Top",
            color=0x5865F2,
        )
        embed.add_field(name="Soru", value=question, inline=False)
        embed.add_field(name="Cevap", value=random.choice(answers), inline=False)
        embed.set_footer(text=f"{ctx.author.name} için")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="embed", aliases=["mesaj-gonder", "duyuru"])
    @commands.has_permissions(manage_messages=True)
    async def embed_manual(self, ctx, title: str = None, *, content: str = None):
        if ctx.message.reference:
            ref = ctx.message.reference.resolved
            if ref:
                content = ref.content or content
                title = title or "Gönderilen Mesaj"
        if not content:
            return await ctx.send("Kullanım: `!embed <başlık> <içerik>`")
        embed = discord.Embed(
            title=title or "Mesaj",
            description=content,
            color=0x5865F2,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="topluluk", aliases=["sunucu-bilgi"])
    async def server_info(self, ctx):
        guild = ctx.guild
        embed = discord.Embed(
            title=f"{guild.name} bilgi",
            color=0x5865F2,
        )
        embed.add_field(name="👤 Üye sayısı", value=guild.member_count, inline=True)
        embed.add_field(name="📜 Kanal sayısı", value=len(guild.channels), inline=True)
        embed.add_field(name="🤖 Rol sayısı", value=len(guild.roles), inline=True)
        embed.add_field(name="👑 Kurucu", value=guild.owner.mention if guild.owner else "?", inline=True)
        embed.add_field(name="🌐 Bölge", value="Türkiye 🇹🇷", inline=True)
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="bsahip", aliases=["bot-sahibi"])
    async def sahip(self, ctx):
        try:
            app = await self.bot.application_info()
            owner = app.owner
            embed = discord.Embed(
                title=f"🤖 {self.bot.user.name} hakkında",
                color=0x5865F2,
            )
            embed.add_field(name="👑 Sahip", value=owner.mention if owner else "?", inline=True)
            embed.add_field(name="📅 Oluşturulma", value=self.bot.user.created_at.strftime("%d.%m.%Y") if self.bot.user else "?", inline=True)
            uptime = discord.utils.utcnow() - self.started_at
            days, rem = divmod(int(uptime.total_seconds()), 86400)
            hours, rem = divmod(rem, 3600)
            minutes, secs = divmod(rem, 60)
            embed.add_field(
                name="⏱️ Aktiflik süresi",
                value=f"{days} gün {hours} saat {minutes} dk {secs} sn",
                inline=True,
            )
            await ctx.send(embed=embed)
        except Exception as e:
            try:
                await ctx.send(f"⚠️ Hata oluştu: `{type(e).__name__}: {e}`")
            except Exception:
                pass


async def setup(bot):
    await bot.add_cog(Fun(bot))