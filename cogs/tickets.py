import asyncio

import discord
from discord import app_commands
from discord.ext import commands

import database

TICKET_CATEGORY_ID = 1537215404928147587
REVIEW_CHANNEL_ID = 1546409474267418705
SUPPORT_ROLE_HINT = "ticket"

OPEN_BUTTON_ID = "ticket_open"
CLOSE_BUTTON_ID = "ticket_close"
CLAIM_BUTTON_ID = "ticket_claim"


def is_support(member: discord.Member) -> bool:
    return member.guild_permissions.manage_channels


def can_claim(member: discord.Member, ticket) -> bool:
    # Ticket sahibi veya yetkili claim edebilir
    if member.id == ticket["author_id"]:
        return True
    return member.guild_permissions.manage_channels


async def open_ticket(guild, user, konu: str):
    existing = database.get_open_ticket(guild.id, user.id)
    if existing:
        channel = guild.get_channel(existing["channel_id"])
        if channel:
            return channel

    category = guild.get_channel(TICKET_CATEGORY_ID)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    suffix = (user.discriminator and user.discriminator != "0") and user.discriminator or str(user.id % 10000)
    name = f"ticket-{user.name[:20]}-{suffix}"
    if category:
        ticket_chan = await guild.create_text_channel(
            name=name, topic=f"Bilet sahibi: {user}", category=category,
            overwrites=overwrites, reason=f"Ticket açıldı: {user}",
        )
    else:
        ticket_chan = await guild.create_text_channel(
            name=name, topic=f"Bilet sahibi: {user}",
            overwrites=overwrites, reason=f"Ticket açıldı: {user}",
        )
    ticket_id = database.create_ticket(guild.id, ticket_chan.id, user.id)

    embed = discord.Embed(
        title="🎫 Destek bileti",
        description="Bir destek ekibi üyesi en kısa sürede sana yardımcı olacak.",
        color=0x5865F2,
    )
    embed.add_field(name="Konu", value=konu, inline=False)
    embed.add_field(name="Sahip", value=user.mention, inline=True)
    embed.add_field(name="Bilet No", value=f"#{ticket_id}", inline=True)
    await ticket_chan.send(embed=embed, view=CloseTicketView())
    return ticket_chan


class TicketModal(discord.ui.Modal):
    konu = discord.ui.TextInput(
        label="Konu",
        placeholder="Sorunuzu veya talebinizi yazın...",
        max_length=200,
        style=discord.TextStyle.short,
    )

    def __init__(self):
        super().__init__(title="🎫 Yeni Destek Bileti")

    async def on_submit(self, interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            channel = await open_ticket(interaction.guild, interaction.user, self.konu.value)
            await interaction.followup.send(f"✅ Biletiniz açıldı: {channel.mention}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ Bilet açılırken hata: `{e}`", ephemeral=True)


class OpenTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # Bunu open_ticket baslangic mesajinda kullanmiyoruz; panel gonderiminde TicketPanelView kullanilir.
    @discord.ui.button(label="🎫 Bilet Aç", style=discord.ButtonStyle.primary, custom_id=OPEN_BUTTON_ID)
    async def open_button(self, interaction, button):
        await interaction.response.send_modal(TicketModal())


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # Discord view button persistence: custom_id ile geri yüklenen buton için
    @discord.ui.button(label="🎫 Bilet Aç", style=discord.ButtonStyle.primary, custom_id=OPEN_BUTTON_ID)
    async def open_button(self, interaction, button):
        await interaction.response.send_modal(TicketModal())


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ClaimButton())
        self.add_item(CloseButton())


class ClaimButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🤝 Talebi Üstlen (Claim)", style=discord.ButtonStyle.success, custom_id=CLAIM_BUTTON_ID)

    async def callback(self, interaction):
        await claim_flow(interaction)


class CloseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🔒 Bileti Kapat", style=discord.ButtonStyle.danger, custom_id=CLOSE_BUTTON_ID)

    async def callback(self, interaction):
        await close_ticket_flow(interaction)


async def claim_flow(interaction):
    ticket = database.get_ticket(interaction.channel.id)
    if not ticket or ticket["status"] == "closed":
        return await interaction.response.send_message("Bu bir açık bilet kanalı değil.", ephemeral=True)
    if not can_claim(interaction.user, ticket):
        return await interaction.response.send_message("Bu bileti üstlenmek için yetkin yok.", ephemeral=True)
    if ticket["claimer_id"] and ticket["claimer_id"] != interaction.user.id:
        return await interaction.response.send_message(
            "Bu bilet başka biri tarafından üstlenildi.", ephemeral=True
        )
    database.claim_ticket(interaction.channel.id, interaction.user.id)

    embed = discord.Embed(
        title="Destek Claimlendi!",
        description=(
            "Merhaba destek ekibiyle iletişime geçtiğiniz için teşekkürler. "
            f"{interaction.user.mention} adlı personel sizinle ilgilenecektir.\n\n"
            "Lütfen probleminizi açık ve anlatıcı şekilde söyleyiniz."
        ),
        color=0x57F287,
    )

    # Butonu karart ve "(Claimlendi) {isim}" yap
    claim_btn = ClaimButton()
    claim_btn.disabled = True
    claim_btn.label = f"(Claimlendi) {interaction.user.display_name}"
    close_btn = CloseButton()
    view = discord.ui.View(timeout=None)
    view.add_item(claim_btn)
    view.add_item(close_btn)

    await interaction.response.edit_message(embed=embed, view=view)

    try:
        author = interaction.guild.get_member(ticket["author_id"])
        if author and author.id != interaction.user.id:
            await author.send(f"🎫 Biletiniz **{interaction.user.display_name}** tarafından üstlenildi.")
    except Exception:
        pass


async def close_ticket_flow(interaction):
    ticket = database.get_ticket(interaction.channel.id)
    if not ticket or ticket["status"] == "closed":
        return await interaction.response.send_message("Bu bir açık bilet kanalı değil.", ephemeral=True)
    if (
        interaction.user.id != ticket["author_id"]
        and not interaction.user.guild_permissions.manage_channels
    ):
        return await interaction.response.send_message("Bu bileti kapatma yetkin yok.", ephemeral=True)
    await interaction.response.defer()
    database.close_ticket(interaction.channel.id)

    author = interaction.guild.get_member(ticket["author_id"])
    if author:
        # Değerlendirme anketi
        try:
            dm = await author.create_dm()
            await dm.send(embed=discord.Embed(
                title="🎫 Biletin kapatıldı",
                description="Destek hizmetini değerlendirmek için aşağıdan yıldız seç.",
                color=0x5865F2,
            ), view=ReviewView(ticket))
        except Exception:
            pass

    close_embed = discord.Embed(
        title="🎫 Bilet kapatıldı",
        description="Bilet kapatıldı. Kanal 15 saniye içinde silinecek.",
        color=0xED4245,
    )
    await interaction.channel.send(embed=close_embed)
    await asyncio.sleep(15)
    await interaction.channel.delete()


class ReviewView(discord.ui.View):
    def __init__(self, ticket):
        super().__init__(timeout=None)
        self.ticket = ticket
        for star in range(1, 6):
            btn = discord.ui.Button(label="⭐" * star, style=discord.ButtonStyle.secondary, custom_id=f"review_{star}")
            btn.callback = self.make_callback(star)
            self.add_item(btn)

    def make_callback(self, stars):
        async def cb(interaction):
            await review_flow(interaction, self.ticket, stars)
        return cb


async def review_flow(interaction, ticket, stars):
    if interaction.user.id != ticket["author_id"]:
        return await interaction.response.send_message("Yalnızca bilet sahibi değerlendirme yapabilir.", ephemeral=True)
    if database.has_reviewed(ticket["id"], interaction.user.id):
        return await interaction.response.send_message("Bu bileti zaten değerlendirdin.", ephemeral=True)
    comment = None
    if stars >= 4:
        # yüksek yıldızlarda opsiyonel yorum modalı
        pass
    # Yorum modalı
    modal = ReviewCommentModal(ticket, stars)
    await interaction.response.send_modal(modal)


class ReviewCommentModal(discord.ui.Modal):
    yorum = discord.ui.TextInput(
        label="Yorum (opsiyonel)",
        placeholder="Geri bildiriminizi yazın...",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=500,
    )

    def __init__(self, ticket, stars):
        super().__init__(title=f"Değerlendirme: {'⭐' * stars}")
        self.ticket = ticket
        self.stars = stars

    async def on_submit(self, interaction):
        database.add_review(
            self.ticket["guild_id"], self.ticket["id"], interaction.user.id,
            self.stars, self.yorum.value or "",
        )
        await interaction.response.send_message("✅ Değerlendirmeniz kaydedildi.", ephemeral=True)
        await post_review(interaction.client, self.ticket, interaction.user, self.stars, self.yorum.value or "")


async def post_review(bot, ticket, reviewer, stars, comment):
    guild = bot.get_guild(ticket["guild_id"])
    if guild is None:
        return
    channel = guild.get_channel(REVIEW_CHANNEL_ID)
    if channel is None:
        return
    claimer = guild.get_member(ticket["claimer_id"]) if ticket["claimer_id"] else None
    embed = discord.Embed(
        title="⭐ Bilet Değerlendirmesi",
        color=0xFEE75C,
    )
    embed.add_field(name="Bilet No", value=f"#{ticket['id']}", inline=True)
    embed.add_field(name="Puan", value="⭐" * stars, inline=True)
    embed.add_field(name="Kullanıcı", value=reviewer.mention, inline=True)
    embed.add_field(name="Görevli", value=claimer.mention if claimer else "Yok", inline=True)
    if comment:
        embed.add_field(name="Yorum", value=comment[:500], inline=False)
    await channel.send(embed=embed)


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="ticket-kur", aliases=["ticket-paneli"], description="Bilet paneli kurar")
    @commands.has_permissions(manage_channels=True)
    async def setup_panel(self, ctx):
        embed = discord.Embed(
            title="🎫 Destek Bileti",
            description="Aşağıdaki butona tıklayarak destek bileti açabilirsin.",
            color=0x5865F2,
        )
        await ctx.send(embed=embed, view=TicketPanelView())
        await ctx.send("✅ Panel kuruldu.", delete_after=5)
        database.add_mod_log(
            ctx.guild.id, "ticket-panel", ctx.channel.id, f"#{ctx.channel.name}",
            (ctx.author.id, ctx.author.name), "Panel kuruldu",
        )

    @commands.hybrid_command(name="ticket", description="Destek bileti açar")
    async def ticket(self, ctx, *, konu: app_commands.Range[str, 1, 200] = "Destek talebi"):
        channel = await open_ticket(ctx.guild, ctx.author, konu)
        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(f"✅ Biletiniz açıldı: {channel.mention}", ephemeral=True)
        else:
            await ctx.send(f"✅ Biletiniz açıldı: {channel.mention}")


async def setup(bot):
    await bot.add_cog(Tickets(bot))
    bot.add_view(TicketPanelView())
    bot.add_view(CloseTicketView())