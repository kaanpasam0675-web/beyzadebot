import functools
import os
import sys
import asyncio
import json
import urllib.parse
import urllib.request

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
        if not session.get("logged_in") and not session.get("discord_user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def owner_required(view):
    """Yalnızca şifreyle giriş yapan sahip erişebilir."""
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            if session.get("discord_user"):
                return "Bu işlem için yalnızca sahip yetkilidir.", 403
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def is_owner_session():
    return bool(session.get("logged_in"))


def current_guild_id():
    return int(session.get("guild_id", 0))


def _discord_oauth_url():
    """Discord authorize sayfasına yönlendiren URL."""
    params = urllib.parse.urlencode(
        {
            "client_id": config.DISCORD_CLIENT_ID,
            "redirect_uri": config.OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": "identify guilds",
        }
    )
    return f"https://discord.com/api/v10/oauth2/authorize?{params}"


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
    # Şifre belirlenmediyse doğrudan içeri al
    if not config.DASHBOARD_PASSWORD:
        session["logged_in"] = True
        return redirect(url_for("home"))
    if session.get("logged_in") or session.get("discord_user"):
        return redirect(url_for("home"))
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == config.DASHBOARD_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("home"))
        error = "Yanlış şifre."
    oauth_url = _discord_oauth_url() if config.DISCORD_CLIENT_ID else None
    invite_url = config.INVITE_URL if config.DISCORD_CLIENT_ID else None
    return render_template("login.html", error=error, oauth_url=oauth_url, invite_url=invite_url)


@app.route("/login/discord")
def discord_login():
    if not config.DISCORD_CLIENT_ID or not config.DISCORD_CLIENT_SECRET:
        return "OAuth yapılandırılmamış (DISCORD_CLIENT_ID / SECRET eksik).", 500
    return redirect(_discord_oauth_url())


@app.route("/login/discord/callback")
def discord_callback():
    code = request.args.get("code")
    state = request.args.get("state")
    if not code:
        return redirect(url_for("login"))
    data = urllib.parse.urlencode(
        {
            "client_id": config.DISCORD_CLIENT_ID,
            "client_secret": config.DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.OAUTH_REDIRECT_URI,
        }
    ).encode()
    req = urllib.request.Request(
        "https://discord.com/api/v10/oauth2/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            token_data = json.loads(resp.read().decode())
    except Exception as e:
        return f"Token alınamadı: {e}", 500
    access_token = token_data.get("access_token")
    if not access_token:
        return "OAuth doğrulaması başarısız.", 400
    session["discord_user"] = _fetch_discord_identity(access_token)
    session["discord_guilds"] = _fetch_discord_guilds(access_token)
    session.pop("logged_in", None)
    return redirect(url_for("home"))


def _fetch_discord_identity(access_token):
    req = urllib.request.Request(
        "https://discord.com/api/v10/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    return {
        "id": int(data.get("id", 0)),
        "username": data.get("username", "?"),
        "global_name": data.get("global_name") or data.get("username", "?"),
        "avatar": f"https://cdn.discordapp.com/avatars/{data.get('id')}/{data.get('avatar')}.png" if data.get("avatar") else None,
    }


def _fetch_discord_guilds(access_token):
    """Kullanıcının yönetici (admin) olduğu sunucuların ID'lerini döndürür."""
    req = urllib.request.Request(
        "https://discord.com/api/v10/users/@me/guilds",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        guilds = json.loads(resp.read().decode())
    admin_ids = []
    for g in guilds:
        permissions = int(g.get("permissions", 0))
        is_admin = bool(permissions & 0x8)
        is_owner = bool(g.get("owner"))
        if is_admin or is_owner:
            admin_ids.append(int(g["id"]))
    return admin_ids


@app.route("/guilds/bot-join", methods=["POST"])
@owner_required
def bot_join_guild():
    """Sahip, verilen davet linkiyle BOT'u bir sunucuya katılır."""
    invite_input = request.form.get("invite_code", "").strip()
    if not invite_input:
        return "Davet linki boş.", 400
    # discord.gg/XXXX veya https://discord.gg/XXXX ya da sadece kod şeklinde olabilir
    code = invite_input
    if "/" in code:
        code = code.split("/")[-1]
    code = code.split("?")[0].strip()
    bot = get_bot()
    if bot is None or not bot.is_ready():
        return "Bot çevrimiçi değil.", 400

    import asyncio

    result = {}

    async def _join():
        try:
            invite = await bot.fetch_invite(code)
            await invite.accept()
            result["ok"] = True
            guild_name = getattr(invite, "guild", None)
            result["name"] = guild_name.name if guild_name else code
        except Exception as e:
            result["ok"] = False
            result["error"] = repr(e)

    fut = asyncio.run_coroutine_threadsafe(_join(), bot.loop)
    fut.result(timeout=25)
    if not result.get("ok"):
        return f"Hata: {result.get('error')}", 400
    return redirect(url_for("home"))


@app.route("/guilds/leave", methods=["POST"])
@owner_required
def leave_guild():
    gid = int(request.form.get("guild_id", 0) or current_guild_id())
    bot = get_bot()
    if bot is None or not bot.is_ready():
        return "Bot çevrimiçi değil.", 400
    guild = bot.get_guild(gid)
    if guild is None:
        return "Sunucu bulunamadı.", 400

    import asyncio

    result = {}

    async def _leave():
        try:
            await guild.leave()
            result["ok"] = True
        except Exception as e:
            result["ok"] = False
            result["error"] = repr(e)

    fut = asyncio.run_coroutine_threadsafe(_leave(), bot.loop)
    fut.result(timeout=20)
    if not result.get("ok"):
        return f"Hata: {result.get('error')}", 400
    session.pop("guild_id", None)
    return redirect(url_for("home"))


@app.route("/guilds/join", methods=["POST"])
@owner_required
def join_guild():
    """Bot, seçili sunucu için tek kullanımlık davet linki üretir; sen linke tıklayıp sunucuya girersin."""
    gid = int(request.form.get("guild_id", 0) or current_guild_id())
    bot = get_bot()
    if bot is None or not bot.is_ready():
        return "Bot çevrimiçi değil.", 400
    guild = bot.get_guild(gid)
    if guild is None:
        return "Sunucu bulunamadı.", 400

    import asyncio

    result = {}

    async def _create():
        try:
            for ch in guild.text_channels:
                perms = ch.permissions_for(guild.me)
                if perms.create_instant_invite:
                    invite = await ch.create_invite(max_age=300, max_uses=1, reason="Dashboard'dan giriş")
                    result["ok"] = True
                    result["url"] = f"https://discord.gg/{invite.code}"
                    return
            result["ok"] = False
            result["error"] = "Botun davet oluşturabildiği kanal yok (İzin eksik)."
        except Exception as e:
            result["ok"] = False
            result["error"] = repr(e)

    fut = asyncio.run_coroutine_threadsafe(_create(), bot.loop)
    fut.result(timeout=20)
    if not result.get("ok"):
        return f"Hata: {result.get('error')}", 400
    return redirect(result["url"])


@app.route("/guilds/set-tag", methods=["POST"])
@owner_required
def set_bot_tag_route():
    """Sahip, seçili sunucu için botun kullanacağı etiketi (tag) ayarlar."""
    gid = int(request.form.get("guild_id", 0) or current_guild_id())
    tag = request.form.get("bot_tag", "").strip()
    database.set_bot_tag(gid, tag)
    bot = get_bot()
    if bot is not None and bot.is_ready():
        guild = bot.get_guild(gid)
        if guild is not None and tag:
            import asyncio

            async def _nick():
                new_nick = f"{tag} {bot.user.name}"
                if guild.me.nick != new_nick:
                    await guild.me.edit(nick=new_nick)

            asyncio.run_coroutine_threadsafe(_nick(), bot.loop).result(timeout=20)
    return redirect(url_for("home"))


@app.route("/guilds/assign-role", methods=["POST"])
@owner_required
def assign_role():
    """Sahip, seçili sunucuda bir Discord kullanıcısına (kendisine) rol verir."""
    gid = int(request.form.get("guild_id", 0) or current_guild_id())
    role_id = request.form.get("role_id")
    user_id = request.form.get("user_id", "").strip()
    try:
        role_id = int(role_id or 0)
        target_user_id = int(user_id)
    except (ValueError, TypeError):
        return "Geçersiz rol/kullanıcı.", 400
    if not role_id or not target_user_id:
        return "Rol ve kullanıcı seçin.", 400
    bot = get_bot()
    if bot is None or not bot.is_ready():
        return "Bot çevrimiçi değil.", 400
    guild = bot.get_guild(gid)
    if guild is None:
        return "Sunucu bulunamadı.", 400

    import asyncio

    result = {}

    async def _assign():
        try:
            member = guild.get_member(target_user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(target_user_id)
                except Exception:
                    member = None
            if member is None:
                result["ok"] = False
                result["error"] = "Kullanıcı bu sunucuda bulunamadı."
                return
            role = discord.utils.get(guild.roles, id=role_id)
            if role is None:
                result["ok"] = False
                result["error"] = "Rol bulunamadı."
                return
            await member.add_roles(role, reason="Dashboard'dan rol verildi")
            result["ok"] = True
        except Exception as e:
            result["ok"] = False
            result["error"] = repr(e)

    fut = asyncio.run_coroutine_threadsafe(_assign(), bot.loop)
    fut.result(timeout=20)
    if not result.get("ok"):
        return f"Hata: {result.get('error')}", 400
    return redirect(url_for("home"))


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
    roles = []
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
                roles = [
                    {"id": r.id, "name": r.name}
                    for r in sorted(guild.roles, key=lambda r: r.position, reverse=True)
                    if not r.is_default() and not r.managed
                ]
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
    invite_url = config.INVITE_URL if config.DISCORD_CLIENT_ID else None
    # Global duyuru için: her sunucunun metin kanalları
    guild_channel_map = {}
    bot = get_bot()
    if bot is not None:
        for g in bot.guilds:
            guild_channel_map[g.id] = [
                {"id": ch.id, "name": ch.name}
                for ch in g.text_channels
                if ch.permissions_for(g.me).send_messages
            ]
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
        invite_url=invite_url,
        oauth_user=session.get("discord_user"),
        is_owner=is_owner_session(),
        roles=roles,
        guild_channel_map=guild_channel_map,
    )


@app.route("/edit-profile", methods=["POST"])
@owner_required
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
@owner_required
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
@owner_required
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


@app.route("/global-announce", methods=["POST"])
@owner_required
def global_announce():
    """Sahip, botun bulunduğu TÜM sunucularda seçilen kanallara duyuru gönderir."""
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

    # Kullanıcının seçtiği kanallar: channel_{guild_id}
    selected = {}
    for key, value in request.form.items():
        if key.startswith("channel_"):
            try:
                gid = int(key.split("_", 1)[1])
            except ValueError:
                continue
            if value and value != "0":
                selected[gid] = int(value)

    import asyncio

    result = {"sent": 0, "failed": []}

    async def _announce():
        for guild in bot.guilds:
            if guild.id not in selected:
                continue  # bu sunucu için kanal seçilmedi -> atla
            channel = bot.get_channel(selected[guild.id])
            if channel is None or getattr(channel, "guild", None) is None or channel.guild.id != guild.id:
                result["failed"].append(f"{guild.name} (kanal bulunamadı)")
                continue
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
                        text=f"Global Duyuru • {bot.user.name if bot.user else 'Bot'}",
                        icon_url=bot.user.display_avatar.url if bot.user else None,
                    )
                    await channel.send(content=content or None, embed=embed)
                else:
                    await channel.send(content)
                result["sent"] += 1
            except Exception as e:
                result["failed"].append(f"{guild.name} ({type(e).__name__})")

    fut = asyncio.run_coroutine_threadsafe(_announce(), bot.loop)
    fut.result(timeout=60)
    msg = f"Duyuru {result['sent']} sunucuya gönderildi."
    if result["failed"]:
        msg += f" Başarısız: {', '.join(result['failed'])}"
    return f"{msg}<br><a href='{url_for('home')}'>Geri dön</a>", 200


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
    try:
        guild_id = int(guild_id or 0)
    except ValueError:
        guild_id = 0
    allowed = available_guilds()
    if guild_id and any(guild_id == g["id"] for g in allowed):
        session["guild_id"] = guild_id
    return redirect(url_for("home"))


@app.route("/commands/add", methods=["POST"])
@owner_required
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
@owner_required
def delete_command():
    name = request.form.get("name", "").strip().lower()
    database.delete_custom_command(current_guild_id(), name)
    _slash_refresh(current_guild_id())
    return redirect(url_for("home"))


@app.route("/commands/sync", methods=["POST"])
@owner_required
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
@owner_required
def delete_ticket_dash():
    ticket_id = int(request.form.get("ticket_id", 0))
    gid = current_guild_id()
    if database.delete_ticket_by_id(gid, ticket_id):
        return redirect(url_for("home"))
    return "Ticket bulunamadı.", 400


@app.route("/modlog/delete", methods=["POST"])
@owner_required
def delete_modlog_dash():
    log_id = int(request.form.get("log_id", 0))
    gid = current_guild_id()
    res = database.delete_mod_log(gid, log_id)
    if res["deleted"]:
        _post_deleted_embed(gid, log_id, res["message_id"])
        return redirect(url_for("home"))
    return "Kayıt bulunamadı.", 400


@app.route("/warnings/delete", methods=["POST"])
@owner_required
def delete_warning_dash():
    warning_id = int(request.form.get("warning_id", 0))
    if database.delete_warning(warning_id):
        return redirect(url_for("home"))
    return "Uyarı bulunamadı.", 400


@app.route("/settings/prefix", methods=["POST"])
@owner_required
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
    # Discord OAuth kullanıcısı: yalnızca admin olduğu ve botun da olduğu sunucular
    if session.get("discord_user"):
        allowed = set(session.get("discord_guilds", []))
        guilds = [g for g in guilds if g["id"] in allowed or not bot]
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
    port = int(os.getenv("PORT") or config.DASHBOARD_PORT)
    print(f"[OK] Dashboard: http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)