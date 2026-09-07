import discord
from discord.ext import commands

import database


class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="seviye", aliases=["level", "xp", "rank"])
    async def level(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        xp, level = database.get_level(ctx.guild.id, member.id)
        current_threshold = level * 100
        progress = min(xp / current_threshold, 1.0) if current_threshold else 0
        bar_length = 10
        filled = int(bar_length * progress)
        bar = "🟩" * filled + "⬛" * (bar_length - filled)

        embed = discord.Embed(
            title=f"{member.display_name} - Seviye",
            color=0x57F287,
        )
        embed.add_field(name="Seviye", value=f"**{level}**", inline=True)
        embed.add_field(name="XP", value=f"**{xp}/{current_threshold}**", inline=True)
        embed.add_field(name="İlerleme", value=bar, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="top", aliases=["liderlik", "siralama", "leaderboard"])
    async def leaderboard(self, ctx):
        rows = database.get_leaderboard(ctx.guild.id, 10)
        if not rows:
            return await ctx.send("Henüz sıralama yok. Mesaj yazınca XP kazanırsın!")
        embed = discord.Embed(
            title="🏆 Liderlik Tablosu",
            description="Seviye ve XP sıralaması",
            color=0xFEE75C,
        )
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, row in enumerate(rows, start=1):
            user = self.bot.get_user(row["user_id"]) or ctx.guild.get_member(row["user_id"])
            name = user.display_name if user else f"<@{row['user_id']}>"
            medal = medals[i - 1] if i <= 3 else f"**{i}.**"
            lines.append(f"{medal} {name} — Seviye **{row['level']}** ({row['xp']} XP)")
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Levels(bot))