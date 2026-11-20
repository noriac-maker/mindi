import os, json, sqlite3, secrets, hashlib, hmac, csv, io, time, threading, logging
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import joblib

import sheets
import mailer
import chatbot
import survey as sv
from insights import action_plan, student_tips, suggested_message

log = logging.getLogger("mindreset")
logging.basicConfig(level=logging.INFO)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("MINDRESET_DB", os.path.join(APP_DIR, "mindreset.db"))
MODEL_PATH = os.getenv("MINDRESET_MODEL", os.path.join(APP_DIR, "mindreset_modelo_prototipo.joblib"))
TZ = ZoneInfo(os.getenv("MINDRESET_TZ", "America/Lima"))
TOKEN_TTL = 12 * 3600
TERMS_VERSION = "2026-11-19"
DEFAULT_NOTIFY = "class,work,rest,study,deadline,exam,sleep,other"
SYNC_INTERVAL = float(os.getenv("MINDRESET_SYNC_INTERVAL", "10"))

MODEL_BUNDLE = None
MODEL_ERROR = None
try:
    MODEL_BUNDLE = joblib.load(MODEL_PATH)
except Exception as exc:  # el modelo es imprescindible: se informa en /health y al evaluar
    MODEL_ERROR = str(exc)

security = HTTPBearer(auto_error=False)


# ------------------------------------------------------------------ utilidades
def now_dt():
    return datetime.now(timezone.utc)


def now_iso():
    return now_dt().isoformat()


def db():
    con = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180000).hex()
    return f"{salt}${digest}"


def verify_password(password, encoded):
    try:
        salt, digest = encoded.split("$", 1)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180000).hex()
        return hmac.compare_digest(candidate, digest)
    except Exception:
        return False


def local_date(iso):
    return datetime.fromisoformat(iso).astimezone(TZ).date()


def csv_safe(v):
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


# ---------------------------------------------------------------------- esquema
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('student','psychologist','admin')),
  display_name TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES users(id),
  anxiety_level REAL NOT NULL,
  sleep_quality REAL NOT NULL,
  study_load REAL NOT NULL,
  predicted_class INTEGER NOT NULL,
  probabilities TEXT NOT NULL,
  alert_level TEXT NOT NULL,
  notes TEXT DEFAULT '',
  reviewed INTEGER NOT NULL DEFAULT 0,
  reviewed_by INTEGER REFERENCES users(id),
  reviewed_at TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'other',
  start_at TEXT NOT NULL, end_at TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT 'manual', plan_id TEXT NOT NULL DEFAULT '',
  notified INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
  rev INTEGER NOT NULL DEFAULT 0, synced INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES users(id), checkin_id INTEGER,
  created_at TEXT NOT NULL, level TEXT NOT NULL, label TEXT NOT NULL,
  psych_report TEXT NOT NULL, student_summary TEXT NOT NULL,
  qa TEXT NOT NULL DEFAULT '[]', recommendations TEXT NOT NULL DEFAULT '[]', source TEXT NOT NULL DEFAULT 'basic',
  rev INTEGER NOT NULL DEFAULT 0, synced INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  author_id INTEGER NOT NULL REFERENCES users(id), category TEXT NOT NULL,
  title TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL, hidden INTEGER NOT NULL DEFAULT 0,
  rev INTEGER NOT NULL DEFAULT 0, synced INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS comments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id INTEGER NOT NULL REFERENCES posts(id), author_id INTEGER NOT NULL REFERENCES users(id),
  body TEXT NOT NULL, created_at TEXT NOT NULL, hidden INTEGER NOT NULL DEFAULT 0,
  rev INTEGER NOT NULL DEFAULT 0, synced INTEGER NOT NULL DEFAULT 0
);
"""
# Columnas añadidas en v2; se agregan automáticamente a bases creadas con la v1.
EXTRA_COLUMNS = {
    "users": {"ciclo": "INTEGER", "carrera": "TEXT DEFAULT ''", "consent_at": "TEXT", "synced": "INTEGER NOT NULL DEFAULT 0",
              "rev": "INTEGER NOT NULL DEFAULT 0", "email": "TEXT NOT NULL DEFAULT ''", "email_verified": "INTEGER NOT NULL DEFAULT 0",
              "notify_email": "INTEGER NOT NULL DEFAULT 1", "notify_kinds": "TEXT NOT NULL DEFAULT ''", "alias": "TEXT",
              "avatar": "TEXT NOT NULL DEFAULT ''", "feed_token": "TEXT", "consent_version": "TEXT NOT NULL DEFAULT ''"},
    "checkins": {"answers": "TEXT NOT NULL DEFAULT '{}'", "psych_note": "TEXT NOT NULL DEFAULT ''",
                 "wants_contact": "TEXT NOT NULL DEFAULT ''", "rev": "INTEGER NOT NULL DEFAULT 0",
                 "model_class": "INTEGER NOT NULL DEFAULT -1", "signals": "TEXT NOT NULL DEFAULT ''",
                 "synced": "INTEGER NOT NULL DEFAULT 0"},
}
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_checkins_created ON checkins(created_at);
CREATE INDEX IF NOT EXISTS idx_checkins_alert ON checkins(alert_level, reviewed);
CREATE INDEX IF NOT EXISTS idx_checkins_student ON checkins(student_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id, start_at);
CREATE INDEX IF NOT EXISTS idx_events_notify ON events(notified, start_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_alias ON users(lower(alias)) WHERE alias IS NOT NULL;
"""


def migrate(con):
    con.executescript(SCHEMA)
    for table, cols in EXTRA_COLUMNS.items():
        have = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        for name, decl in cols.items():
            if name not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    con.executescript(INDEXES)
    con.commit()


# ------------------------------------------------------------------------ modelo
LEVEL_ORDER = {"alto": 0, "medio": 1, "bajo": 2}


def run_model(features):
    if MODEL_BUNDLE is None:
        raise HTTPException(status_code=503, detail="No se pudo cargar el modelo ML. Verifica el archivo .joblib y sus versiones.")
    model = MODEL_BUNDLE.get("model", MODEL_BUNDLE)
    names = MODEL_BUNDLE.get("features", list(sv.FEATURES))
    try:
        import pandas as pd
        frame = pd.DataFrame([{n: features[n] for n in names}], columns=names)
        pred = int(model.predict(frame)[0])
        proba = model.predict_proba(frame)[0].tolist() if hasattr(model, "predict_proba") else []
        classes = list(getattr(model, "classes_", [0, 1, 2]))
        prob_map = {str(int(c)): float(p) for c, p in zip(classes, proba)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al ejecutar el modelo: {exc}")
    p_ang = prob_map.get("2", 0.0)
    if pred == 2 or p_ang >= 0.60:
        alert = "alto"
    elif pred == 1 or p_ang >= 0.30:
        alert = "medio"
    else:
        alert = "bajo"
    return pred, prob_map, alert


def score_answers(answers):
    """Modelo + capa de señales. predicted_class/alert ya incluyen el ajuste; model_class conserva la salida cruda."""
    feats = sv.answers_to_features(answers)
    raw, probs, model_alert = run_model(feats)
    floor, reasons = sv.signal_floor(answers)
    raised = LEVEL_ORDER[floor] < LEVEL_ORDER[model_alert]
    alert = floor if raised else model_alert
    final = max(raw, sv.FLOOR_TO_CLASS[alert])
    return {"features": feats, "model_class": raw, "predicted_class": final, "probs": probs, "alert": alert,
            "signals": reasons if raised else []}


def shape_checkin(r, include_note=True):
    """sqlite Row -> dict listo para la API."""
    answers = json.loads(r["answers"] or "{}")
    probs = json.loads(r["probabilities"] or "{}")
    d = {
        "id": r["id"],
        "created_at": r["created_at"],
        "predicted_class": r["predicted_class"],
        "label": sv.STRESS_LABELS.get(r["predicted_class"], f"Clase {r['predicted_class']}"),
        "description": sv.STRESS_DESCRIPTIONS.get(r["predicted_class"], ""),
        "alert_level": r["alert_level"],
        "model_label": sv.STRESS_LABELS.get(r["model_class"]) if r["model_class"] >= 0 else None,
        "adjusted": r["model_class"] >= 0 and bool(r["signals"]),
        "signals": [x for x in (r["signals"] or "").split("|") if x],
        "probabilities": probs,
        "features": {"anxiety_level": r["anxiety_level"], "sleep_quality": r["sleep_quality"], "study_load": r["study_load"]},
        "answers": answers,
        "answers_readable": sv.readable_answers(answers) if answers else [],
        "wants_contact": answers.get("wants_contact") == "c_yes" or r["wants_contact"] == "yes",
        "reviewed": bool(r["reviewed"]),
        "reviewed_at": r["reviewed_at"],
    }
    if include_note:
        d["psych_note"] = r["psych_note"]
    return d


# --------------------------------------------------------------- sync con Sheets
SYNC_STATE = {"last_ok": None, "last_error": None}
SYNC_WAKE = threading.Event()
SYNC_DELETED = []   # [(hoja, id)] filas a borrar en la hoja


def user_row(u, _=None):
    return {"id": u["id"], "usuario": u["username"], "nombre": u["display_name"], "ciclo": u["ciclo"] if u["ciclo"] is not None else "",
            "carrera": u["carrera"] or "", "rol": u["role"], "activo": u["active"], "password_hash": u["password_hash"],
            "consentimiento": u["consent_at"] or "", "creado": u["created_at"], "email": u["email"], "email_verificado": u["email_verified"],
            "notificar": u["notify_email"], "tipos_notificacion": u["notify_kinds"], "alias": u["alias"] or "", "avatar": u["avatar"],
            "version_consentimiento": u["consent_version"]}


def checkin_row(c, u):
    ans = json.loads(c["answers"] or "{}")

    def lab(qid):
        o = sv.option(qid, ans.get(qid)) if ans.get(qid) else None
        return o["label"] if o else ""

    probs = json.loads(c["probabilities"] or "{}")
    return {"id": c["id"], "fecha": c["created_at"], "id_estudiante": c["student_id"], "estudiante": u["display_name"],
            "ciclo": u["ciclo"] if u["ciclo"] is not None else "", "carrera": u["carrera"] or "",
            "resp_ansiedad": lab("anxiety"), "resp_horas_sueno": lab("sleep_hours"), "resp_calidad_sueno": lab("sleep_quality"),
            "resp_carga_estudio": lab("study_load"), "resp_estresor": lab("stressor"), "resp_contacto": lab("wants_contact"),
            "ansiedad_0_21": c["anxiety_level"], "calidad_sueno_1_5": c["sleep_quality"], "carga_estudio_1_10": c["study_load"],
            "nivel_estres": sv.STRESS_LABELS.get(c["predicted_class"], ""),
            "prob_sin_estres": round(probs.get("0", 0), 4), "prob_eustres": round(probs.get("1", 0), 4),
            "prob_angustia": round(probs.get("2", 0), 4), "alerta": c["alert_level"],
            "revisado": c["reviewed"], "nota_psicologia": c["psych_note"], "fecha_revision": c["reviewed_at"] or "",
            "respuestas_json": c["answers"], "clase": c["predicted_class"],
            "clase_modelo": c["model_class"], "ajuste_respuestas": (c["signals"] or "").replace("|", "; ")}


def event_row(e, _=None):
    return {"id": e["id"], "id_estudiante": e["user_id"], "titulo": e["title"], "tipo": e["kind"], "inicio": e["start_at"], "fin": e["end_at"],
            "notas": e["notes"], "origen": e["source"], "plan_id": e["plan_id"], "notificado": e["notified"], "creado": e["created_at"]}


def report_row(r, u):
    return {"id": r["id"], "fecha": r["created_at"], "id_estudiante": r["student_id"], "estudiante": u["display_name"],
            "ciclo": u["ciclo"] if u["ciclo"] is not None else "", "nivel_estres": r["label"], "atencion": r["level"],
            "informe_psicologia": r["psych_report"], "resumen_estudiante": r["student_summary"], "preguntas_json": r["qa"],
            "recomendaciones_json": r["recommendations"], "fuente": r["source"], "id_chequeo": r["checkin_id"] or ""}


def post_row(p, owners):
    return {"id": p["id"], "id_autor": p["author_id"], "alias": (owners.get(p["author_id"]) or {"alias": ""})["alias"] or "", "categoria": p["category"],
            "titulo": p["title"], "texto": p["body"], "fecha": p["created_at"], "oculto": p["hidden"]}


def comment_row(c, owners):
    return {"id": c["id"], "id_publicacion": c["post_id"], "id_autor": c["author_id"], "alias": (owners.get(c["author_id"]) or {"alias": ""})["alias"] or "",
            "texto": c["body"], "fecha": c["created_at"], "oculto": c["hidden"]}


SYNC_TABLES = [  # tabla local, hoja, constructor de fila (fila, usuarios)
    ("users", "Usuarios", lambda r, U: user_row(r)),
    ("checkins", "Encuestas", lambda r, U: checkin_row(r, U[r["student_id"]])),
    ("events", "Calendario", lambda r, U: event_row(r)),
    ("reports", "Informes", lambda r, U: report_row(r, U[r["student_id"]])),
    ("posts", "Foro_Publicaciones", lambda r, U: post_row(r, U)),
    ("comments", "Foro_Comentarios", lambda r, U: comment_row(r, U)),
]


def pending_sync_count(con=None):
    own = con is None
    con = con or db()
    n = sum(con.execute(f"SELECT COUNT(*) FROM {t} WHERE synced=0").fetchone()[0] for t, _, _ in SYNC_TABLES) + len(SYNC_DELETED)
    if own:
        con.close()
    return n


def sync_once():
    """Envía a la hoja lo pendiente (altas, cambios y borrados). Devuelve cuántas filas quedan sin sincronizar."""
    con = db()
    try:
        owners = {u["id"]: u for u in con.execute("SELECT * FROM users")}
        for table, sheet, fn in SYNC_TABLES:
            rows = con.execute(f"SELECT * FROM {table} WHERE synced=0 ORDER BY id LIMIT 100").fetchall()
            if not rows:
                continue
            sheets.upsert(sheet, [fn(r, owners) for r in rows])
            # `rev` evita perder una edición ocurrida mientras se subía la fila
            con.executemany(f"UPDATE {table} SET synced=1 WHERE id=? AND rev=?", [(r["id"], r["rev"]) for r in rows])
            con.commit()
        while SYNC_DELETED:
            sheet, rid = SYNC_DELETED[0]
            sheets.call("delete", sheet=sheet, ids=[rid])
            SYNC_DELETED.pop(0)
        pending = pending_sync_count(con)
    finally:
        con.close()
    SYNC_STATE["last_ok"] = now_iso()
    SYNC_STATE["last_error"] = None
    return pending


def sync_loop():
    while True:
        SYNC_WAKE.wait(SYNC_INTERVAL)
        SYNC_WAKE.clear()
        try:
            while sync_once() > 0:
                pass
        except Exception as exc:
            SYNC_STATE["last_error"] = str(exc)[:300]
            log.warning("Sincronización con Google Sheets falló: %s", exc)
            time.sleep(min(30, SYNC_INTERVAL * 2))


def restore_from_sheets():
    """Inserta en la BD local lo que exista en la hoja y falte aquí. Devuelve (usuarios, encuestas) añadidos."""
    data = sheets.dump()
    con = db()
    added = {"users": 0, "checkins": 0}

    def to_int(x, default=None):
        try:
            return int(float(x))
        except (TypeError, ValueError):
            return default

    for r in data.get("Usuarios", []):
        uid = to_int(r.get("id"))
        if uid is None or con.execute("SELECT 1 FROM users WHERE id=? OR username=?", (uid, r.get("usuario"))).fetchone():
            continue
        alias = (r.get("alias") or "").strip() or None
        if alias and con.execute("SELECT 1 FROM users WHERE lower(alias)=lower(?)", (alias,)).fetchone():
            alias = None
        con.execute("""INSERT INTO users(id,username,password_hash,role,display_name,ciclo,carrera,consent_at,active,created_at,synced,email,email_verified,
                       notify_email,notify_kinds,alias,avatar,consent_version) VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?,?)""",
                    (uid, r["usuario"], r["password_hash"], r["rol"], r["nombre"], to_int(r.get("ciclo")), r.get("carrera", ""),
                     r.get("consentimiento") or None, to_int(r.get("activo"), 1), r.get("creado") or now_iso(), r.get("email", ""),
                     to_int(r.get("email_verificado"), 0), to_int(r.get("notificar"), 1), r.get("tipos_notificacion", ""), alias, r.get("avatar", ""),
                     r.get("version_consentimiento", "")))
        added["users"] += 1
    for r in data.get("Encuestas", []):
        cid, sid = to_int(r.get("id")), to_int(r.get("id_estudiante"))
        if cid is None or sid is None or con.execute("SELECT 1 FROM checkins WHERE id=?", (cid,)).fetchone():
            continue
        if not con.execute("SELECT 1 FROM users WHERE id=?", (sid,)).fetchone():
            continue
        try:
            answers = json.loads(r.get("respuestas_json") or "{}")
            feats = sv.answers_to_features(answers) if answers else {
                "anxiety_level": float(r["ansiedad_0_21"]), "sleep_quality": float(r["calidad_sueno_1_5"]), "study_load": float(r["carga_estudio_1_10"])}
        except Exception:
            continue
        probs = {"0": float(r.get("prob_sin_estres") or 0), "1": float(r.get("prob_eustres") or 0), "2": float(r.get("prob_angustia") or 0)}
        con.execute("""INSERT INTO checkins(id,student_id,anxiety_level,sleep_quality,study_load,predicted_class,model_class,signals,probabilities,
                       alert_level,answers,reviewed,reviewed_at,psych_note,created_at,synced) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                    (cid, sid, feats["anxiety_level"], feats["sleep_quality"], feats["study_load"], to_int(r.get("clase"), 0),
                     to_int(r.get("clase_modelo"), -1), "|".join(x.strip() for x in (r.get("ajuste_respuestas") or "").split(";") if x.strip()),
                     json.dumps(probs), r.get("alerta") or "bajo", json.dumps(answers), to_int(r.get("revisado"), 0),
                     r.get("fecha_revision") or None, r.get("nota_psicologia", ""), r["fecha"]))
        added["checkins"] += 1
    for r in data.get("Calendario", []):
        eid, uid = to_int(r.get("id")), to_int(r.get("id_estudiante"))
        if eid is None or uid is None or con.execute("SELECT 1 FROM events WHERE id=?", (eid,)).fetchone() or not con.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
            continue
        con.execute("""INSERT INTO events(id,user_id,title,kind,start_at,end_at,notes,source,plan_id,notified,created_at,synced) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)""",
                    (eid, uid, r.get("titulo", ""), r.get("tipo", "other"), r.get("inicio", ""), r.get("fin", ""), r.get("notas", ""), r.get("origen", "manual"),
                     r.get("plan_id", ""), to_int(r.get("notificado"), 0), r.get("creado") or now_iso()))
    for r in data.get("Informes", []):
        rid, sid = to_int(r.get("id")), to_int(r.get("id_estudiante"))
        if rid is None or sid is None or con.execute("SELECT 1 FROM reports WHERE id=?", (rid,)).fetchone() or not con.execute("SELECT 1 FROM users WHERE id=?", (sid,)).fetchone():
            continue
        con.execute("""INSERT INTO reports(id,student_id,checkin_id,created_at,level,label,psych_report,student_summary,qa,recommendations,source,synced)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,1)""",
                    (rid, sid, to_int(r.get("id_chequeo")), r.get("fecha") or now_iso(), r.get("atencion", "bajo"), r.get("nivel_estres", ""),
                     r.get("informe_psicologia", ""), r.get("resumen_estudiante", ""), r.get("preguntas_json") or "[]", r.get("recomendaciones_json") or "[]",
                     r.get("fuente", "basic")))
    for r in data.get("Foro_Publicaciones", []):
        pid, aid = to_int(r.get("id")), to_int(r.get("id_autor"))
        if pid is None or aid is None or con.execute("SELECT 1 FROM posts WHERE id=?", (pid,)).fetchone() or not con.execute("SELECT 1 FROM users WHERE id=?", (aid,)).fetchone():
            continue
        con.execute("INSERT INTO posts(id,author_id,category,title,body,created_at,hidden,synced) VALUES(?,?,?,?,?,?,?,1)",
                    (pid, aid, r.get("categoria", "Otros"), r.get("titulo", ""), r.get("texto", ""), r.get("fecha") or now_iso(), to_int(r.get("oculto"), 0)))
    for r in data.get("Foro_Comentarios", []):
        cid, pid, aid = to_int(r.get("id")), to_int(r.get("id_publicacion")), to_int(r.get("id_autor"))
        if None in (cid, pid, aid) or con.execute("SELECT 1 FROM comments WHERE id=?", (cid,)).fetchone() or not con.execute("SELECT 1 FROM posts WHERE id=?", (pid,)).fetchone() \
                or not con.execute("SELECT 1 FROM users WHERE id=?", (aid,)).fetchone():
            continue
        con.execute("INSERT INTO comments(id,post_id,author_id,body,created_at,hidden,synced) VALUES(?,?,?,?,?,?,1)",
                    (cid, pid, aid, r.get("texto", ""), r.get("fecha") or now_iso(), to_int(r.get("oculto"), 0)))
    con.commit()
    con.close()
    return added["users"], added["checkins"]


# ----------------------------------------------------------------------- datos demo
DEMO_STUDENT_PASSWORD = "MindReset2026!"
DEMO_STUDENTS = [
    # usuario, nombre, ciclo, carrera, [(días_atrás, ansiedad, horas, calidad_sueño, carga, estresor, contacto)]  (calidad y carga: 0–5)
    ("estudiante1", "Estudiante Demo", 5, "Ingeniería de Sistemas", []),
    ("demo.sofia", "Sofía Rojas Mendoza", 2, "Administración", [(12, 1, 2, 3, 2, "s_exams", "c_no"), (5, 1, 2, 4, 2, "s_none", "c_no")]),
    ("demo.diego", "Diego Paredes Flores", 7, "Ingeniería Civil", [(10, 2, 1, 2, 4, "s_tasks", "c_no"), (3, 3, 1, 1, 5, "s_tasks", "c_yes")]),
    ("demo.valeria", "Valeria Quispe Huamán", 4, "Enfermería", [(9, 2, 2, 3, 3, "s_time", "c_no"), (2, 1, 2, 4, 2, "s_exams", "c_maybe")]),
    ("demo.mateo", "Mateo Salazar Ríos", 9, "Derecho", [(8, 3, 0, 1, 5, "s_money", "c_yes"), (1, 3, 0, 0, 5, "s_money", "c_yes")]),
    ("demo.camila", "Camila Torres Vega", 3, "Arquitectura", [(7, 0, 2, 4, 1, "s_none", "c_no")]),
    ("demo.andres", "Andrés Cárdenas Luna", 6, "Ingeniería Industrial", [(11, 3, 1, 1, 5, "s_tasks", "c_no"), (6, 2, 1, 2, 4, "s_time", "c_no"), (2, 1, 2, 3, 3, "s_time", "c_no")]),
    ("demo.luciana", "Luciana Herrera Soto", 1, "Medicina Humana", [(4, 2, 1, 2, 4, "s_people", "c_maybe")]),
    ("demo.joaquin", "Joaquín Medina Paz", 8, "Contabilidad", []),
]


def seed_demo(con, with_checkins):
    demo = [("adminmindreset", "AdminMindReset2026!", "admin", "Administración MindReset")]
    names = ["Psicólogo Demo 1", "Psicóloga Demo 2", "Psicólogo Demo 3", "Psicóloga Demo 4", "Psicólogo Demo 5",
             "Psicóloga Demo 6", "Psicólogo Demo 7", "Psicóloga Demo 8", "Psicólogo Demo 9", "Psicóloga Demo 10"]
    demo += [(f"psicologo{i}", "PsicoDemo2026!", "psychologist", names[i - 1]) for i in range(1, 11)]
    for username, password, role, name in demo:
        con.execute("INSERT INTO users(username,password_hash,role,display_name,created_at) VALUES(?,?,?,?,?)",
                    (username, hash_password(password), role, name, now_iso()))
    for username, name, ciclo, carrera, entries in DEMO_STUDENTS:
        cur = con.execute("INSERT INTO users(username,password_hash,role,display_name,ciclo,carrera,consent_at,consent_version,notify_kinds,created_at) VALUES(?,?,'student',?,?,?,?,?,?,?)",
                          (username, hash_password(DEMO_STUDENT_PASSWORD), name, ciclo, carrera, now_iso(), TERMS_VERSION, DEFAULT_NOTIFY, now_iso()))
        if not (with_checkins and MODEL_BUNDLE is not None):
            continue
        for days_ago, a, h, q, l, stressor, contact in entries:
            answers = {"anxiety": f"a{a}", "sleep_hours": f"h{h}", "sleep_quality": f"q{q}", "study_load": f"l{l}",
                       "stressor": stressor, "wants_contact": contact}
            sc = score_answers(answers)
            feats = sc["features"]
            when = (now_dt() - timedelta(days=days_ago, hours=days_ago % 5)).isoformat()
            con.execute("""INSERT INTO checkins(student_id,anxiety_level,sleep_quality,study_load,predicted_class,model_class,signals,probabilities,
                           alert_level,answers,wants_contact,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (cur.lastrowid, feats["anxiety_level"], feats["sleep_quality"], feats["study_load"], sc["predicted_class"], sc["model_class"],
                         "|".join(sc["signals"]), json.dumps(sc["probs"]), sc["alert"], json.dumps(answers),
                         "yes" if contact == "c_yes" else "", when))
    if with_checkins and MODEL_BUNDLE is not None:
        seed_demo_extras(con)


DEMO_ALIASES = {"demo.sofia": ("Luna Serena", "p2"), "demo.diego": ("Nube Tranquila", "p3"), "demo.valeria": ("Brote Verde", "p5"),
                "demo.camila": ("Gatito Zen", "p1"), "demo.andres": ("Oso Calmo", "p4")}
DEMO_POSTS = [
    ("demo.andres", "Estudios", "¿Cómo organizan sus semanas de parciales?", "Tengo tres parciales juntos y no sé por dónde empezar. Yo estoy probando bloques de 25 minutos. ¿Qué les funciona a ustedes?",
     [("demo.valeria", "A mí me ayudó escribir los temas en tarjetas y repasar uno por día. ¡Ánimo!"), ("demo.sofia", "Bloques de 25/5 también me funcionan. Y dormir bien antes del examen.")]),
    ("demo.sofia", "Sueño", "No logro dormir antes de las 2 a. m.", "Llevo dos semanas durmiendo muy tarde por las tareas. Me levanto cansada. ¿Algún consejo que no sea «duerme temprano»? 😅",
     [("demo.camila", "Apagar el celular 30 minutos antes y anotar pendientes en papel me ayudó bastante."), ("demo.diego", "A mí me sirvió la respiración 4-6 en la cama.")]),
    ("demo.camila", "Consejos", "Una pausa que me cambió el día", "Salir 10 minutos a caminar sin celular entre clases me bajó la ansiedad. Se los recomiendo.", [("demo.andres", "Voy a probarlo mañana, gracias por compartir.")]),
    ("demo.valeria", "Ánimo", "Hoy fue un día difícil", "Sentí que no llegaba a nada. Escribirlo aquí ya me alivia un poco. Gracias por leer.",
     [("demo.sofia", "Te leo. Mañana puede ir mejor, y hoy ya hiciste bastante. 💜"), ("demo.camila", "No estás sola, a muchos nos pasa en esta época.")]),
]


def seed_demo_extras(con):
    import deep
    import planner as pl
    ids = {r["username"]: r["id"] for r in con.execute("SELECT id, username FROM users")}
    for uname, (alias, avatar) in DEMO_ALIASES.items():
        con.execute("UPDATE users SET alias=?, avatar=? WHERE id=?", (alias, avatar, ids[uname]))
    for i, (author, cat, title, body, comments) in enumerate(DEMO_POSTS):
        when = (now_dt() - timedelta(days=4 - i, hours=3)).isoformat()
        cur = con.execute("INSERT INTO posts(author_id,category,title,body,created_at) VALUES(?,?,?,?,?)", (ids[author], cat, title, body, when))
        for j, (ca, ctext) in enumerate(comments):
            con.execute("INSERT INTO comments(post_id,author_id,body,created_at) VALUES(?,?,?,?)",
                        (cur.lastrowid, ids[ca], ctext, (now_dt() - timedelta(days=3 - i, hours=j)).isoformat()))
    # horario de ejemplo para la cuenta demo de estudiante
    start = datetime.now(TZ).date() + timedelta(days=1)
    plan = pl.generate_plan([{"title": "Clases", "kind": "class", "days": [0, 1, 2, 3, 4], "start": "08:00", "end": "14:00"}],
                            [{"title": "Informe de estadística", "due": (start + timedelta(days=6)).isoformat(), "hours": 6, "kind": "task"},
                             {"title": "Examen de cálculo", "due": (start + timedelta(days=9)).isoformat(), "hours": 5, "kind": "exam"}],
                            {"transport_min": 40}, start)
    for e in plan["events"]:
        con.execute("INSERT INTO events(user_id,title,kind,start_at,end_at,notes,source,plan_id,created_at) VALUES(?,?,?,?,?,?,'plan','demo',?)",
                    (ids["estudiante1"], e["title"], e["kind"], e["start_at"], e["end_at"], e["notes"], now_iso()))
    # informes de ejemplo para dos estudiantes
    seeds = {"demo.diego": [("sleep_pre", "worry"), ("task_hard", "amount"), ("support", "friends")],
             "demo.mateo": [("work_hours", "w3"), ("sleep_pre", "late_study"), ("support", "nobody")]}
    for uname, picks in seeds.items():
        last = con.execute("SELECT * FROM checkins WHERE student_id=? ORDER BY id DESC LIMIT 1", (ids[uname],)).fetchone()
        prev = con.execute("SELECT * FROM checkins WHERE student_id=? ORDER BY id DESC LIMIT 1 OFFSET 1", (ids[uname],)).fetchone()
        if not last:
            continue
        c = shape_checkin(last)
        qa = []
        for topic, tag in picks:
            title, _, opts = deep.QB[topic]
            qa.append({"qid": topic, "question": title, "answer": next(o[1] for o in opts if o[0] == tag), "tag": tag})
        res = deep._rule_analysis(uname.split(".")[1].capitalize(), c["answers"], c["features"], c["label"], c["alert_level"], qa,
                                  deep.schedule_summary([], datetime.now(TZ).date()), sv.STRESS_LABELS[prev["predicted_class"]] if prev else None)
        con.execute("""INSERT INTO reports(student_id,checkin_id,created_at,level,label,psych_report,student_summary,qa,recommendations,source)
                       VALUES(?,?,?,?,?,?,?,?,?,'basic')""",
                    (ids[uname], last["id"], (now_dt() - timedelta(days=1)).isoformat(), c["alert_level"], c["label"], res["psych_report"],
                     res["student_summary"], json.dumps(qa, ensure_ascii=False), json.dumps(res["recommendations"], ensure_ascii=False)))


def init_db():
    con = db()
    migrate(con)
    if con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        restored = False
        if sheets.enabled():
            con.close()
            try:
                u, c = restore_from_sheets()
                restored = u > 0
                log.info("Restauradas desde Google Sheets: %s usuarios, %s encuestas", u, c)
            except Exception as exc:
                log.warning("No se pudo leer Google Sheets al iniciar: %s", exc)
            con = db()
        if not restored:
            # Con Sheets activo no se siembran encuestas de ejemplo para no ensuciar la hoja real.
            default_seed = "0" if sheets.enabled() else "1"
            seed_demo(con, with_checkins=os.getenv("MINDRESET_SEED_DEMO", default_seed) == "1")
    con.commit()
    con.close()


@asynccontextmanager
async def lifespan(app):
    init_db()
    if sheets.enabled():
        threading.Thread(target=sync_loop, daemon=True, name="sheets-sync").start()
        SYNC_WAKE.set()
        log.info("Sincronización con Google Sheets activada.")
    else:
        log.info("Google Sheets no configurado: se usa solo la base local.")
    if mailer.configured():
        import routes_calendar
        routes_calendar.start_reminders()
        log.info("Recordatorios por correo activados.")
    yield


app = FastAPI(title="MindReset API", version="2.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")

# ------------------------------------------------------------------------ sesiones
TOKENS = {}


def make_token(user):
    token = secrets.token_urlsafe(32)
    TOKENS[token] = {"id": user["id"], "exp": time.time() + TOKEN_TTL}
    return token


def current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    t = TOKENS.get(credentials.credentials) if credentials else None
    if not t or t["exp"] < time.time():
        if credentials:
            TOKENS.pop(credentials.credentials, None)
        raise HTTPException(status_code=401, detail="Inicia sesión para continuar.")
    con = db()
    user = con.execute("SELECT * FROM users WHERE id=? AND active=1", (t["id"],)).fetchone()
    con.close()
    if not user:
        raise HTTPException(status_code=401, detail="La cuenta no está activa.")
    return dict(user)


def require_roles(*roles):
    def dependency(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="No tienes permisos para esta función.")
        return user
    return dependency


def public_user(u, con=None):
    d = {"id": u["id"], "username": u["username"], "role": u["role"], "display_name": u["display_name"],
         "ciclo": u["ciclo"], "carrera": u["carrera"], "email": u.get("email") or "", "email_verified": bool(u.get("email_verified")),
         "notify_email": bool(u.get("notify_email", 1)), "notify_kinds": (u.get("notify_kinds") or DEFAULT_NOTIFY).split(","),
         "alias": u.get("alias"), "avatar": u.get("avatar") or ("p1" if u.get("alias") else ""),
         "mail_enabled": mailer.configured()}
    if u["role"] == "student":
        own = con or db()
        last = own.execute("SELECT created_at FROM checkins WHERE student_id=? ORDER BY id DESC LIMIT 1", (u["id"],)).fetchone()
        if con is None:
            own.close()
        d["checked_today"] = bool(last and local_date(last["created_at"]) == datetime.now(TZ).date())
        d["chat_mode"] = "gemini" if chatbot.gemini_available() else "basic"
    return d


# ---------------------------------------------------------------------- esquemas API
class LoginInput(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=200)


class RegisterInput(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(min_length=2, max_length=120)
    ciclo: int = Field(ge=1, le=12)
    carrera: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    consent_terms: bool
    consent_data: bool
    consent_visibility: bool
    consent_tool: bool
    notify_email: bool = True


class CheckinInput(BaseModel):
    answers: dict


class ReviewInput(BaseModel):
    reviewed: Optional[bool] = None
    psych_note: Optional[str] = Field(default=None, max_length=2000)


class ChatTurn(BaseModel):
    role: str = Field(max_length=10)
    text: str = Field(max_length=2000)


class ChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: List[ChatTurn] = Field(default_factory=list, max_length=30)
    offered: bool = False   # el cliente ya ofreció avisar a psicología en esta sesión


class CreateUserInput(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=200)
    display_name: str = Field(min_length=2, max_length=120)
    role: str = Field(pattern="^(student|psychologist)$")
    ciclo: Optional[int] = Field(default=None, ge=1, le=12)
    carrera: str = Field(default="", max_length=80)


# ------------------------------------------------------------------------ páginas
@app.get("/", response_class=HTMLResponse)
def home():
    with open(os.path.join(APP_DIR, "static", "index.html"), encoding="utf-8") as f:
        return f.read()


@app.get("/manifest.webmanifest")
def manifest():
    return JSONResponse({"name": "MindReset", "short_name": "MindReset", "start_url": "/", "display": "standalone",
                         "background_color": "#FFF9F0", "theme_color": "#6A3EC8",
                         "icons": [{"src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}]})


GEMINI_STATE = {"last_error": None}


@app.get("/health")
def health():
    info = {"status": "ok", "model_loaded": MODEL_BUNDLE is not None, "model_error": MODEL_ERROR,
            "model_name": (MODEL_BUNDLE or {}).get("model_name"), "features": (MODEL_BUNDLE or {}).get("features"),
            "chatbot": "gemini" if chatbot.gemini_available() else "basic",
            "gemini_model": chatbot.ACTIVE_MODEL["name"] or chatbot.GEMINI_MODEL,
            "gemini_last_error": GEMINI_STATE["last_error"]}
    info["google_sheets"] = {"enabled": sheets.enabled(), "last_ok": SYNC_STATE["last_ok"], "last_error": SYNC_STATE["last_error"],
                             "pending_rows": pending_sync_count() if sheets.enabled() else 0}
    info["mail"] = mailer.configured()
    info["show_demo"] = os.getenv("MINDRESET_HIDE_DEMO", "0") != "1"
    return info


# ---------------------------------------------------------------------------- auth
@app.post("/api/login")
def login(data: LoginInput):
    con = db()
    user = con.execute("SELECT * FROM users WHERE username=? AND active=1", (data.username.strip().lower(),)).fetchone()
    if not user or not verify_password(data.password, user["password_hash"]):
        con.close()
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")
    out = {"token": make_token(user), "user": public_user(dict(user), con)}
    con.close()
    return out


@app.post("/api/register")
def register(data: RegisterInput):
    if not (data.consent_terms and data.consent_data and data.consent_visibility and data.consent_tool):
        raise HTTPException(status_code=400, detail="Para crear tu cuenta debes aceptar los Términos y Condiciones y las cuatro autorizaciones.")
    username = data.username.strip().lower()
    con = db()
    try:
        cur = con.execute("""INSERT INTO users(username,password_hash,role,display_name,ciclo,carrera,consent_at,consent_version,email,notify_email,notify_kinds,created_at)
                             VALUES(?,?,'student',?,?,?,?,?,?,?,?,?)""",
                          (username, hash_password(data.password), data.display_name.strip(), data.ciclo, data.carrera.strip(), now_iso(), TERMS_VERSION,
                           data.email.strip().lower(), 1 if data.notify_email else 0, DEFAULT_NOTIFY, now_iso()))
        con.commit()
    except sqlite3.IntegrityError:
        con.close()
        raise HTTPException(status_code=409, detail="Ese nombre de usuario ya existe. Prueba con otro.")
    user = con.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    out = {"token": make_token(user), "user": public_user(dict(user), con)}
    con.close()
    SYNC_WAKE.set()
    return out


@app.post("/api/logout")
def logout(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if credentials:
        TOKENS.pop(credentials.credentials, None)
    return {"ok": True}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return public_user(user)


@app.get("/api/survey")
def get_survey(user=Depends(require_roles("student"))):
    return {"questions": sv.public_survey()}


# ---------------------------------------------------------------------- estudiante
def latest_checkin(con, student_id):
    r = con.execute("SELECT * FROM checkins WHERE student_id=? ORDER BY id DESC LIMIT 1", (student_id,)).fetchone()
    return shape_checkin(r, include_note=False) if r else None


@app.post("/api/checkins")
def create_checkin(data: CheckinInput, user=Depends(require_roles("student"))):
    answers, err = sv.validate_answers(data.answers)
    if err:
        raise HTTPException(status_code=422, detail=err)
    sc = score_answers(answers)
    feats, pred, alert = sc["features"], sc["predicted_class"], sc["alert"]
    wants = "yes" if answers["wants_contact"] == "c_yes" else ""
    con = db()
    cur = con.execute("""INSERT INTO checkins(student_id,anxiety_level,sleep_quality,study_load,predicted_class,model_class,signals,probabilities,
                         alert_level,answers,wants_contact,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (user["id"], feats["anxiety_level"], feats["sleep_quality"], feats["study_load"], pred, sc["model_class"],
                       "|".join(sc["signals"]), json.dumps(sc["probs"]), alert, json.dumps(answers), wants, now_iso()))
    con.commit()
    row = con.execute("SELECT * FROM checkins WHERE id=?", (cur.lastrowid,)).fetchone()
    con.close()
    SYNC_WAKE.set()
    c = shape_checkin(row, include_note=False)
    return {"id": c["id"], "predicted_class": pred, "label": c["label"], "description": c["description"],
            "alert_level": alert, "tips": student_tips(c), "wants_contact": c["wants_contact"],
            "resources": chatbot.HELP_RESOURCES,
            "message": "Registro guardado. Este resultado es orientativo y no constituye un diagnóstico clínico."}


@app.get("/api/my-checkins")
def my_checkins(user=Depends(require_roles("student"))):
    con = db()
    rows = con.execute("SELECT * FROM checkins WHERE student_id=? ORDER BY id DESC LIMIT 30", (user["id"],)).fetchall()
    con.close()
    out = []
    for r in rows:
        c = shape_checkin(r, include_note=False)
        out.append({k: c[k] for k in ("id", "created_at", "predicted_class", "label", "description", "alert_level", "features", "answers_readable", "wants_contact")})
    return out


@app.post("/api/contact-request")
def contact_request(user=Depends(require_roles("student"))):
    """El estudiante pide, de forma explícita, que psicología lo contacte."""
    con = db()
    r = con.execute("SELECT id FROM checkins WHERE student_id=? ORDER BY id DESC LIMIT 1", (user["id"],)).fetchone()
    if not r:
        con.close()
        raise HTTPException(status_code=400, detail="Primero completa la encuesta.")
    con.execute("UPDATE checkins SET wants_contact='yes', reviewed=0, reviewed_at=NULL, rev=rev+1, synced=0 WHERE id=?", (r["id"],))
    con.commit()
    con.close()
    SYNC_WAKE.set()
    return {"ok": True, "message": "Listo. Avisamos al servicio de psicología para que te escriban."}


_chat_hits = defaultdict(deque)


@app.post("/api/chat")
def chat(data: ChatInput, user=Depends(require_roles("student"))):
    q = _chat_hits[user["id"]]
    now = time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= 15:
        raise HTTPException(status_code=429, detail="Vas muy rápido. Respira y vuelve a escribir en un momento.")
    q.append(now)

    msg = data.message.strip()
    if chatbot.is_crisis(msg):
        return {"reply": chatbot.CRISIS_REPLY, "suggestions": chatbot.CRISIS_SUGGESTIONS, "crisis": True,
                "source": "safety", "resources": chatbot.HELP_RESOURCES}

    import routes_student
    first = user["display_name"].split()[0]
    con = db()
    last = latest_checkin(con, user["id"])
    sigs, _, _ = routes_student.signals_for(con, user["id"])
    rep_row = con.execute("SELECT student_summary FROM reports WHERE student_id=? ORDER BY id DESC LIMIT 1", (user["id"],)).fetchone()
    con.close()
    history = [t.model_dump() for t in data.history]
    # Mindi detecta señales de decaimiento en ESTA conversación y se lo dice al estudiante; solo avisa a psicología si él lo acepta.
    user_texts = [t["text"] for t in history if t["role"] == "user"] + [msg]
    offer = (not data.offered) and chatbot.distress_hits(user_texts) >= 2
    extra = ""
    if sigs:
        extra += " Observaciones recientes (úsalas con tacto, sin alarmar): " + " ".join(x["student"] for x in sigs[:3])
    if rep_row:
        extra += " Resumen de su último chequeo profundo: " + rep_row["student_summary"]
    if offer:
        extra += " En esta conversación el estudiante ha mostrado señales de decaimiento: valida sus emociones con calidez."
    out = {"crisis": False, "offer_support": offer}
    if chatbot.gemini_available():
        try:
            reply, sugg = chatbot.gemini_reply(history, msg, chatbot.build_context(first, last, extra))
            GEMINI_STATE["last_error"] = None
            return {**out, "reply": reply, "suggestions": sugg, "source": "gemini"}
        except Exception as exc:  # el texto del estudiante nunca se guarda en logs
            GEMINI_STATE["last_error"] = (str(exc) or type(exc).__name__)[:200]
            log.warning("Gemini no disponible, uso modo básico: %s", type(exc).__name__)
    reply, sugg = chatbot.basic_reply(msg, first)
    return {**out, "reply": reply, "suggestions": sugg, "source": "basic"}


# ------------------------------------------------------------------- psicología
def students_overview(con):
    rows = con.execute("""
        SELECT u.id sid, u.display_name, u.username, u.ciclo, u.carrera,
               (SELECT COUNT(*) FROM checkins WHERE student_id=u.id) n,
               l.id cid, l.created_at, l.predicted_class, l.alert_level, l.reviewed, l.answers, l.wants_contact,
               (SELECT predicted_class FROM checkins WHERE student_id=u.id AND id<l.id ORDER BY id DESC LIMIT 1) prev_class
        FROM users u LEFT JOIN checkins l ON l.id=(SELECT MAX(id) FROM checkins WHERE student_id=u.id)
        WHERE u.role='student' AND u.active=1""").fetchall()
    out = []
    for r in rows:
        has = r["cid"] is not None
        answers = json.loads(r["answers"] or "{}") if has else {}
        wants = has and (answers.get("wants_contact") == "c_yes" or r["wants_contact"] == "yes")
        stressor = sv.option("stressor", answers["stressor"]) if answers.get("stressor") else None
        out.append({
            "student_id": r["sid"], "name": r["display_name"], "username": r["username"], "ciclo": r["ciclo"], "carrera": r["carrera"] or "",
            "n_checkins": r["n"], "checkin_id": r["cid"], "last_at": r["created_at"],
            "predicted_class": r["predicted_class"], "label": sv.STRESS_LABELS.get(r["predicted_class"]) if has else None,
            "alert_level": r["alert_level"], "reviewed": bool(r["reviewed"]) if has else None, "wants_contact": bool(wants),
            "trend": None if (not has or r["prev_class"] is None) else (r["predicted_class"] > r["prev_class"]) - (r["predicted_class"] < r["prev_class"]),
            "stressor": stressor["label"] if stressor else None,
        })

    def key(s):
        ts = datetime.fromisoformat(s["last_at"]).timestamp() if s["last_at"] else 0
        asked = bool(s["wants_contact"]) and not s["reviewed"]
        return (s["checkin_id"] is None, 0 if asked else 1, LEVEL_ORDER.get(s["alert_level"], 3), 1 if s["reviewed"] else 0, -ts)

    out.sort(key=key)
    return out


@app.get("/api/dashboard")
def dashboard(user=Depends(require_roles("psychologist", "admin"))):
    con = db()
    students = students_overview(con)
    since = (now_dt() - timedelta(days=20)).isoformat()
    created = con.execute("SELECT created_at, alert_level FROM checkins WHERE created_at>=?", (since,)).fetchall()
    total_checkins = con.execute("SELECT COUNT(*) FROM checkins").fetchone()[0]
    con.close()

    days = defaultdict(lambda: {"total": 0, "alto": 0, "medio": 0})
    for r in created:
        d = local_date(r["created_at"]).isoformat()
        days[d]["total"] += 1
        if r["alert_level"] in ("alto", "medio"):
            days[d][r["alert_level"]] += 1
    trend = [{"day": d, **v} for d, v in sorted(days.items())][-14:]

    with_reg = [s for s in students if s["checkin_id"]]
    import routes_student
    mindi_alerts = []
    con2 = db()
    for s_ in with_reg[:300]:
        sg, _, _ = routes_student.signals_for(con2, s_["student_id"])
        sg = [x for x in sg if x["level"] in ("alert", "warn")]
        if sg:
            mindi_alerts.append({"student_id": s_["student_id"], "name": s_["name"], "ciclo": s_["ciclo"], "level": sg[0]["level"],
                                 "texts": [x["psych"] for x in sg[:2]]})
    con2.close()
    mindi_alerts.sort(key=lambda a: 0 if a["level"] == "alert" else 1)
    dist = {"0": 0, "1": 0, "2": 0}
    alerts = {"alto": 0, "medio": 0, "bajo": 0}
    by_ciclo = defaultdict(lambda: {"total": 0, "alto": 0, "medio": 0, "bajo": 0})
    for s in with_reg:
        dist[str(s["predicted_class"])] += 1
        alerts[s["alert_level"]] += 1
        g = by_ciclo[s["ciclo"] or 0]
        g["total"] += 1
        g[s["alert_level"]] += 1
    return {
        "total_students": len(students), "students_with_checkin": len(with_reg), "total_checkins": total_checkins,
        "distribution": dist, "alerts": alerts,
        "pending_reviews": sum(1 for s in with_reg if s["alert_level"] in ("alto", "medio") and not s["reviewed"]),
        "contact_requests": sum(1 for s in with_reg if s["wants_contact"] and not s["reviewed"]),
        "trend": trend,
        "by_ciclo": [{"ciclo": c, **v} for c, v in sorted(by_ciclo.items())],
        "mindi_alerts": mindi_alerts[:8],
        "attention": [s for s in with_reg if (s["alert_level"] == "alto" or s["wants_contact"]) and not s["reviewed"]][:6],
    }


@app.get("/api/students")
def students(user=Depends(require_roles("psychologist", "admin"))):
    con = db()
    out = students_overview(con)
    con.close()
    return out


@app.get("/api/students/{student_id}")
def student_detail(student_id: int, user=Depends(require_roles("psychologist", "admin"))):
    con = db()
    s = con.execute("SELECT id,display_name,username,ciclo,carrera,created_at FROM users WHERE id=? AND role='student' AND active=1", (student_id,)).fetchone()
    if not s:
        con.close()
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    rows = con.execute("SELECT * FROM checkins WHERE student_id=? ORDER BY id DESC LIMIT 40", (student_id,)).fetchall()
    import routes_student
    sigs, _, evs = routes_student.signals_for(con, student_id)
    reps = con.execute("SELECT * FROM reports WHERE student_id=? ORDER BY id DESC LIMIT 10", (student_id,)).fetchall()
    con.close()
    import deep
    from routes_calendar import today_local
    sched = deep.schedule_summary(evs, today_local())
    items = []
    for i, r in enumerate(rows):
        c = shape_checkin(r)
        prev = shape_checkin(rows[i + 1]) if i + 1 < len(rows) else None
        c["plan"] = action_plan(c, prev)
        items.append(c)
    first = s["display_name"].split()[0]
    classes = [c["predicted_class"] for c in reversed(items)]
    progress = {"n": len(classes), "first": items[-1]["label"] if items else None, "last": items[0]["label"] if items else None,
                "direction": ("sin datos" if len(classes) < 2 else "mejora" if classes[-1] < classes[0] else "empeora" if classes[-1] > classes[0] else "estable")}
    return {"student": {"id": s["id"], "name": s["display_name"], "username": s["username"], "ciclo": s["ciclo"],
                        "carrera": s["carrera"] or "", "joined": s["created_at"]},
            "checkins": items, "suggested_message": suggested_message(first), "resources": chatbot.HELP_RESOURCES,
            "reports": [{"id": r["id"], "created_at": r["created_at"], "label": r["label"], "level": r["level"], "psych_report": r["psych_report"],
                         "qa": json.loads(r["qa"]), "source": r["source"], "n_recs": len(json.loads(r["recommendations"]))} for r in reps],
            "signals": [{"id": x["id"], "level": x["level"], "text": x["psych"]} for x in sigs],
            "schedule": {"busy_avg_h": sched["busy_avg_h"], "busy_max_h": sched["busy_max_h"], "days_without_rest": sched["days_without_rest"],
                         "has_events": sched["has_events"]},
            "progress": progress}


@app.patch("/api/checkins/{checkin_id}")
def update_checkin(checkin_id: int, data: ReviewInput, user=Depends(require_roles("psychologist", "admin"))):
    con = db()
    row = con.execute("SELECT id FROM checkins WHERE id=?", (checkin_id,)).fetchone()
    if not row:
        con.close()
        raise HTTPException(status_code=404, detail="Registro no encontrado.")
    if data.reviewed is not None:
        con.execute("UPDATE checkins SET reviewed=?, reviewed_by=?, reviewed_at=? WHERE id=?",
                    (1 if data.reviewed else 0, user["id"], now_iso() if data.reviewed else None, checkin_id))
    if data.psych_note is not None:
        con.execute("UPDATE checkins SET psych_note=? WHERE id=?", (data.psych_note.strip(), checkin_id))
    con.execute("UPDATE checkins SET rev=rev+1, synced=0 WHERE id=?", (checkin_id,))
    con.commit()
    con.close()
    SYNC_WAKE.set()
    return {"ok": True}


@app.get("/api/export.csv")
def export_csv(user=Depends(require_roles("psychologist", "admin"))):
    con = db()
    rows = con.execute("""SELECT c.*, u.username, u.display_name, u.ciclo, u.carrera FROM checkins c
                          JOIN users u ON u.id=c.student_id ORDER BY c.id DESC""").fetchall()
    con.close()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id_registro", "usuario", "estudiante", "ciclo", "carrera", "fecha_utc", "nivel_estres", "alerta",
                "ansiedad_0_21", "calidad_sueno_1_5", "carga_estudio_1_10", "resp_horas_sueno", "resp_estresor", "resp_contacto",
                "revisado", "nota_psicologia"])
    for r in rows:
        ans = json.loads(r["answers"] or "{}")

        def lab(q):
            return (sv.option(q, ans.get(q)) or {}).get("label", "") if ans.get(q) else ""

        w.writerow([r["id"], csv_safe(r["username"]), csv_safe(r["display_name"]), r["ciclo"] or "", csv_safe(r["carrera"]), r["created_at"],
                    sv.STRESS_LABELS.get(r["predicted_class"], ""), r["alert_level"], r["anxiety_level"], r["sleep_quality"],
                    r["study_load"], lab("sleep_hours"), lab("stressor"), lab("wants_contact"), r["reviewed"], csv_safe(r["psych_note"])])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=mindreset_registros.csv"})


# ------------------------------------------------------------------------- admin
@app.get("/api/psychologists")
def psychologists(user=Depends(require_roles("admin"))):
    con = db()
    rows = con.execute("SELECT id,username,display_name,active,created_at FROM users WHERE role='psychologist' ORDER BY id").fetchall()
    con.close()
    return [dict(r) for r in rows]


@app.post("/api/users")
def create_user(data: CreateUserInput, user=Depends(require_roles("admin"))):
    con = db()
    try:
        cur = con.execute("INSERT INTO users(username,password_hash,role,display_name,ciclo,carrera,created_at) VALUES(?,?,?,?,?,?,?)",
                          (data.username.strip().lower(), hash_password(data.password), data.role, data.display_name, data.ciclo, data.carrera, now_iso()))
        con.commit()
        result = {"id": cur.lastrowid, "username": data.username, "role": data.role}
    except sqlite3.IntegrityError:
        con.close()
        raise HTTPException(status_code=409, detail="El nombre de usuario ya existe.")
    con.close()
    SYNC_WAKE.set()
    return result


@app.post("/api/admin/sheets/sync")
def admin_sync(user=Depends(require_roles("admin"))):
    """Fuerza un envío inmediato a Google Sheets."""
    if not sheets.enabled():
        raise HTTPException(status_code=400, detail="Google Sheets no está configurado.")
    try:
        return {"pending": sync_once()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo sincronizar: {exc}")


@app.post("/api/admin/sheets/restore")
def admin_restore(user=Depends(require_roles("admin"))):
    """Trae desde la hoja lo que falte en la base local (no sobrescribe filas existentes)."""
    if not sheets.enabled():
        raise HTTPException(status_code=400, detail="Google Sheets no está configurado.")
    try:
        u, c = restore_from_sheets()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo leer la hoja: {exc}")
    return {"usuarios_agregados": u, "encuestas_agregadas": c}


# ------------------------------------------------------------------ módulos adicionales
import routes_calendar, routes_student, routes_community  # noqa: E402  (se importan al final para evitar ciclos)
app.include_router(routes_calendar.router)
app.include_router(routes_student.router)
app.include_router(routes_community.router)
