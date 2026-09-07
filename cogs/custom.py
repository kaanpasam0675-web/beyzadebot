import asyncio

import discord
from discord import app_commands
from discord.ext import commands

import database


class Custom(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------- Slash komut eşitleme ----------

    async def sync_all(self, bot):
        """DB'deki tüm özel komutları belirtilen sunuculara slash komut olarak kaydeder."""
        for guild_id in database.get_command_guild_ids():
            try:
                guild = discord.Object(id=guild_id)
                for cmd in database.get_all_custom_commands(guild_id):
                    if cmd["enabled"]:
                        self._register_slash(bot, guild, cmd["name"])
                await bot.tree.sync(guild=guild)
                print(f"[OK] Slash komutlar eşitlendi: guild={guild_id}")
            except discord.HTTPException as e:
                print(f"[UYARI] Slash eşitleme başarısız guild={guild_id}: {e}")
            except Exception as e:
                print(f"[UYARI] Slash eşitleme hatası guild={guild_id}: {e}")

    async def sync_guild(self, bot, guild_id: int):
        guild = discord.Object(id=guild_id)
        try:
            for cmd in database.get_all_custom_commands(guild_id):
                if cmd["enabled"]:
                    self._register_slash(bot, guild, cmd["name"])
            await bot.tree.sync(guild=guild)
            return True
        except Exception as e:
            print(f"[HATA] sync_guild {guild_id}: {e}")
            return False

    def _register_slash(self, bot, guild, name: str):
        if bot.tree.get_command(name, guild=guild) is not None:
            return
        cog = self

        async def handler(interaction):
            cmd_data = database.get_custom_command(interaction.guild_id, name)
            if not cmd_data:
                return await interaction.response.send_message("Bu komut artık bulunmuyor.", ephemeral=True)
            await interaction.response.defer()
            await cog._execute(
                author=interaction.user,
                channel=interaction.channel,
                cmd=cmd_data,
                args_text="",
            )
            await interaction.followup.send("✅", ephemeral=True)

        handler.__name__ = "custom_" + name
        cmd_obj = app_commands.Command(
            name=name,
            description=f"Özel komut: {name}",
            callback=handler,
        )
        bot.tree.add_command(cmd_obj, guild=guild)

    async def unregister_slash(self, bot, guild_id: int, name: str):
        guild = discord.Object(id=guild_id)
        if bot.tree.get_command(name, guild=guild) is not None:
            bot.tree.remove_command(name, guild=guild)
            try:
                await bot.tree.sync(guild=guild)
            except Exception as e:
                print(f"[UYARI] slash kaldırma/hata {guild_id}: {e}")

    # ---------- Prefix & slash ortak çalışma ----------

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        prefix = database.get_prefix(message.guild.id)
        content = message.content.strip()
        if not content.startswith(prefix):
            return
        body = content[len(prefix):].strip()
        if not body:
            return
        name = body.split()[0].lower()
        args_text = body[len(name):].strip()
        cmd = database.get_custom_command(message.guild.id, name)
        if not cmd or not cmd["enabled"]:
            return
        try:
            await self._execute(
                author=message.author,
                channel=message.channel,
                cmd=cmd,
                args_text=args_text,
            )
        except Exception as e:
            try:
                await message.channel.send(f"⚠️ Özel komut hatası: `{e}`")
            except Exception:
                pass

    def _fmt(self, text, author, args_text="", guild=None):
        replacements = {
            "{user}": author.name,
            "{mention}": author.mention,
            "{id}": str(author.id),
            "{args}": args_text,
            "{server}": guild.name if guild else "",
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        return text

    @staticmethod
    def _resolve_member(guild, ref):
        if ref is None:
            return None
        if str(ref).isdigit():
            return guild.get_member(int(ref))
        cleaned = str(ref).strip("<@!&>")
        if cleaned.isdigit():
            return guild.get_member(int(cleaned))
        return discord.utils.get(guild.members, name=ref) or discord.utils.find(
            lambda m: ref.lower() in m.name.lower(), guild.members
        )

    @staticmethod
    def _resolve_role(guild, ref):
        if ref is None:
            return None
        if str(ref).isdigit():
            return guild.get_role(int(ref))
        return discord.utils.get(guild.roles, name=ref) or discord.utils.find(
            lambda r: ref.lower() in r.name.lower(), guild.roles
        )

    async def _execute(self, author, channel, cmd, args_text=""):
        guild = channel.guild

        # 1) Düz metin yanıtı
        if cmd.get("response_text"):
            await channel.send(self._fmt(cmd["response_text"], author, args_text, guild))

        # 2) Embed yanıtı
        title = cmd.get("embed_title") or ""
        description = cmd.get("embed_description") or ""
        if title or description:
            color = (cmd.get("embed_color") or "#5865F2").lstrip("#")
            try:
                color_int = int(color, 16)
            except Exception:
                color_int = 0x5865F2
            embed = discord.Embed(
                title=self._fmt(title, author, args_text, guild) if title else None,
                description=self._fmt(description, author, args_text, guild) if description else None,
                color=color_int,
            )
            await channel.send(embed=embed)

        # 3) Aksiyon
        action_type = cmd.get("action_type") or "reply"
        if action_type == "reply":
            return

        target = self._resolve_member(guild, cmd.get("target_value"))
        value = cmd.get("action_value") or ""

        if not target:
            return await channel.send(f"⚠️ Aksiyon hedefi bulunamadı: `{cmd.get('target_value') or '-'}`")

        if action_type == "rol-ver":
            role = self._resolve_role(guild, value)
            if role is None:
                return await channel.send(f"⚠️ Rol bulunamadı: `{value}`")
            if role not in target.roles:
                await target.add_roles(role, reason="Özel komut ile rol verildi")
                await channel.send(f"✅ {target.mention} ile **@{role.name}** rolü verildi.")
            else:
                await channel.send(f"ℹ️ {target.mention} zaten bu role sahip.")
        elif action_type == "rol-al":
            role = self._resolve_role(guild, value)
            if role is None:
                return await channel.send(f"⚠️ Rol bulunamadı: `{value}`")
            if role in target.roles:
                await target.remove_roles(role, reason="Özel komut ile rol alındı")
                await channel.send(f"✅ {target.mention} ile **@{role.name}** rolü alındı.")
            else:
                await channel.send(f"ℹ️ {target.mention} bu role sahip değil.")
        elif action_type == "sustur":
            minutes = 10
            try:
                minutes = int(value) if value.isdigit() else 10
            except Exception:
                minutes = 10
            muted = discord.utils.get(guild.roles, name="Muted")
            if muted is None:
                muted = await guild.create_role(name="Muted")
                for ch in guild.channels:
                    try:
                        await ch.set_permissions(muted, send_messages=False, speak=False)
                    except Exception:
                        pass
            await target.add_roles(muted, reason="Özel komut ile susturma")
            await channel.send(f"🔇 {target.mention} **{minutes}** dakika susturuldu.")
            await asyncio.sleep(minutes * 60)
            if muted in target.roles:
                await target.remove_roles(muted)
        elif action_type == "ban":
            if not guild.me.guild_permissions.ban_members:
                return await channel.send("⚠️ Bu aksiyon için botun `Ban Member` yetkisi yok.")
            await target.ban(reason="Özel komut ile banlandı")
            await channel.send(f"🔨 {target.mention} yasaklandı.")
        elif action_type == "kick":
            if not guild.me.guild_permissions.kick_members:
                return await channel.send("⚠️ Bu aksiyon için botun `Kick Member` yetkisi yok.")
            await target.kick(reason="Özel komut ile atıldı")
            await channel.send(f"👢 {target.mention} sunucudan atıldı.")
        elif action_type == "mesaj-gonder":
            text = self._fmt(value, author, args_text, guild)
            if text:
                await channel.send(text)
        elif action_type == "tepki":
            if value:
                try:
                    await channel.send(f"{author.mention}", delete_after=0.1)
                except Exception:
                    pass
                await channel.send(f"Tepki: {value}")


async def setup(bot):
    cog = Custom(bot)
    await bot.add_cog(cog)