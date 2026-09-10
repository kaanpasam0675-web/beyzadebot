import config
import discord
from discord.ext import commands

AI_MODEL = config.GEMINI_MODEL or "gemini-2.0-flash"


def _build_payload(prompt: str, system: str, history=None):
    contents = []
    if history:
        for role, text in history[-12:]:
            contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    return {
        "contents": contents,
        "systemInstruction": {
            "parts": [{"text": system}],
        },
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 700,
        },
    }


class AI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._session = None
        self._history = {}
        self._last_reply = {}

    async def _get_session(self):
        import aiohttp

        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        if message.channel.id != config.AUTO_CHAT_CHANNEL_ID:
            return
        if message.content.startswith(config.PREFIX) or message.content.startswith("/"):
            return
        if not message.content.strip():
            return
        import time

        key = f"{message.guild.id}:{message.channel.id}"
        now = time.time()
        if now - self._last_reply.get(key, 0) < 2.5:
            return
        self._last_reply[key] = now
        if not config.GEMINI_API_KEY:
            warning_key = f"{key}:nokey"
            if now - self._last_reply.get(warning_key, 0) > 60:
                self._last_reply[warning_key] = now
                await message.channel.send(
                    "⚠️ AI sohbet için **`GEMINI_API_KEY`** tanımlanmamış.\n"
                    "Railway → Variables'a ekleyip yeniden başlatın:\n"
                    "`https://aistudio.google.com` → Get API key"
                )
            return
        history = self._history.get(key, [])
        async with message.channel.typing():
            try:
                answer = await self._ask_gemini(
                    message.content.strip(),
                    system=(
                        "Sen 'Beyzade Bot'un AI'sisin ve bir Discord sohbet kanalındasın. "
                        "Doğal, samimi ve akıllı bir sohbet arkadaşı gibi davran. "
                        "Türkçe cevap ver. Kısa ve net ol ama konu derinleşirse detay verebilirsin. "
                        "Kullanıcının mesajına doğrudan ve ilgili cevap ver."
                    ),
                    history=history,
                )
            except Exception as e:
                error_key = f"{key}:hata"
                if now - self._last_reply.get(error_key, 0) > 60:
                    self._last_reply[error_key] = now
                    try:
                        await message.channel.send(f"⚠️ Gemini hatası: `{e}`")
                    except Exception:
                        pass
                return
        history.append(("user", message.content.strip()))
        history.append(("model", answer))
        self._history[key] = history[-12:]
        for chunk in self._split_send(answer):
            await message.channel.send(chunk)

    async def _ask_gemini(self, prompt: str, system: str = "", history=None):
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
            f"?key={config.GEMINI_API_KEY}"
        )
        session = await self._get_session()
        async with session.post(url, json=_build_payload(prompt, system, history)) as resp:
            data = await resp.json()
        if resp.status != 200:
            detail = data.get("error", {}).get("message", resp.status)
            raise RuntimeError(str(detail))
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("Gemini boş yanıt döndü.")
        if len(text) > 3800:
            text = text[:3800] + "…"
        return text

    def _split_send(self, text: str, n=2):
        """4000+ karakterli mesajları parçalar."""
        if len(text) <= 1700:
            return [text]
        chunks = []
        words = text.split()
        cur = ""
        for w in words:
            if len(cur) + len(w) + 1 <= 1700:
                cur += (w + " ") if cur else (w + " ")
            else:
                chunks.append(cur.strip())
                cur = w + " "
        if cur.strip():
            chunks.append(cur.strip())
        return chunks

    @commands.hybrid_command(name="ai", aliases=["gemini", "ask"])
    async def ai_cmd(self, ctx, *, prompt: str):
        """🤖 Gemini AI ile sohbet — soruna cevap verir."""
        if not config.GEMINI_API_KEY:
            await ctx.send("❌ `GEMINI_API_KEY` tanımlanmamış. `.env` dosyasına ekleyip botu yeniden başlatın.")
            return
        await ctx.defer()
        system = (
            "Sen 'Beyzade Bot' içindeki yardımsever bir yapay zeka asistanısın. "
            "Kısa, net ve Türkçe cevap ver. Kullanıcı Discord üzerinde konuşuyor; "
            "markdown kullanabilirsin ama çok uzun tutma."
        )
        try:
            answer = await self._ask_gemini(prompt, system)
        except Exception as e:
            await ctx.send(f"❌ Gemini hatası: `{e}`")
            return
        for chunk in self._split_send(answer):
            await ctx.send(chunk)

    @commands.hybrid_command(name="ai-sistem")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def ai_sistem(self, ctx, *, sistem: str):
        """Admin: AI asistanına özel sistem talimatını geçici olarak verir (sadece bu çağrı için)."""
        if not config.GEMINI_API_KEY:
            await ctx.send("❌ `GEMINI_API_KEY` tanımlanmamış.")
            return
        await ctx.defer()
        system = (
            "Sen bir Discord bot asistanısın. Şu özel talimatla davran:\n"
            f"{sistem}\n\nKısa ve Türkçe cevap ver."
        )
        try:
            answer = await self._ask_gemini(sistem, system)
        except Exception as e:
            await ctx.send(f"❌ Gemini hatası: `{e}`")
            return
        for chunk in self._split_send(answer):
            await ctx.send(chunk)

    def cog_unload(self):
        if self._session is not None:
            import asyncio

            asyncio.run_coroutine_threadsafe(self._session.close(), self.bot.loop)


async def setup(bot):
    await bot.add_cog(AI(bot))