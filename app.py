from flask import Flask, render_template, request, redirect, url_for, session
import os
import sqlite3
import qrcode

app = Flask(__name__)
app.secret_key = "pizarro123"

# =========================
# CONFIG
# =========================

# RAILWAY: vá em seu projeto → Add Volume → Mount Path: /data
# Isso garante que o banco de dados persiste entre deploys e reinicializações.
DATA_DIR  = os.environ.get("DATA_DIR", "/data")
DB_PATH   = os.path.join(DATA_DIR, "pizarro.db")
QR_FOLDER = "static/qrcodes"

BASE_URL = os.environ.get(
    "BASE_URL",
    "https://movelaria-pizarro-production.up.railway.app"
).rstrip("/")

os.makedirs(DATA_DIR,  exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

# =========================
# BANCO DE DADOS
# =========================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sobras (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                largura   TEXT NOT NULL,
                altura    TEXT NOT NULL,
                espessura TEXT,
                cor       TEXT,
                obs       TEXT,
                usado     TEXT NOT NULL DEFAULT 'NÃO'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                user  TEXT UNIQUE NOT NULL,
                senha TEXT NOT NULL
            )
        """)
        conn.commit()

init_db()

# =========================
# HELPERS QR
# =========================
def gerar_qr(item_id):
    url = f"{BASE_URL}/sobra/{item_id}"
    qr = qrcode.make(url)
    qr.save(f"{QR_FOLDER}/qr_{item_id}.png")

def regenerar_todos_qrs():
    """Regenera QR codes ausentes ao iniciar o servidor."""
    try:
        with get_db() as conn:
            rows = conn.execute("SELECT id FROM sobras").fetchall()
        for row in rows:
            qr_path = f"{QR_FOLDER}/qr_{row['id']}.png"
            if not os.path.exists(qr_path):
                gerar_qr(row["id"])
    except Exception:
        pass

regenerar_todos_qrs()

# =========================
# LOGIN
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("index"))

    erro = None
    if request.method == "POST":
        user  = request.form.get("user",  "").strip()
        senha = request.form.get("senha", "").strip()

        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM usuarios WHERE user = ? AND senha = ?",
                (user, senha)
            ).fetchone()

        if row:
            session["user"] = user
            return redirect(url_for("index"))
        else:
            erro = "Usuário ou senha incorretos."

    return render_template("login.html", erro=erro)

# =========================
# CADASTRO
# =========================
@app.route("/register", methods=["GET", "POST"])
def register():
    erro = None
    if request.method == "POST":
        user   = request.form.get("user",   "").strip()
        senha  = request.form.get("senha",  "").strip()
        senha2 = request.form.get("senha2", "").strip()

        if not user or not senha:
            erro = "Preencha todos os campos."
        elif senha != senha2:
            erro = "As senhas não coincidem."
        else:
            try:
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO usuarios (user, senha) VALUES (?, ?)",
                        (user, senha)
                    )
                    conn.commit()
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                erro = "Este usuário já existe. Escolha outro."

    return render_template("register.html", erro=erro)

# =========================
# HOME — ESTOQUE
# =========================
@app.route("/", methods=["GET", "POST"])
def index():
    if "user" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        largura   = request.form.get("largura",   "").strip()
        altura    = request.form.get("altura",    "").strip()
        espessura = request.form.get("espessura", "").strip()
        cor       = request.form.get("cor",       "").strip()
        obs       = request.form.get("obs",       "").strip()

        if largura and altura:
            with get_db() as conn:
                cursor = conn.execute(
                    """INSERT INTO sobras (largura, altura, espessura, cor, obs, usado)
                       VALUES (?, ?, ?, ?, ?, 'NÃO')""",
                    (largura, altura, espessura, cor, obs)
                )
                conn.commit()
                new_id = cursor.lastrowid

            gerar_qr(new_id)

        return redirect(url_for("index"))

    with get_db() as conn:
        rows = conn.execute("SELECT * FROM sobras ORDER BY id DESC").fetchall()

    dados = [dict(row) for row in rows]
    return render_template("index.html", dados=dados, user=session["user"])

# =========================
# DETALHE (via QR Code)
# =========================
@app.route("/sobra/<int:id>")
def detalhe(id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM sobras WHERE id = ?", (id,)).fetchone()

    if not row:
        return "Peça não encontrada.", 404

    return render_template("detalhe.html", sobra=dict(row))

# =========================
# USAR PEÇA
# =========================
@app.route("/usar/<int:id>")
def usar(id):
    if "user" not in session:
        return redirect(url_for("login"))

    with get_db() as conn:
        row = conn.execute("SELECT * FROM sobras WHERE id = ?", (id,)).fetchone()

        if not row:
            return "Peça não encontrada.", 404

        if row["usado"] == "NÃO":
            conn.execute(
                "UPDATE sobras SET usado = ? WHERE id = ?",
                (session["user"], id)
            )
            conn.commit()

    return redirect(url_for("index"))

# =========================
# DASHBOARD
# =========================
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    with get_db() as conn:
        total       = conn.execute("SELECT COUNT(*) FROM sobras").fetchone()[0]
        usados      = conn.execute("SELECT COUNT(*) FROM sobras WHERE usado != 'NÃO'").fetchone()[0]
        disponiveis = total - usados

        usados_rows = conn.execute(
            "SELECT largura, altura, usado FROM sobras WHERE usado != 'NÃO'"
        ).fetchall()

        ranking_rows = conn.execute(
            """SELECT usado, COUNT(*) as total FROM sobras
               WHERE usado != 'NÃO'
               GROUP BY usado ORDER BY total DESC"""
        ).fetchall()

    PRECO_M2 = 100
    economia = 0.0
    for row in usados_rows:
        try:
            area = (float(row["largura"]) * float(row["altura"])) / 1_000_000
            economia += area * PRECO_M2
        except (ValueError, TypeError):
            pass

    porcentagem = round(usados / total * 100, 1) if total > 0 else 0
    ranking = {row["usado"]: row["total"] for row in ranking_rows}

    return render_template(
        "dashboard.html",
        usados=usados,
        disponiveis=disponiveis,
        economia=round(economia, 2),
        porcentagem=porcentagem,
        ranking=ranking,
        user=session["user"]
    )

# =========================
# LOGOUT
# =========================
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)