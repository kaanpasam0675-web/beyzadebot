import functools
import html
import os
import secrets
import sqlite3
import threading
from datetime import datetime

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "site.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

CATEGORIES = {
    "duyurular": "Duyurular",
    "egitim": "Eğitim",
    "etkinlikler": "Etkinlikler",
    "spor": "Spor",
    "bilim": "Bilim",
    "sanat": "Sanat",
    "kultur": "Kültür",
}
ROLE_LABELS = {"kurucu": "Kurucu", "yetkili": "Yetkili"}
TR_MONTHS = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

# İlk kurulumda oluşturulacak kurucu hesabı (.env / sistem değişkeniyle değiştirilebilir)
SITE_FOUNDER_USER = os.getenv("SITE_FOUNDER_USER", "kurucu")
SITE_FOUNDER_PASSWORD = os.getenv("SITE_FOUNDER_PASSWORD", "suleymaniye2026")

app = Flask(__name__)
app.secret_key = os.getenv("SITE_SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

_lock = threading.Lock()


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'yetkili',
                full_name TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT DEFAULT 'duyurular',
                summary TEXT DEFAULT '',
                content TEXT NOT NULL,
                image TEXT DEFAULT '',
                author_id INTEGER NOT NULL,
                author_name TEXT DEFAULT '',
                views INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'published',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.commit()

        # Kurucu hesabı yoksa oluştur
        row = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, full_name, created_at) VALUES (?, ?, ?, ?, ?)",
                (SITE_FOUNDER_USER,
                 generate_password_hash(SITE_FOUNDER_PASSWORD),
                 "kurucu", "Site Kurucusu", datetime.now().isoformat()),
            )
            conn.commit()
            print("[OK] Kurucu hesap oluşturuldu:")
            print(f"    Kullanıcı adı : {SITE_FOUNDER_USER}")
            print(f"    Şifre         : {SITE_FOUNDER_PASSWORD}")
            print("    (Değiştirmek için SITE_FOUNDER_USER / SITE_FOUNDER_PASSWORD ortam değişkenleri kullanın)")

        # Örnek haberler yoksa ekle
        count = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
        if count == 0:
            founder = conn.execute(
                "SELECT id, full_name, username FROM users WHERE role = 'kurucu' LIMIT 1"
            ).fetchone()
            author_id = founder["id"]
            author_name = founder["full_name"] or founder["username"]
            now = datetime.now().isoformat()
            samples = [
                (
                    "Yeni Eğitim Dönemi Başladı",
                    "duyurular",
                    "Öğrencilerimiz için keyifli ve verimli bir dönem diliyoruz.",
                    "Süleymaniye Okulu olarak yeni eğitim öğretim dönemine tüm öğrencilerimizle birlikte "
                    "merhaba dedik. Derslerimiz, etkinliklerimiz ve projelerimiz tüm hızıyla devam ediyor.\n\n"
                    "Bu dönemde hepinize başarılar diler, okulumuzun her köşesinde öğrenmenin ve "
                    "üretmenin heyecanını birlikte yaşamayı umuyoruz.",
                    author_id, author_name, now, now,
                ),
                (
                    "Bilim Şenliği Büyük İlgi Gördü",
                    "bilim",
                    "Öğrencilerimizin hazırladığı projeler şenlikte sergilendi.",
                    "Öğrencilerimiz, yıl boyunca hazırladıkları fen ve teknoloji projelerini "
                    "Bilim Şenliği'nde sergiledi. Deneyler, robotik çalışmalar ve araştırmalar "
                    "büyük ilgi gördü.\n\nEmeği geçen tüm öğretmen ve öğrencilerimizi tebrik ediyoruz.",
                    author_id, author_name, now, now,
                ),
                (
                    "Okullar Arası Futbol Turnuvası",
                    "spor",
                    "Takımımız turnuvada mücadeleye başladı.",
                    "Okullar arası düzenlenen futbol turnuvasında okul takımımız sahaya çıktı. "
                    "Öğrencilerimiz büyük bir heyecanla taraftar gruplarını oluşturdu.\n\n"
                    "Takımımıza başarılar diler, tüm öğrencilerimizi tribünlere bekleriz.",
                    author_id, author_name, now, now,
                ),
            ]
            cur.executemany(
                """INSERT INTO articles (title, category, summary, content, author_id,
                                        author_name, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                samples,
            )
            conn.commit()
        conn.close()


def save_image(file) -> str:
    if not file or not file.filename:
        return ""
    fn = secure_filename(file.filename)
    if not fn or "." not in fn:
        return ""
    ext = fn.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return ""
    name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{os.urandom(3).hex()}.{ext}"
    file.save(os.path.join(UPLOAD_FOLDER, name))
    return name


def remove_image(filename: str):
    if not filename:
        return
    try:
        path = os.path.join(UPLOAD_FOLDER, os.path.basename(filename))
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT id, username, role, full_name FROM users WHERE id = ?", (uid,)
        ).fetchone()
        conn.close()
    return dict(row) if row else None


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Lütfen önce giriş yapın.", "warning")
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def kurucu_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Lütfen önce giriş yapın.", "warning")
            return redirect(url_for("admin_login", next=request.path))
        if user["role"] != "kurucu":
            flash("Bu bölüme yalnızca kurucu erişebilir.", "error")
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def category_totals():
    with _lock:
        conn = _conn()
        rows = conn.execute(
            "SELECT category, COUNT(*) AS c FROM articles WHERE status = 'published' GROUP BY category"
        ).fetchall()
        conn.close()
    totals = {slug: 0 for slug in CATEGORIES}
    for r in rows:
        totals[r["category"]] = r["c"]
    return totals


# ---------- Jinja yardımcıları ----------

@app.template_filter("nf")
def nl2br_filter(value):
    return html.escape(value or "").replace("\n", "<br>")

@app.template_filter("trdate")
def trdate_filter(value):
    try:
        d = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return value or ""
    return f"{d.day} {TR_MONTHS[d.month]} {d.year}"

@app.template_filter("catname")
def catname_filter(slug):
    return CATEGORIES.get(slug or "", "Genel")

@app.context_processor
def inject_globals():
    return {
        "categories": CATEGORIES,
        "category_totals": category_totals(),
        "now_year": datetime.now().year,
        "role_labels": ROLE_LABELS,
        "user": current_user(),
    }


# ---------- Genel sayfalar ----------

@app.route("/")
def index():
    featured = None
    with _lock:
        conn = _conn()
        rows = conn.execute(
            "SELECT * FROM articles WHERE status = 'published' ORDER BY views DESC, created_at DESC LIMIT 1"
        ).fetchone()
        if rows:
            featured = dict(rows)
        articles = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM articles WHERE status = 'published' ORDER BY created_at DESC LIMIT 9"
            ).fetchall()
        ]
        latest_sidebar = [
            dict(r)
            for r in conn.execute(
                "SELECT id, title, category, created_at FROM articles WHERE status = 'published' ORDER BY created_at DESC LIMIT 5"
            ).fetchall()
        ]
        conn.close()
    return render_template(
        "index.html",
        featured=featured,
        articles=articles,
        latest_sidebar=latest_sidebar,
    )


@app.route("/haberler")
def all_articles():
    page = max(request.args.get("sayfa", 1, type=int), 1)
    per_page = 9
    q = request.args.get("q", "").strip()
    cat = request.args.get("kategori", "").strip()
    params = []
    where = "WHERE status = 'published'"
    if cat in CATEGORIES:
        where += " AND category = ?"
        params.append(cat)
    if q:
        where += " AND (title LIKE ? OR summary LIKE ? OR content LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    with _lock:
        conn = _conn()
        total = conn.execute(f"SELECT COUNT(*) AS c FROM articles {where}", params).fetchone()["c"]
        articles = [
            dict(r)
            for r in conn.execute(
                f"SELECT * FROM articles {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params + [per_page, (page - 1) * per_page],
            ).fetchall()
        ]
        conn.close()
    total_pages = max((total + per_page - 1) // per_page, 1)
    return render_template(
        "haberler.html",
        articles=articles,
        page=page,
        total_pages=total_pages,
        total=total,
        q=q,
        cat=cat if cat in CATEGORIES else "",
    )


@app.route("/haber/<int:article_id>")
def article_detail(article_id):
    with _lock:
        conn = _conn()
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        if row is not None:
            conn.execute("UPDATE articles SET views = views + 1 WHERE id = ?", (article_id,))
            conn.commit()
        conn.close()
    article = dict(row) if row else None
    if article is None or article["status"] != "published":
        abort(404)
    with _lock:
        conn = _conn()
        related = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM articles WHERE status = 'published' AND category = ? AND id != ? ORDER BY created_at DESC LIMIT 3",
                (article["category"], article_id),
            ).fetchall()
        ]
        conn.close()
    return render_template("article.html", article=article, related=related)


@app.route("/kategori/<slug>")
def category_page(slug):
    if slug not in CATEGORIES:
        abort(404)
    with _lock:
        conn = _conn()
        articles = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM articles WHERE status = 'published' AND category = ? ORDER BY created_at DESC",
                (slug,),
            ).fetchall()
        ]
        conn.close()
    return render_template("category.html", slug=slug, articles=articles)


# ---------- Giriş / çıkış ----------

@app.route("/admin/giris", methods=["GET", "POST"])
def admin_login():
    if session.get("user_id"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with _lock:
            conn = _conn()
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            conn.close()
        if row and check_password_hash(row["password_hash"], password):
            session.clear()
            session["user_id"] = row["id"]
            session["user_name"] = row["full_name"] or row["username"]
            session["user_role"] = row["role"]
            flash(f"Hoş geldiniz, {session['user_name']}!", "success")
            nxt = request.args.get("next")
            return redirect(nxt if nxt and nxt.startswith("/") else url_for("admin_dashboard"))
        flash("Kullanıcı adı veya şifre hatalı.", "error")
    return render_template("admin/login.html")


@app.route("/admin/cikis")
def admin_logout():
    session.clear()
    flash("Çıkış yaptınız.", "info")
    return redirect(url_for("admin_login"))


# ---------- Yönetim paneli ----------

@app.route("/admin")
@login_required
def admin_dashboard():
    user = current_user()
    with _lock:
        conn = _conn()
        total = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
        published = conn.execute("SELECT COUNT(*) AS c FROM articles WHERE status = 'published'").fetchone()["c"]
        drafts = conn.execute("SELECT COUNT(*) AS c FROM articles WHERE status = 'draft'").fetchone()["c"]
        views = conn.execute("SELECT COALESCE(SUM(views), 0) AS v FROM articles").fetchone()["v"]
        by_cat = []
        for slug in CATEGORIES:
            c = conn.execute("SELECT COUNT(*) AS c FROM articles WHERE category = ?", (slug,)).fetchone()["c"]
            if c:
                by_cat.append({"slug": slug, "name": CATEGORIES[slug], "count": c})
        user_articles = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM articles ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
        ]
        users = [
            dict(r)
            for r in conn.execute(
                """SELECT u.id, u.username, u.role, u.full_name, u.created_at,
                          (SELECT COUNT(*) FROM articles a WHERE a.author_id = u.id) AS article_count
                   FROM users u ORDER BY u.role != 'kurucu', u.id""",
            ).fetchall()
        ]
        conn.close()
    return render_template(
        "admin/dashboard.html",
        user=user,
        stats={"total": total, "published": published, "drafts": drafts, "views": views},
        by_cat=by_cat,
        articles=user_articles,
        users=users,
    )


@app.route("/admin/haber/yeni", methods=["GET", "POST"])
@login_required
def article_new():
    user = current_user()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "duyurular")
        summary = request.form.get("summary", "").strip()
        content = request.form.get("content", "").strip()
        status = "published" if request.form.get("status") == "published" else "draft"
        if not title or not content:
            flash("Başlık ve içerik zorunludur.", "error")
            return render_template("admin/article_form.html", article=None, title="Yeni Haber")
        if category not in CATEGORIES:
            category = "duyurular"
        image = save_image(request.files.get("image"))
        now = datetime.now().isoformat()
        with _lock:
            conn = _conn()
            conn.execute(
                """INSERT INTO articles (title, category, summary, content, image, author_id,
                                         author_name, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (title, category, summary, content, image,
                 user["id"], user["full_name"] or user["username"],
                 status, now, now),
            )
            conn.commit()
            conn.close()
        flash("Haber yayınlandı." if status == "published" else "Haber taslak olarak kaydedildi.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin/article_form.html", article=None, title="Yeni Haber")


@app.route("/admin/haber/<int:article_id>/duzenle", methods=["GET", "POST"])
@login_required
def article_edit(article_id):
    user = current_user()
    with _lock:
        conn = _conn()
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        conn.close()
    if row is None:
        abort(404)
    article = dict(row)
    # Yetkili yalnızca kendi haberlerini düzenleyebilir
    if user["role"] != "kurucu" and article["author_id"] != user["id"]:
        flash("Sadece kendi haberlerinizi düzenleyebilirsiniz.", "error")
        abort(403)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "duyurular")
        summary = request.form.get("summary", "").strip()
        content = request.form.get("content", "").strip()
        status = "published" if request.form.get("status") == "published" else "draft"
        if not title or not content:
            flash("Başlık ve içerik zorunludur.", "error")
            return render_template("admin/article_form.html", article=article, title="Haber Düzenle")
        if category not in CATEGORIES:
            category = "duyurular"
        image = article["image"]
        new_img = save_image(request.files.get("image"))
        if new_img:
            remove_image(image)
            image = new_img
        elif request.form.get("remove_image"):
            remove_image(image)
            image = ""
        with _lock:
            conn = _conn()
            conn.execute(
                """UPDATE articles SET title = ?, category = ?, summary = ?, content = ?,
                       image = ?, status = ?, updated_at = ? WHERE id = ?""",
                (title, category, summary, content, image, status, datetime.now().isoformat(), article_id),
            )
            conn.commit()
            conn.close()
        flash("Haber güncellendi.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin/article_form.html", article=article, title="Haber Düzenle")


@app.route("/admin/haber/<int:article_id>/sil", methods=["POST"])
@login_required
def article_delete(article_id):
    user = current_user()
    with _lock:
        conn = _conn()
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        if row is None:
            conn.close()
            abort(404)
        if user["role"] != "kurucu" and row["author_id"] != user["id"]:
            conn.close()
            flash("Sadece kendi haberlerinizi silebilirsiniz.", "error")
            abort(403)
        conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
        conn.commit()
        conn.close()
    remove_image(row["image"])
    flash("Haber silindi.", "success")
    return redirect(url_for("admin_dashboard"))


# ---------- Kullanıcı yönetimi (yalnızca kurucu) ----------

@app.route("/admin/kullanicilar", methods=["GET", "POST"])
@kurucu_required
def users_page():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "yetkili")
        full_name = request.form.get("full_name", "").strip()
        if not username or len(password) < 4:
            flash("Kullanıcı adı zorunlu, şifre en az 4 karakter olmalı.", "error")
            return redirect(url_for("users_page"))
        if role not in ROLE_LABELS:
            role = "yetkili"
        with _lock:
            conn = _conn()
            try:
                conn.execute(
                    "INSERT INTO users (username, password_hash, role, full_name, created_at) VALUES (?, ?, ?, ?, ?)",
                    (username, generate_password_hash(password), role, full_name, datetime.now().isoformat()),
                )
                conn.commit()
                added = True
            except sqlite3.IntegrityError:
                added = False
            conn.close()
        if added:
            flash("Kullanıcı eklendi.", "success")
        else:
            flash("Bu kullanıcı adı zaten kullanılıyor.", "error")
        return redirect(url_for("users_page"))

    with _lock:
        conn = _conn()
        users = [
            dict(r)
            for r in conn.execute(
                """SELECT u.id, u.username, u.role, u.full_name, u.created_at,
                          (SELECT COUNT(*) FROM articles a WHERE a.author_id = u.id) AS article_count
                   FROM users u ORDER BY u.role != 'kurucu', u.id""",
            ).fetchall()
        ]
        conn.close()
    return render_template("admin/users.html", users=users)


@app.route("/admin/kullanici/<int:user_id>/sil", methods=["POST"])
@kurucu_required
def user_delete(user_id):
    if user_id == session.get("user_id"):
        flash("Kendi hesabınızı silemezsiniz.", "error")
        return redirect(url_for("users_page"))
    with _lock:
        conn = _conn()
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
    flash("Kullanıcı silindi.", "success")
    return redirect(url_for("users_page"))


@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    init_db()
    port = int(os.getenv("SITE_PORT", "5050"))
    print(f"[OK] Süleymaniye Okulu Haber Sitesi: http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)