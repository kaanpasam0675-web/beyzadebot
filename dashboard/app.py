import functools
import os
import sys
import asyncio

import discord
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import database
from bot import Bot, get_bot, start_bot_thread

app = Flask(__name__)
app.secret_key = "discord-bot-dashboard-secret"

BOT_THREAD = None


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def current_guild_id():
    return int(session.get("guild_id", 0))


def _post_deleted_embed(guild_id, log_id, message_id=0):
    """Dashboard'dan moderasyon kaydı silinince, eski işlem mesajını silip yerine bildirim embed'i atar."""
    bot = get_bot()
    if bot is None or not bot.is_ready():
        return
    channel = bot.get_channel(config.MOD_LOG_CHANNEL_ID)
    if channel is None:
        return
    import asyncio

    async def _do():
        if message_id:
            try:
                old = await channel.fetch_message(message_id)
                await old.delete()
            except Exception:
                pass
        embed = discord.Embed(
            title="Moderasyon kaydı silindi",
            description=f"Bu moderasyon kaydı **Dashboard Yöneticisi** tarafından silindi.",
            color=0xFEE75C,
        )
        embed.add_field(name="Kayıt No", value=f"#{log_id}", inline=True)
        await channel.send(embed=embed)

    asyncio.run_coroutine_threadsafe(_do(), bot.loop)


def _slash_refresh(guild_id=None):
    """Özel komutları bot üzerinden slash komut olarak eşitler (arka planda)."""
    bot = get_bot()
    if bot is None:
        return
    import asyncio

    async def _do():
        cog = bot.get_cog("Custom")
        if cog is None:
            return
        if guild_id:
            await cog.sync_guild(bot, guild_id)
        else:
            await cog.sync_all(bot)

    asyncio.run_coroutine_threadsafe(_do(), bot.loop)


@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("home"))
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == config.DASHBOARD_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("home"))
        error = "Yanlış şifre."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/home")
@login_required
def home():
    guilds = available_guilds()
    selected_guild = None
    if guilds:
        selected_id = session.get("guild_id") or guilds[0]["id"]
        session["guild_id"] = selected_id
        selected_guild = next((g for g in guilds if g["id"] == selected_id), guilds[0])
    commands = []
    settings = {}
    tickets = []
    mod_logs = []
    warnings = []
    bot_status = {}
    channels = []
    if selected_guild:
        gid = selected_guild["id"]
        commands = database.get_all_custom_commands(gid)
        settings = database.get_guild_settings(gid)
        tickets = enrich_tickets(database.get_tickets(gid))
        mod_logs = database.get_mod_logs(gid)
        warnings = database.get_all_warnings(gid)
        bot = get_bot()
        if bot is not None:
            guild = bot.get_guild(gid)
            if guild is not None:
                channels = [
                    {"id": ch.id, "name": ch.name}
                    for ch in guild.text_channels
                ][:25]
                emojis = [
                    {
                        "name": e.name,
                        "id": e.id,
                        "animated": e.animated,
                        "mention": f"<a:{e.name}:{e.id}>" if e.animated else f"<:{e.name}:{e.id}>",
                        "preview": e.url,
                    }
                    for e in guild.emojis
                ]
                bot_status = {
                    "ready": bot.is_ready(),
                    "name": bot.user.name if bot.user else "?",
                    "avatar": bot.user.display_avatar.url if bot.user else None,
                    "ping": round(bot.latency * 1000) if bot.latency else 0,
                    "guild_count": len(bot.guilds),
                    "guild_name": guild.name,
                    "guild_members": guild.member_count,
                    "guild_id": guild.id,
                    "status": str(bot.status) if bot.status else "online",
                    "activity_name": bot.activity.name if bot.activity else None,
                    "activity_type": str(bot.activity.type) if bot.activity else None,
                }
    return render_template(
        "home.html",
        guilds=guilds,
        selected_guild=selected_guild,
        commands=[dict(c) for c in commands],
        settings=settings,
        tickets=tickets,
        mod_logs=mod_logs,
        warnings=warnings,
        bot_status=bot_status,
        channels=channels,
        emojis=emojis if guild is not None else [],
    )


@app.route("/edit-profile", methods=["POST"])
@login_required
def edit_profile():
    bot = get_bot()
    if bot is None or not bot.is_ready():
        return "Bot çevrimiçi değil.", 400
    username = request.form.get("username", "").strip() or None
    bio = None
    if "bio" in request.form:
        bio = request.form.get("bio", "") or None
    avatar_bytes = None
    banner_bytes = None
    av_file = request.files.get("avatar")
    bn_file = request.files.get("banner")
    if av_file and av_file.filename:
        avatar_bytes = av_file.read()
    if bn_file and bn_file.filename:
        banner_bytes = bn_file.read()

    import asyncio

    future = {}

    async def _edit():
        try:
            kwargs = {}
            if username:
                kwargs["username"] = username
            if bio is not None:
                kwargs["bio"] = bio
            if avatar_bytes:
                kwargs["avatar"] = avatar_bytes
            if banner_bytes:
                kwargs["banner"] = banner_bytes
            if not kwargs:
                return
            await bot.user.edit(**kwargs)
            future["ok"] = True
        except Exception as e:
            future["ok"] = False
            future["error"] = repr(e)

    fut = asyncio.run_coroutine_threadsafe(_edit(), bot.loop)
    fut.result(timeout=30)
    if not future.get("ok"):
        return f"Hata: {future.get('error')}", 400
    return redirect(url_for("home"))


@app.route("/set-status", methods=["POST"])
@login_required
def set_status():
    text = request.form.get("status_text", "").strip()
    act_type = request.form.get("activity_type", "playing")
    presence = request.form.get("presence_status", "online")
    bot = get_bot()
    if bot is None or not bot.is_ready():
        return "Bot çevrimiçi değil.", 400

    def _build():
        import discord as d2
        act = None
        if text:
            if act_type == "custom":
                act = d2.CustomActivity(name=text)
            else:
                types = {
                    "playing": d2.ActivityType.playing,
                    "listening": d2.ActivityType.listening,
                    "watching": d2.ActivityType.watching,
                    "streaming": d2.ActivityType.streaming,
                    "competing": d2.ActivityType.competing,
                }
                act = d2.Activity(type=types.get(act_type, d2.ActivityType.playing), name=text)
        stat = {
            "online": d2.Status.online,
            "idle": d2.Status.idle,
            "dnd": d2.Status.dnd,
            "invisible": d2.Status.invisible,
        }.get(presence, d2.Status.online)
        return act, stat

    act, stat = _build()
    import asyncio

    async def _do():
        await bot.change_presence(activity=act, status=stat)

    asyncio.run_coroutine_threadsafe(_do(), bot.loop)
    return redirect(url_for("home"))


@app.route("/send-message", methods=["POST"])
@login_required
def send_message():
    gid = current_guild_id()
    channel_id = int(request.form.get("channel_id", 0))
    content = request.form.get("message", "").strip()
    msg_type = request.form.get("msg_type", "plain")
    if msg_type == "embed":
        if not request.form.get("embed_description", "").strip():
            return "Embed açıklaması boş olamaz.", 400
    elif not content:
        return "Mesaj boş.", 400
    bot = get_bot()
    if bot is None or not bot.is_ready():
        return "Bot çevrimiçi değil.", 400
    channel = bot.get_channel(channel_id)
    if channel is None or getattr(channel, "guild", None) is None or channel.guild.id != gid:
        return "Kanal bulunamadı veya bu sunucuya ait değil.", 400

    import asyncio

    result = {}

    async def _send():
        try:
            if msg_type == "embed":
                try:
                    color = int(request.form.get("embed_color", "5865F2").lstrip("#"), 16)
                except Exception:
                    color = 0x5865F2
                embed = discord.Embed(
                    title=request.form.get("embed_title", "") or None,
                    description=request.form.get("embed_description", ""),
                    color=color,
                )
                embed.set_footer(
                    text=f"Dashboard'dan • {bot.user.name if bot.user else 'Bot'}",
                    icon_url=bot.user.display_avatar.url if bot.user else None,
                )
                await channel.send(content=content or None, embed=embed)
            else:
                await channel.send(content)
            result["ok"] = True
        except Exception as e:
            result["ok"] = False
            result["error"] = repr(e)

    fut = asyncio.run_coroutine_threadsafe(_send(), bot.loop)
    fut.result(timeout=20)
    if not result.get("ok"):
        return f"Hata: {result.get('error')}", 400
    return redirect(url_for("home"))


def enrich_tickets(tickets):
    bot = get_bot()
    out = []
    for t in tickets:
        t = dict(t)
        user = bot.get_user(t["author_id"]) if bot is not None else None
        t["author_name"] = user.name if user else f"<@{t['author_id']}>"
        if t.get("claimer_id"):
            claimer = bot.get_user(t["claimer_id"]) if bot is not None else None
            t["claimer_name"] = claimer.name if claimer else f"<@{t['claimer_id']}>"
        else:
            t["claimer_name"] = "-"
        out.append(t)
    return out


@app.route("/tickets/<int:ticket_id>")
@login_required
def ticket_detail(ticket_id):
    gid = current_guild_id()
    ticket = database.get_ticket_by_id(gid, ticket_id)
    if not ticket:
        return "Ticket bulunamadı.", 404
    reviews = database.get_reviews_for_ticket(gid, ticket_id)
    bot = get_bot()
    reviewer_names = {}
    if bot is not None:
        for r in reviews:
            u = bot.get_user(r["reviewer_id"])
            reviewer_names[r["reviewer_id"]] = u.name if u else f"<@{r['reviewer_id']}>"
    messages = []
    if bot is not None and bot.is_ready():
        for g in bot.guilds:
            ch = g.get_channel(ticket["channel_id"])
            if ch:
                try:
                    fut = asyncio.run_coroutine_threadsafe(
                        ch.history(limit=100).flatten(), bot.loop
                    )
                    for m in fut.result(timeout=10):
                        messages.append({
                            "author": m.author.display_name if not m.author.bot else f"{m.author.name} (bot)",
                            "is_bot": m.author.bot,
                            "content": m.clean_content[:2000],
                            "time": m.created_at.strftime("%d.%m.%Y %H:%M"),
                        })
                except Exception:
                    pass
                break
    return render_template(
        "ticket_detail.html",
        ticket=ticket,
        reviews=reviews,
        reviewer_names=reviewer_names,
        messages=list(reversed(messages)),
    )


@app.route("/tickets/<int:ticket_id>/review", methods=["POST"])
@login_required
def add_review_dash(ticket_id):
    gid = current_guild_id()
    ticket = database.get_ticket_by_id(gid, ticket_id)
    if not ticket:
        return "Ticket bulunamadı.", 404
    try:
        stars = int(request.form.get("stars", 1))
    except ValueError:
        stars = 1
    stars = max(1, min(stars, 5))
    comment = request.form.get("comment", "").strip()
    database.add_review(gid, ticket_id, 0, stars, comment)
    return redirect(url_for("ticket_detail", ticket_id=ticket_id))


@app.route("/switch-guild", methods=["POST"])
@login_required
def switch_guild():
    guild_id = request.form.get("guild_id")
    if guild_id and any(int(guild_id) == g["id"] for g in available_guilds()):
        session["guild_id"] = int(guild_id)
    return redirect(url_for("home"))


@app.route("/commands/add", methods=["POST"])
@login_required
def add_command():
    guild_id = current_guild_id()
    name = request.form.get("name", "").strip().lower()
    if not name or not name.isalnum():
        return "Komut adı boş olamaz ve sadece harf/sayı içermelidir.", 400
    data = {
        "response_text": request.form.get("response_text", ""),
        "embed_title": request.form.get("embed_title", ""),
        "embed_description": request.form.get("embed_description", ""),
        "embed_color": request.form.get("embed_color", "#5865F2"),
        "action_type": request.form.get("action_type", "reply"),
        "action_value": request.form.get("action_value", ""),
        "target_value": request.form.get("target_value", ""),
        "enabled": request.form.get("enabled") == "on",
    }
    database.add_custom_command(guild_id, name, data)
    _slash_refresh(guild_id)
    return redirect(url_for("home"))


@app.route("/commands/delete", methods=["POST"])
@login_required
def delete_command():
    name = request.form.get("name", "").strip().lower()
    database.delete_custom_command(current_guild_id(), name)
    _slash_refresh(current_guild_id())
    return redirect(url_for("home"))


@app.route("/commands/sync", methods=["POST"])
@login_required
def sync_commands():
    _slash_refresh(current_guild_id())
    return redirect(url_for("home"))


@app.route("/tickets/close", methods=["POST"])
@login_required
def close_ticket_dash():
    channel_id = int(request.form.get("channel_id", 0))
    ticket = database.get_ticket(channel_id)
    if ticket and ticket["guild_id"] != current_guild_id():
        return "Bu sunucunun bileti değil.", 400
    if ticket:
        database.close_ticket(channel_id)
        bot = get_bot()
        if bot is not None:
            for g in bot.guilds:
                ch = g.get_channel(channel_id)
                if ch:
                    try:
                        bot.loop.create_task(ch.delete())
                    except Exception:
                        pass
                    break
    return redirect(url_for("home"))


@app.route("/tickets/delete", methods=["POST"])
@login_required
def delete_ticket_dash():
    ticket_id = int(request.form.get("ticket_id", 0))
    gid = current_guild_id()
    if database.delete_ticket_by_id(gid, ticket_id):
        return redirect(url_for("home"))
    return "Ticket bulunamadı.", 400


@app.route("/modlog/delete", methods=["POST"])
@login_required
def delete_modlog_dash():
    log_id = int(request.form.get("log_id", 0))
    gid = current_guild_id()
    res = database.delete_mod_log(gid, log_id)
    if res["deleted"]:
        _post_deleted_embed(gid, log_id, res["message_id"])
        return redirect(url_for("home"))
    return "Kayıt bulunamadı.", 400


@app.route("/warnings/delete", methods=["POST"])
@login_required
def delete_warning_dash():
    warning_id = int(request.form.get("warning_id", 0))
    if database.delete_warning(warning_id):
        return redirect(url_for("home"))
    return "Uyarı bulunamadı.", 400


@app.route("/settings/prefix", methods=["POST"])
@login_required
def update_prefix():
    new_prefix = request.form.get("prefix", "!").strip()
    if not new_prefix or len(new_prefix) > 5:
        return "Prefix 1-5 karakter olmalı.", 400
    database.set_prefix(current_guild_id(), new_prefix)
    return redirect(url_for("home"))


def available_guilds():
    """Bot çalışıyorsa gerçek sunucuları, çalışmıyorsa DB'deki sunucuları döndürür."""
    bot = get_bot()
    guilds = []
    if bot is not None:
        for g in bot.guilds:
            guilds.append(
                {
                    "id": g.id,
                    "name": g.name,
                    "icon": g.icon.url if g.icon else None,
                    "member_count": g.member_count,
                }
            )
    if not guilds:
        import sqlite3

        try:
            conn = sqlite3.connect(config.DB_PATH)
            rows = conn.execute("SELECT DISTINCT guild_id FROM custom_commands UNION SELECT DISTINCT guild_id FROM guilds").fetchall()
            conn.close()
            for (guild_id,) in rows:
                guilds.append({"id": guild_id, "name": str(guild_id), "icon": None, "member_count": 0})
        except Exception:
            pass
    return guilds


if __name__ == "__main__":
    database.init_db()
    print("[OK] Veritabanı hazır.")
    if config.DISCORD_TOKEN and config.DISCORD_TOKEN != "PASTIRINIZ_BURAYA":
        start_bot_thread()
        print("[OK] Discord botu arka planda başlatıldı.")
    else:
        print("[UYARI] DISCORD_TOKEN boş. Lütfen .env dosyasını doldurun.")
    print(f"[OK] Dashboard: http://127.0.0.1:{config.DASHBOARD_PORT}")
    app.run(host="127.0.0.1", port=config.DASHBOARD_PORT, debug=False)