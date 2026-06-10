from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import sqlite3, hashlib, jwt, datetime, random, os, re, base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── Twilio (optionnel) ────────────────────────
try:
    from twilio.rest import Client as TwilioClient
    TWILIO_OK = True
except ImportError:
    TWILIO_OK = False

# ── Config ────────────────────────────────────
try:
    from config import (
        GMAIL_USER, GMAIL_PASSWORD,
        TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM
    )
    MAIL_OK = True
    SMS_OK  = TWILIO_OK
    print("✅ Config chargée — Email & SMS actifs")
except Exception as e:
    MAIL_OK = False
    SMS_OK  = False
    print(f"⚠️  config.py manquant ({e}) — mode DEV (codes dans le terminal)")

app = FastAPI(title="SER Auth API")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# Servir les fichiers HTML directement
BASE      = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.join(BASE, "ser_users.db")
AVATAR_DIR= os.path.join(BASE, "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=BASE), name="static")

@app.get("/app")
def serve_login():
    return FileResponse(os.path.join(BASE, "index.html"))

@app.get("/dashboard")
def serve_dashboard():
    return FileResponse(os.path.join(BASE, "dashboard.html"))

SECRET_KEY = "SER_SECRET_2024_CHANGE_IN_PROD"
ALGORITHM  = "HS256"
bearer     = HTTPBearer()

# ── Database ──────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        fullname        TEXT NOT NULL,
        email           TEXT UNIQUE NOT NULL,
        phone           TEXT,
        password_hash   TEXT NOT NULL,
        birthdate       TEXT,
        gender          TEXT,
        country         TEXT,
        city            TEXT,
        profession      TEXT,
        avatar_path     TEXT,
        language        TEXT DEFAULT 'fr',
        email_verified  INTEGER DEFAULT 0,
        phone_verified  INTEGER DEFAULT 0,
        email_code      TEXT,
        phone_code      TEXT,
        code_expires    TEXT,
        created_at      TEXT DEFAULT (datetime('now')),
        last_login      TEXT
    );
    CREATE TABLE IF NOT EXISTS analyses (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        emotion    TEXT NOT NULL,
        confidence REAL NOT NULL,
        filename   TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """)
    # Migration pour les DBs existantes
    cols = [r[1] for r in db.execute("PRAGMA table_info(users)").fetchall()]
    for col, typ in [
        ("birthdate","TEXT"),("gender","TEXT"),("country","TEXT"),
        ("city","TEXT"),("profession","TEXT"),("avatar_path","TEXT"),
        ("language","TEXT DEFAULT 'fr'"),
    ]:
        if col not in cols:
            db.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
    db.commit()
    db.close()

init_db()

# ── Helpers ───────────────────────────────────
def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def make_token(user_id, email):
    exp = datetime.datetime.utcnow() + datetime.timedelta(days=7)
    return jwt.encode({"sub": str(user_id), "email": email, "exp": exp},
                      SECRET_KEY, algorithm=ALGORITHM)

def verify_token(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except Exception:
        raise HTTPException(401, "Token invalide ou expiré")

def gen_code():    return str(random.randint(100000, 999999))
def code_expiry(): return (datetime.datetime.utcnow() + datetime.timedelta(minutes=10)).isoformat()

def calc_age(birthdate_str):
    if not birthdate_str: return None
    try:
        bd    = datetime.date.fromisoformat(birthdate_str)
        today = datetime.date.today()
        return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    except: return None

def user_public(row):
    d = dict(row)
    for k in ("password_hash","email_code","phone_code","code_expires"):
        d.pop(k, None)
    d["age"] = calc_age(d.get("birthdate"))
    if d.get("avatar_path") and os.path.exists(d["avatar_path"]):
        with open(d["avatar_path"], "rb") as f:
            ext = d["avatar_path"].rsplit(".", 1)[-1]
            d["avatar_b64"] = f"data:image/{ext};base64," + base64.b64encode(f.read()).decode()
    else:
        d["avatar_b64"] = None
    return d

# ── Email ─────────────────────────────────────
def send_email_code(email: str, code: str, fullname: str = ""):
    if not MAIL_OK:
        print(f"📧 [DEV] Code email pour {email} : {code}")
        return code

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "🎤 SER Platform — Code de vérification"
        msg["From"]    = GMAIL_USER
        msg["To"]      = email

        html = f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:20px;background:#0a0a0f;font-family:Arial,sans-serif">
  <div style="max-width:460px;margin:auto;background:#1a1a26;border-radius:16px;overflow:hidden;border:1px solid rgba(255,255,255,0.07)">
    <div style="background:linear-gradient(135deg,#7c6ff7,#4facfe);padding:28px;text-align:center">
      <h1 style="margin:0;color:#fff;font-size:22px;letter-spacing:-0.5px">🎤 SER Platform</h1>
      <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:13px">Speech Emotion Recognition</p>
    </div>
    <div style="padding:28px">
      <p style="color:#f0eeff;font-size:15px;margin:0 0 8px">Bonjour <b>{fullname}</b>,</p>
      <p style="color:#7a7a9a;font-size:13px;margin:0 0 20px">
        Voici votre code de vérification pour activer votre compte SER Platform :
      </p>
      <div style="background:#0a0a0f;border-radius:12px;padding:22px;text-align:center;
                  letter-spacing:14px;font-size:38px;font-weight:700;color:#7c6ff7;
                  border:1px solid rgba(124,111,247,0.3)">
        {code}
      </div>
      <p style="color:#7a7a9a;font-size:12px;margin:18px 0 6px">
        ⏱ Ce code expire dans <b style="color:#a99ff5">10 minutes</b>.
      </p>
      <p style="color:#7a7a9a;font-size:12px;margin:0">
        Si vous n'avez pas créé de compte, ignorez cet email.
      </p>
    </div>
    <div style="padding:16px;text-align:center;border-top:1px solid rgba(255,255,255,0.07)">
      <p style="color:#555;font-size:11px;margin:0">SER Platform — Projet pluridisciplinaire S8</p>
    </div>
  </div>
</body>
</html>"""
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, email, msg.as_string())
        print(f"✅ Email envoyé à {email}")
    except Exception as e:
        print(f"❌ Erreur email: {e}")
    return code

# ── SMS ───────────────────────────────────────
def send_sms_code(phone: str, code: str):
    if not SMS_OK:
        print(f"📱 [DEV] Code SMS pour {phone} : {code}")
        return code
    try:
        client = TwilioClient(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(
            body=f"🎤 SER Platform\nCode de vérification : {code}\nValable 10 minutes.",
            from_=TWILIO_FROM,
            to=phone
        )
        print(f"✅ SMS envoyé à {phone}")
    except Exception as e:
        print(f"❌ Erreur SMS: {e}")
    return code

# ── Schemas ───────────────────────────────────
class RegisterSchema(BaseModel):
    fullname:   str
    email:      str
    phone:      Optional[str] = None
    password:   str
    birthdate:  Optional[str] = None
    gender:     Optional[str] = None
    country:    Optional[str] = None
    city:       Optional[str] = None
    profession: Optional[str] = None
    language:   Optional[str] = "fr"

class LoginSchema(BaseModel):
    email:    str
    password: str

class VerifyEmailSchema(BaseModel):
    email: str
    code:  str

class VerifyPhoneSchema(BaseModel):
    phone: str
    code:  str

class UpdateProfileSchema(BaseModel):
    fullname:   Optional[str] = None
    birthdate:  Optional[str] = None
    gender:     Optional[str] = None
    country:    Optional[str] = None
    city:       Optional[str] = None
    profession: Optional[str] = None
    language:   Optional[str] = None
    phone:      Optional[str] = None

class AnalysisSchema(BaseModel):
    emotion:    str
    confidence: float
    filename:   Optional[str] = None

# ── Auth routes ───────────────────────────────
@app.post("/auth/register")
def register(data: RegisterSchema):
    if len(data.password) < 6:
        raise HTTPException(400, "Mot de passe trop court (min 6 caractères)")
    if not re.match(r"[^@]+@[^@]+\.[^@]+", data.email):
        raise HTTPException(400, "Email invalide")
    db = get_db()
    if db.execute("SELECT id FROM users WHERE email=?", (data.email,)).fetchone():
        db.close()
        raise HTTPException(400, "Email déjà utilisé")
    code = gen_code(); expires = code_expiry()
    db.execute("""INSERT INTO users
        (fullname,email,phone,password_hash,birthdate,gender,
         country,city,profession,language,email_code,code_expires)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (data.fullname, data.email, data.phone,
         hash_password(data.password), data.birthdate, data.gender,
         data.country, data.city, data.profession,
         data.language or "fr", code, expires))
    db.commit(); db.close()
    send_email_code(data.email, code, data.fullname)
    # En dev, on renvoie le code pour faciliter les tests
    dev_info = {} if MAIL_OK else {"dev_code": code}
    return {"message": "Compte créé. Vérifiez votre email.", **dev_info}

@app.post("/auth/verify-email")
def verify_email(data: VerifyEmailSchema):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=?", (data.email,)).fetchone()
    if not user:
        db.close(); raise HTTPException(404, "Utilisateur introuvable")
    if user["email_verified"]:
        db.close(); return {"message": "Email déjà vérifié"}
    if user["email_code"] != data.code:
        db.close(); raise HTTPException(400, "Code incorrect")
    if datetime.datetime.utcnow().isoformat() > user["code_expires"]:
        db.close(); raise HTTPException(400, "Code expiré — demandez un nouveau")
    db.execute("UPDATE users SET email_verified=1, email_code=NULL WHERE email=?", (data.email,))
    db.commit()
    token  = make_token(user["id"], user["email"])
    result = user_public(db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone())
    db.close()
    return {"message": "Email vérifié!", "token": token, "user": result}

@app.post("/auth/resend-code")
def resend_code(data: dict):
    email = data.get("email","")
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user:
        db.close(); raise HTTPException(404, "Email introuvable")
    code = gen_code(); expires = code_expiry()
    db.execute("UPDATE users SET email_code=?, code_expires=? WHERE email=?",
               (code, expires, email))
    db.commit(); db.close()
    send_email_code(email, code, user["fullname"])
    dev_info = {} if MAIL_OK else {"dev_code": code}
    return {"message": "Code renvoyé", **dev_info}

@app.post("/auth/get-email-code")
def get_email_code(data: dict):
    """Génère et sauvegarde le code, le renvoie au frontend pour envoi via EmailJS."""
    email = data.get("email", "")
    if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        raise HTTPException(400, "Email invalide")
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user:
        db.close(); raise HTTPException(404, "Email introuvable")
    code = gen_code(); expires = code_expiry()
    db.execute("UPDATE users SET email_code=?, code_expires=? WHERE email=?",
               (code, expires, email))
    db.commit(); db.close()
    return {"code": code, "fullname": user["fullname"]}

@app.post("/auth/login")
def login(data: LoginSchema):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=?", (data.email,)).fetchone()
    if not user or user["password_hash"] != hash_password(data.password):
        db.close(); raise HTTPException(401, "Email ou mot de passe incorrect")
    if not user["email_verified"]:
        db.close(); raise HTTPException(403, "Email non vérifié — vérifiez votre boîte mail")
    db.execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (user["id"],))
    db.commit()
    token  = make_token(user["id"], user["email"])
    result = user_public(db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone())
    db.close()
    return {"token": token, "user": result}

@app.get("/auth/me")
def me(user_id: int = Depends(verify_token)):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    db.close()
    if not user: raise HTTPException(404, "Introuvable")
    return user_public(user)

@app.put("/auth/profile")
def update_profile(data: UpdateProfileSchema, user_id: int = Depends(verify_token)):
    db = get_db()
    fields, vals = [], []
    for field, val in data.dict(exclude_none=True).items():
        fields.append(f"{field}=?"); vals.append(val)
    if fields:
        vals.append(user_id)
        db.execute(f"UPDATE users SET {', '.join(fields)} WHERE id=?", vals)
        db.commit()
    result = user_public(db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())
    db.close()
    return result

@app.post("/auth/avatar")
async def upload_avatar(file: UploadFile = File(...),
                        user_id: int = Depends(verify_token)):
    ext = (file.filename or "avatar.jpg").rsplit(".", 1)[-1].lower()
    if ext not in ["jpg","jpeg","png","gif","webp"]:
        raise HTTPException(400, "Format non supporté (jpg/png/gif/webp)")
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(400, "Fichier trop grand (max 2 MB)")
    path = os.path.join(AVATAR_DIR, f"user_{user_id}.{ext}")
    with open(path, "wb") as f: f.write(content)
    db = get_db()
    db.execute("UPDATE users SET avatar_path=? WHERE id=?", (path, user_id))
    db.commit(); db.close()
    b64 = f"data:image/{ext};base64," + base64.b64encode(content).decode()
    return {"message": "Avatar mis à jour", "avatar_b64": b64}

@app.post("/auth/send-phone-code")
def send_phone_code(user_id: int = Depends(verify_token)):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user or not user["phone"]:
        db.close(); raise HTTPException(400, "Numéro de téléphone non renseigné")
    code = gen_code(); expires = code_expiry()
    db.execute("UPDATE users SET phone_code=?, code_expires=? WHERE id=?",
               (code, expires, user_id))
    db.commit(); db.close()
    send_sms_code(user["phone"], code)
    dev_info = {} if SMS_OK else {"dev_code": code}
    return {"message": "Code SMS envoyé", **dev_info}

@app.post("/auth/verify-phone")
def verify_phone(data: VerifyPhoneSchema,
                 user_id: int = Depends(verify_token)):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        db.close(); raise HTTPException(404, "Introuvable")
    if user["phone_code"] != data.code:
        db.close(); raise HTTPException(400, "Code incorrect")
    if datetime.datetime.utcnow().isoformat() > user["code_expires"]:
        db.close(); raise HTTPException(400, "Code expiré")
    db.execute("UPDATE users SET phone_verified=1, phone_code=NULL, phone=? WHERE id=?",
               (data.phone, user_id))
    db.commit(); db.close()
    return {"message": "Téléphone vérifié!"}

# ── Analyses ──────────────────────────────────
@app.post("/analyses/save")
def save_analysis(data: AnalysisSchema,
                  user_id: int = Depends(verify_token)):
    db = get_db()
    db.execute("INSERT INTO analyses (user_id,emotion,confidence,filename) VALUES (?,?,?,?)",
               (user_id, data.emotion, data.confidence, data.filename))
    db.commit(); db.close()
    return {"message": "Analyse sauvegardée"}

@app.get("/analyses/history")
def get_history(user_id: int = Depends(verify_token)):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM analyses WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (user_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.get("/analyses/stats")
def get_stats(user_id: int = Depends(verify_token)):
    db        = get_db()
    total     = db.execute("SELECT COUNT(*) as c FROM analyses WHERE user_id=?",
                           (user_id,)).fetchone()["c"]
    week_ago  = (datetime.datetime.utcnow() - datetime.timedelta(days=7)).isoformat()
    month_ago = (datetime.datetime.utcnow() - datetime.timedelta(days=30)).isoformat()
    week_rows  = db.execute(
        "SELECT emotion,COUNT(*) as c FROM analyses WHERE user_id=? AND created_at>=? GROUP BY emotion",
        (user_id, week_ago)).fetchall()
    month_rows = db.execute(
        "SELECT emotion,COUNT(*) as c FROM analyses WHERE user_id=? AND created_at>=? GROUP BY emotion",
        (user_id, month_ago)).fetchall()
    daily      = db.execute(
        "SELECT date(created_at) as day,COUNT(*) as c FROM analyses WHERE user_id=? AND created_at>=? GROUP BY day ORDER BY day",
        (user_id, week_ago)).fetchall()
    top        = db.execute(
        "SELECT emotion,COUNT(*) as c FROM analyses WHERE user_id=? GROUP BY emotion ORDER BY c DESC LIMIT 1",
        (user_id,)).fetchone()
    db.close()
    return {
        "total":       total,
        "top_emotion": dict(top) if top else None,
        "week":        {r["emotion"]: r["c"] for r in week_rows},
        "month":       {r["emotion"]: r["c"] for r in month_rows},
        "daily":       [dict(d) for d in daily],
    }

@app.get("/")
def root():
    return {"status": "SER Auth API ✅",
            "email_service": "Gmail SMTP" if MAIL_OK else "DEV mode",
            "sms_service":   "Twilio"     if SMS_OK  else "DEV mode"}