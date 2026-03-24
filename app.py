from flask import Flask, render_template, request, redirect, url_for, session
import pandas as pd
import os
import qrcode
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = "pizarro123"

# =========================
# CONFIG
# =========================
EXCEL_FILE = "sobras.xlsx"
USERS_FILE = "usuarios.xlsx"
QR_FOLDER = "static/qrcodes"

BASE_URL = "https://movelaria-pizarro-production.up.railway.app"

os.makedirs(QR_FOLDER, exist_ok=True)

# =========================
# CRIAR ARQUIVOS
# =========================
if not os.path.exists(EXCEL_FILE):
    df = pd.DataFrame(columns=[
        "id", "largura", "altura", "espessura",
        "cor", "obs", "usado"
    ])
    df.to_excel(EXCEL_FILE, index=False)

if not os.path.exists(USERS_FILE):
    df_users = pd.DataFrame(columns=["user", "senha"])
    df_users.to_excel(USERS_FILE, index=False)

# =========================
# FUNÇÕES
# =========================
def load_data():
    return pd.read_excel(EXCEL_FILE)

def save_data(df):
    df.to_excel(EXCEL_FILE, index=False)

def load_users():
    return pd.read_excel(USERS_FILE)

def save_users(df):
    df.to_excel(USERS_FILE, index=False)

# =========================
# LOGIN
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form["user"].strip()
        senha = request.form["senha"].strip()

        df_users = load_users()
        df_users["user"] = df_users["user"].astype(str).str.strip()
        df_users["senha"] = df_users["senha"].astype(str).str.strip()

        usuario = df_users[
            (df_users["user"] == user) & (df_users["senha"] == senha)
        ]

        if not usuario.empty:
            session["user"] = user
            return redirect(url_for("index"))
        else:
            return "Login inválido"

    return render_template("login.html")

# =========================
# CADASTRO
# =========================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        user = request.form["user"].strip()
        senha = request.form["senha"].strip()

        df_users = load_users()
        df_users["user"] = df_users["user"].astype(str).str.strip()

        if user in df_users["user"].values:
            return "Usuário já existe!"

        new_user = {"user": user, "senha": senha}
        df_users = pd.concat([df_users, pd.DataFrame([new_user])], ignore_index=True)
        save_users(df_users)

        return redirect(url_for("login"))

    return render_template("register.html")

# =========================
# HOME
# =========================
@app.route("/", methods=["GET", "POST"])
def index():
    if "user" not in session:
        return redirect("/login")

    df = load_data()

    if request.method == "POST":
        new_id = len(df) + 1

        new_row = {
            "id": new_id,
            "largura": request.form["largura"],
            "altura": request.form["altura"],
            "espessura": request.form["espessura"],
            "cor": request.form["cor"],
            "obs": request.form["obs"],
            "usado": "NÃO"
        }

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        save_data(df)

        # QR CODE ONLINE
        url = f"{BASE_URL}/sobra/{new_id}"
        qr = qrcode.make(url)
        qr.save(f"{QR_FOLDER}/qr_{new_id}.png")

        return redirect(url_for("index"))

    return render_template("index.html", dados=df.to_dict(orient="records"))

# =========================
# DETALHE (QR)
# =========================
@app.route("/sobra/<int:id>")
def detalhe(id):
    df = load_data()
    sobra = df[df["id"] == id].iloc[0]
    return render_template("detalhe.html", sobra=sobra)

# =========================
# USAR (FUNCIONÁRIO)
# =========================
@app.route("/usar/<int:id>")
def usar(id):
    if "user" not in session:
        return redirect("/login")

    df = load_data()

    df.loc[df["id"] == id, "usado"] = session["user"]

    save_data(df)
    return redirect("/")

# =========================
# DASHBOARD COMPLETO
# =========================
@app.route("/dashboard")
def dashboard():
    df = load_data()

    total = len(df)
    usados_df = df[df["usado"] != "NÃO"]

    usados = len(usados_df)
    disponiveis = total - usados

    # 💰 economia
    preco_mdf_m2 = 100
    economia = 0

    for _, row in usados_df.iterrows():
        try:
            largura = float(row["largura"])
            altura = float(row["altura"])
            area = (largura * altura) / 1000000
            economia += area * preco_mdf_m2
        except:
            pass

    # 📊 porcentagem
    porcentagem = (usados / total * 100) if total > 0 else 0

    # 👷 ranking
    ranking = usados_df["usado"].value_counts().to_dict()

    # 📈 gráfico
    labels = ["Usados", "Disponíveis"]
    valores = [usados, disponiveis]

    plt.figure()
    plt.bar(labels, valores)
    plt.savefig("static/grafico.png")
    plt.close()

    return render_template(
        "dashboard.html",
        usados=usados,
        disponiveis=disponiveis,
        economia=round(economia, 2),
        porcentagem=round(porcentagem, 1),
        ranking=ranking
    )

# =========================
# LOGOUT
# =========================
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

# =========================
# RUN (RAILWAY)
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)