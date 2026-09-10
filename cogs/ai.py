import config
import discord
from discord.ext import commands

AI_MODEL = config.GEMINI_MODEL or "gemini-2.0-flash"


def _build_payload(prompt: str, system: str):
    return {
        "contents": [
            {
                "parts": [{"text": prompt}],
            }
        ],
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

    async def _get_session(self):
        import aiohttp

        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _ask_gemini(self, prompt: str, system: str = ""):
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
            f"?key={config.GEMINI_API_KEY}"
        )
        session = await self._get_session()
        async with session.post(url, json=_build_payload(prompt, system)) as resp:
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