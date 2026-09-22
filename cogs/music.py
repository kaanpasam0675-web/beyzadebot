import asyncio
import os

import discord
from discord.ext import commands
import yt_dlp

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None

FFMPEG_EXE = None
if imageio_ffmpeg is not None:
    try:
        FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        FFMPEG_EXE = os.getenv("FFMPEG_BINARY", "ffmpeg")


def _get_ffmpeg():
    return FFMPEG_EXE or "ffmpeg"


class MusicView(discord.ui.View):
    """Çalan müziği kontrol eden buton paneli."""

    def __init__(self, cog, channel):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel = channel
        self.add_item(CtrlButton("⏸ Duraklat", "pause", discord.ButtonStyle.primary))
        self.add_item(CtrlButton("⏭ Geç", "skip", discord.ButtonStyle.secondary))
        self.add_item(CtrlButton("⏹ Çık", "stop", discord.ButtonStyle.danger))


class CtrlButton(discord.ui.Button):
    def __init__(self, label, action, style=discord.ButtonStyle.secondary):
        super().__init__(label=label, style=style)
        self.action = action

    async def callback(self, interaction):
        view = self.view
        if view is None:
            return
        await view._handle(interaction, self.action)


class Music(commands.Cog):
    """🎵 Müzik sistemi: !çal <isim/link> • !çık • kuyruk ve kontrol paneli"""

    def __init__(self, bot):
        self.bot = bot
        self.players = {}  # guild_id -> {"vc", "queue", "now", "playing", "np_msg", "task", "volume"}

    # ---------- yardımcılar ----------

    def _player(self, guild_id):
        return self.players.setdefault(
            guild_id,
            {"vc": None, "queue": [], "now": None, "playing": False, "np_msg": None, "volume": 0.5},
        )

    async def _ensure_voice(self, ctx):
        if not ctx.author.voice:
            await ctx.send("❌ Önce bir ses kanalına katılmalısın.")
            return None, None
        ch = ctx.author.voice.channel
        vc = ctx.voice_client
        if vc is not None:
            if vc.channel.id != ch.id:
                await vc.move_to(ch)
        else:
            vc = await ch.connect()
        return vc, ch

    async def _search(self, query):
        """YouTube'da arar ve ilk sonucun ses linkini döndürür."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._extract_any(query),
        )

    def _extract_any(self, query):
        """Farklı YouTube istemcilerini sırayla dener (bot korumasına karşı)."""
        clients = ["android", "android_vr", "web"]
        last_err = None
        for client in clients:
            ydl_opts = {
                "format": "bestaudio/best",
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "extractor_args": {"youtube": [f"player_client={client}"]},
                "nocheckcertificate": True,
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(query, download=False)
                    if "entries" in info and info["entries"]:
                        info = info["entries"][0]
                    url = info.get("url") or info.get("webpage_url")
                    if not url:
                        raise RuntimeError("Ses bağlantısı bulunamadı")
                    return {
                        "title": info.get("title") or query,
                        "url": url,
                        "duration": info.get("duration") or 0,
                        "thumbnail": info.get("thumbnail"),
                        "channel": info.get("channel") or "",
                    }
            except Exception as e:
                last_err = e
                continue
        raise last_err or RuntimeError("Sonuç bulunamadı")

    # ---------- oynatıcı döngüsü ----------

    def _play_next(self, guild_id):
        player = self._player(guild_id)
        vc = player["vc"]
        if vc is None:
            return
        if player["queue"]:
            player["now"] = player["queue"].pop(0)
            track = player["now"]
            source = discord.FFmpegPCMAudio(
                track["url"],
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn",
                executable=_get_ffmpeg(),
            )
            vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(self._on_track_done(guild_id, e), self.bot.loop))
            player["playing"] = True
            asyncio.run_coroutine_threadsafe(self._update_panel(guild_id), self.bot.loop)
        else:
            player["now"] = None
            player["playing"] = False
            asyncio.run_coroutine_threadsafe(self._update_panel(guild_id), self.bot.loop)

    async def _on_track_done(self, guild_id, error):
        if error:
            print(f"[MÜZİK] Parça hatası: {error}")
        await asyncio.sleep(0.2)
        self._play_next(guild_id)

    async def _update_panel(self, guild_id):
        player = self._player(guild_id)
        vc = player["vc"]
        if vc is None or not vc.is_connected():
            return
        if player["now"] is None:
            if player["np_msg"] is not None:
                try:
                    await player["np_msg"].delete()
                except Exception:
                    pass
                player["np_msg"] = None
            return
        track = player["now"]
        embed = discord.Embed(
            title="🎵 Şimdi Çalıyor",
            description=f"**{track['title']}**\n{track['duration'] // 60}:{track['duration'] % 60:02d} dk · {track['channel']}",
            color=0x57F287,
        )
        if track.get("thumbnail"):
            embed.set_thumbnail(url=track["thumbnail"])
        if player["queue"]:
            q = "\n".join(
                f"{i + 1}. {t['title'][:45]}" for i, t in enumerate(player["queue"][:5])
            )
            embed.add_field(name=f"Sırada ({len(player['queue'])})", value=q[:1024], inline=False)
        view = MusicView(self, vc.channel)
        if player["np_msg"] is not None and player["np_msg"].guild is not None:
            try:
                await player["np_msg"].edit(embed=embed, view=view)
                return
            except Exception:
                pass
        player["np_msg"] = await vc.channel.send(embed=embed, view=view)

    async def _handle(self, interaction, action):
        guild_id = interaction.guild_id
        player = self._player(guild_id)
        vc = player["vc"]
        if vc is None or not vc.is_connected():
            await interaction.response.send_message("Ses kanalından ayrılmış durumdayım.", ephemeral=True)
            return
        if action == "pause":
            if vc.is_playing():
                vc.pause()
        elif action == "resume":
            if vc.is_paused():
                vc.resume()
        elif action == "skip":
            vc.stop()
        elif action == "clear":
            player["queue"] = []
            vc.stop()
        elif action == "stop":
            player["queue"] = []
            vc.stop()
            await self._leave(guild_id)
        try:
            await interaction.response.defer()
        except Exception:
            pass
        await self._update_panel(guild_id)

    async def _leave(self, guild_id):
        player = self.players.pop(guild_id, None)
        if player and player["vc"] is not None:
            try:
                await player["vc"].disconnect()
            except Exception:
                pass
            if player["np_msg"] is not None:
                try:
                    await player["np_msg"].delete()
                except Exception:
                    pass

    # ---------- komutlar ----------

    @commands.command(name="çal", aliases=["cal", "play", "oynat"])
    async def play(self, ctx, *, query: str):
        """🎵 Ses kanalına katılıp YouTube'da arar ve ilk sonucu çalar."""
        vc, ch = await self._ensure_voice(ctx)
        if vc is None:
            return
        player = self._player(ctx.guild.id)
        player["vc"] = vc

        async with ctx.typing():
            try:
                track = await self._search(query)
            except Exception as e:
                await ctx.send(f"❌ Müzik aranamadı: `{e}`")
                return
            if not track or not track.get("url"):
                await ctx.send("❌ Sonuç bulunamadı.")
                return

        player["queue"].append(track)
        if not player["playing"] and not vc.is_playing():
            self._play_next(ctx.guild.id)
            await ctx.send(f"🔍 Şarkı sıraya eklendi → **{track['title']}**")
        else:
            await ctx.send(f"➕ Sıraya eklendi: **{track['title']}**")

    @commands.command(name="sıra", aliases=["sira", "queue", "kuyruk"])
    async def queue_cmd(self, ctx):
        """📜 Sıradaki şarkıları listeler."""
        player = self._player(ctx.guild.id)
        if not player["queue"] and not player["now"]:
            await ctx.send("Sırada şarkı yok.")
            return
        lines = []
        if player["now"]:
            lines.append(f"▶ Şimdi: **{player['now']['title']}**")
        for i, t in enumerate(player["queue"], 1):
            lines.append(f"{i}. {t['title'][:60]}")
        await ctx.send("\n".join(lines[:15]))

    @commands.command(name="çık", aliases=["cik", "stop", "kapat"])
    async def leave(self, ctx):
        """⏹ Müziği durdurup ses kanalından çıkar."""
        player = self._player(ctx.guild.id)
        player["queue"] = []
        if player["vc"] is not None:
            player["vc"].stop()
        await self._leave(ctx.guild.id)
        await ctx.send("👋 Ses kanalından çıktım, müzik durdu.")

    @commands.command(name="ses", aliases=["sesayari", "volume"])
    async def volume(self, ctx, volume: int = None):
        """🔊 Ses seviyesi (0-100)."""
        player = self._player(ctx.guild.id)
        vc = player["vc"]
        if vc is None or not vc.is_connected():
            await ctx.send("Önce müzik çalmam gerekiyor.")
            return
        if volume is None:
            await ctx.send(f"Şu anki ses: **{int(player['volume'] * 100)}%**")
            return
        if not 0 <= volume <= 100:
            await ctx.send("Ses 0-100 arasında olmalı.")
            return
        player["volume"] = volume / 100
        await ctx.send(f"🔊 Ses seviyesi: **{volume}%**")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        vc_before = before.channel
        vc_after = after.channel
        if vc_before is None:
            return
        guild_id = member.guild.id
        player = self.players.get(guild_id)
        if player is None or player["vc"] is None:
            return
        my_vc = player["vc"]
        if vc_before.id == my_vc.channel.id and vc_after is None:
            channel = vc_before
            others = [m for m in channel.members if not m.bot]
            if not others:
                await asyncio.sleep(2)
                try:
                    current = self.players.get(guild_id)
                    if current and current["vc"] is not None and len([m for m in channel.members if not m.bot]) == 0:
                        player["queue"] = []
                        my_vc.stop()
                        await self._leave(guild_id)
                except Exception:
                    pass

    def cog_unload(self):
        for guild_id in list(self.players.keys()):
            asyncio.run_coroutine_threadsafe(self._leave(guild_id), self.bot.loop)


async def setup(bot):
    await bot.add_cog(Music(bot))