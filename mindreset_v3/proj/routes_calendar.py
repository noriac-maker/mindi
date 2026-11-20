"""Calendario, planificador, recordatorios por correo, verificación de email y enlaces para Google Calendar."""
import json
import logging
import os
import re
import secrets
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

import app as core
import chatbot
import mailer
import planner as pl

log = logging.getLogger("mindreset.calendar")
router = APIRouter()
student = core.require_roles("student")
STAMP = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$"
DEFAULT_NOTIFY = "class,work,rest,study,deadline,exam,sleep,other"
APP_URL = os.getenv("MINDRESET_APP_URL", "").rstrip("/")


def today_local():
    return datetime.now(core.TZ).date()


def app_url(request: Request):
    if APP_URL:
        return APP_URL
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return f"{proto}://{request.headers.get('x-forwarded-host', request.headers.get('host', 'localhost'))}"


def ev_dict(r):
    d = {k: r[k] for k in ("id", "title", "kind", "start_at", "end_at", "notes", "source")}
    d["gcal"] = pl.google_link(d, core.TZ)
    return d


def insert_events(con, user_id, events, source, plan_id=""):
    ids = []
    for e in events:
        cur = con.execute("INSERT INTO events(user_id,title,kind,start_at,end_at,notes,source,plan_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                          (user_id, e["title"][:80], e["kind"] if e["kind"] in pl.KINDS else "other", e["start_at"], e["end_at"],
                           (e.get("notes") or "")[:300], source, plan_id, core.now_iso()))
        ids.append(cur.lastrowid)
    return ids


def user_events(con, user_id, d0=None, d1=None):
    q, args = "SELECT * FROM events WHERE user_id=?", [user_id]
    if d0:
        q += " AND substr(start_at,1,10)>=?"
        args.append(d0)
    if d1:
        q += " AND substr(start_at,1,10)<=?"
        args.append(d1)
    return con.execute(q + " ORDER BY start_at", args).fetchall()


# ------------------------------------------------------------------ eventos
class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    kind: str = "other"
    start_at: str = Field(pattern=STAMP)
    end_at: str = Field(pattern=STAMP)
    notes: str = Field(default="", max_length=300)


def _check_event(e: EventIn):
    if e.kind not in pl.KINDS:
        raise HTTPException(422, "Tipo de actividad inválido.")
    try:
        a, b = pl.parse_stamp(e.start_at), pl.parse_stamp(e.end_at)
        if a >= b:
            raise ValueError
    except Exception:
        raise HTTPException(422, "La hora de fin debe ser posterior a la de inicio.")


@router.get("/api/calendar/events")
def list_events(start: str, end: str, user=Depends(student)):
    try:
        date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise HTTPException(422, "Fechas inválidas.")
    con = core.db()
    rows = user_events(con, user["id"], start, end)
    con.close()
    return [ev_dict(r) for r in rows]


@router.post("/api/calendar/events")
def create_event(data: EventIn, user=Depends(student)):
    _check_event(data)
    con = core.db()
    (eid,) = insert_events(con, user["id"], [data.model_dump()], "manual")
    con.commit()
    row = con.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
    con.close()
    core.SYNC_WAKE.set()
    return ev_dict(row)


@router.put("/api/calendar/events/{event_id}")
def update_event(event_id: int, data: EventIn, user=Depends(student)):
    _check_event(data)
    con = core.db()
    if not con.execute("SELECT 1 FROM events WHERE id=? AND user_id=?", (event_id, user["id"])).fetchone():
        con.close()
        raise HTTPException(404, "Actividad no encontrada.")
    con.execute("UPDATE events SET title=?,kind=?,start_at=?,end_at=?,notes=?,notified=0,rev=rev+1,synced=0 WHERE id=?",
                (data.title, data.kind, data.start_at, data.end_at, data.notes, event_id))
    con.commit()
    row = con.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    con.close()
    core.SYNC_WAKE.set()
    return ev_dict(row)


@router.delete("/api/calendar/events/{event_id}")
def delete_event(event_id: int, user=Depends(student)):
    con = core.db()
    cur = con.execute("DELETE FROM events WHERE id=? AND user_id=?", (event_id, user["id"]))
    con.commit()
    con.close()
    if not cur.rowcount:
        raise HTTPException(404, "Actividad no encontrada.")
    core.SYNC_DELETED.append(("Calendario", event_id))
    core.SYNC_WAKE.set()
    return {"ok": True}


@router.delete("/api/calendar/plan")
def delete_plan(user=Depends(student)):
    """Borra las actividades generadas por Mindi (no las que agregaste a mano)."""
    con = core.db()
    ids = [r["id"] for r in con.execute("SELECT id FROM events WHERE user_id=? AND source IN ('plan','mindi')", (user["id"],))]
    con.execute("DELETE FROM events WHERE user_id=? AND source IN ('plan','mindi')", (user["id"],))
    con.commit()
    con.close()
    core.SYNC_DELETED.extend(("Calendario", i) for i in ids)
    core.SYNC_WAKE.set()
    return {"deleted": len(ids)}


# ------------------------------------------------------------------ planificador
class FixedIn(BaseModel):
    title: str = Field(default="", max_length=80)
    kind: str = "class"
    days: List[int] = Field(default_factory=list, max_length=7)
    start: str = Field(pattern=r"^\d{1,2}:\d{2}$")
    end: str = Field(pattern=r"^\d{1,2}:\d{2}$")


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    due: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    hours: float = Field(default=3, ge=0.5, le=40)
    kind: str = "task"
    due_time: Optional[str] = Field(default=None, pattern=r"^\d{1,2}:\d{2}$")


class PlanReq(BaseModel):
    fixed: List[FixedIn] = Field(default_factory=list, max_length=30)
    tasks: List[TaskIn] = Field(default_factory=list, max_length=30)
    prefs: dict = Field(default_factory=dict)
    mode: str = Field(default="full", pattern="^(full|tasks_only)$")
    start: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.post("/api/planner/generate")
def planner_generate(data: PlanReq, user=Depends(student)):
    start = date.fromisoformat(data.start) if data.start else today_local() + timedelta(days=1)
    horizon_end = (start + timedelta(days=28)).isoformat()
    con = core.db()
    rows = user_events(con, user["id"], start.isoformat(), horizon_end)
    con.close()
    # en modo completo el plan anterior se reemplaza, así que no ocupa huecos; lo manual sí
    existing = [ev_dict(r) for r in rows if data.mode == "tasks_only" or r["source"] not in ("plan", "mindi")]
    now = datetime.now(core.TZ)
    if start == now.date():
        existing.append({"start_at": pl.stamp(start, 0), "end_at": pl.stamp(start, min(1439, now.hour * 60 + now.minute + 30))})
    prefs = {k: v for k, v in data.prefs.items() if k in pl.DEFAULT_PREFS}
    try:
        plan = pl.generate_plan([f.model_dump() for f in data.fixed], [t.model_dump() for t in data.tasks], prefs, start, existing, data.mode)
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, f"Revisa los datos del horario: {exc}")
    plan["start"] = start.isoformat()
    return plan


class ApplyReq(BaseModel):
    events: List[dict] = Field(max_length=900)
    replace_plan: bool = True
    start: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.post("/api/planner/apply")
def planner_apply(data: ApplyReq, user=Depends(student)):
    clean = []
    for e in data.events:
        try:
            ev = EventIn(title=str(e["title"]), kind=str(e.get("kind", "other")), start_at=e["start_at"], end_at=e["end_at"], notes=str(e.get("notes", "")))
            _check_event(ev)
            clean.append(ev.model_dump())
        except HTTPException:
            continue
        except Exception:
            continue
    if not clean:
        raise HTTPException(422, "No hay actividades válidas para guardar.")
    con = core.db()
    removed = []
    if data.replace_plan:
        start = data.start or min(e["start_at"][:10] for e in clean)
        removed = [r["id"] for r in con.execute("SELECT id FROM events WHERE user_id=? AND source='plan' AND substr(start_at,1,10)>=?", (user["id"], start))]
        con.execute("DELETE FROM events WHERE user_id=? AND source='plan' AND substr(start_at,1,10)>=?", (user["id"], start))
    insert_events(con, user["id"], clean, "plan", uuid.uuid4().hex[:10])
    con.commit()
    con.close()
    core.SYNC_DELETED.extend(("Calendario", i) for i in removed)
    core.SYNC_WAKE.set()
    return {"saved": len(clean), "replaced": len(removed)}


class AddActivitiesReq(BaseModel):
    items: List[dict] = Field(min_length=1, max_length=8)


@router.post("/api/calendar/add-activities")
def add_activities(data: AddActivitiesReq, user=Depends(student)):
    start = today_local() + timedelta(days=1)
    con = core.db()
    existing = [ev_dict(r) for r in user_events(con, user["id"], start.isoformat(), (start + timedelta(days=8)).isoformat())]
    items = []
    for it in data.items:
        days = it.get("days")
        items.append({"title": it.get("title"), "kind": it.get("kind"), "minutes": it.get("minutes"),
                      "days": [d for d in days if isinstance(d, int) and 0 <= d <= 6] if isinstance(days, list) else None,
                      "time_pref": it.get("time_pref"), "notes": "Sugerido por Mindi"})
    res = pl.place_activities(items, start, existing)
    insert_events(con, user["id"], res["events"], "mindi", uuid.uuid4().hex[:10])
    con.commit()
    con.close()
    core.SYNC_WAKE.set()
    return {"added": len(res["events"]), "skipped": res["skipped"], "from": start.isoformat()}


# ------------------------------------------------------------------ lectura de texto libre
class ParseReq(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


def _clean_parse(d, today):
    fixed, tasks = [], []
    for f in d.get("fixed") or []:
        try:
            days = [int(x) for x in f.get("days", []) if 0 <= int(x) <= 6]
            s, e = str(f["start"]), str(f["end"])
            pl.to_min(s), pl.to_min(e)
            if days:
                fixed.append({"title": str(f.get("title") or "Clases")[:80], "kind": f.get("kind") if f.get("kind") in pl.KINDS else "class", "days": days, "start": s, "end": e})
        except Exception:
            continue
    for t in d.get("tasks") or []:
        try:
            due = date.fromisoformat(str(t["due"]))
            tasks.append({"title": str(t.get("title") or "Tarea")[:80], "due": due.isoformat(), "hours": max(0.5, min(float(t.get("hours") or 3), 40)),
                          "kind": "exam" if t.get("kind") == "exam" else "task"})
        except Exception:
            continue
    prefs = {k: d["prefs"][k] for k in ("wake", "sleep", "transport_min") if isinstance(d.get("prefs"), dict) and d["prefs"].get(k) not in (None, "")}
    return {"fixed": fixed, "tasks": tasks, "prefs": prefs, "unparsed": [str(x) for x in (d.get("unparsed") or [])][:5]}


@router.post("/api/planner/parse")
def planner_parse(data: ParseReq, user=Depends(student)):
    today = today_local()
    if chatbot.gemini_available():
        try:
            num = {"type": "NUMBER"}
            schema = {"type": "OBJECT", "properties": {
                "fixed": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"title": {"type": "STRING"}, "kind": {"type": "STRING"}, "days": {"type": "ARRAY", "items": num},
                                                                                       "start": {"type": "STRING"}, "end": {"type": "STRING"}}, "required": ["days", "start", "end"]}},
                "tasks": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"title": {"type": "STRING"}, "due": {"type": "STRING"}, "hours": num, "kind": {"type": "STRING"}},
                                                     "required": ["title", "due"]}},
                "prefs": {"type": "OBJECT", "properties": {"wake": {"type": "STRING"}, "sleep": {"type": "STRING"}, "transport_min": num}},
                "unparsed": {"type": "ARRAY", "items": {"type": "STRING"}}}}
            prompt = (f"Hoy es {pl.DAYS[today.weekday()]} {today.isoformat()}. Extrae del texto del estudiante: (1) 'fixed': compromisos semanales fijos (clases, trabajo, otros) con "
                      "days (0=lunes…6=domingo), start y end en HH:MM de 24 h y kind (class|work|other); (2) 'tasks': entregas o exámenes con title, due (YYYY-MM-DD, calcula la fecha "
                      "real a partir de hoy), hours (esfuerzo estimado; si no lo dice, 3 para tareas y 6 para exámenes) y kind (task|exam); (3) 'prefs': wake, sleep (HH:MM) y "
                      "transport_min (minutos de traslado por trayecto) si los menciona; (4) 'unparsed': frases que no pudiste interpretar. No inventes datos.\n\nTexto: " + data.text)
            res = chatbot.gemini_json("Eres un asistente que convierte texto en JSON de horario. Respondes solo JSON válido.", prompt, schema, max_tokens=1800, temperature=0.1)
            out = _clean_parse(res, today)
            out["source"] = "gemini"
            return out
        except Exception as exc:
            log.warning("Gemini no pudo leer el horario (%s); uso lector básico", type(exc).__name__)
    out = pl.parse_text(data.text, today)
    out["source"] = "basic"
    return out


# ------------------------------------------------------------------ Google Calendar / ICS
def _feed_token(user):
    if user.get("feed_token"):
        return user["feed_token"]
    token = secrets.token_urlsafe(24)
    con = core.db()
    con.execute("UPDATE users SET feed_token=? WHERE id=?", (token, user["id"]))
    con.commit()
    con.close()
    return token


@router.get("/api/calendar/feed-info")
def feed_info(request: Request, user=Depends(student)):
    base = app_url(request)
    url = f"{base}/cal/{_feed_token(user)}.ics"
    webcal = "webcal://" + url.split("://", 1)[1]
    return {"feed_url": url, "webcal_url": webcal, "google_subscribe": "https://calendar.google.com/calendar/r?cid=" + quote(webcal, safe=""),
            "email": user.get("email") or ""}


def _events_ics(user_id, name):
    con = core.db()
    d0 = (today_local() - timedelta(days=30)).isoformat()
    rows = user_events(con, user_id, d0, None)
    con.close()
    return pl.make_ics([{k: r[k] for k in ("id", "title", "start_at", "end_at", "notes")} for r in rows], core.TZ, name)


@router.get("/cal/{token}.ics")
def public_feed(token: str):
    con = core.db()
    u = con.execute("SELECT id FROM users WHERE feed_token=? AND role='student' AND active=1", (token,)).fetchone()
    con.close()
    if not u:
        raise HTTPException(404, "Calendario no encontrado.")
    return Response(_events_ics(u["id"], "MindReset"), media_type="text/calendar; charset=utf-8", headers={"Cache-Control": "no-store"})


@router.get("/api/calendar/export.ics")
def export_ics(user=Depends(student)):
    return Response(_events_ics(user["id"], "MindReset"), media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=mindreset_calendario.ics"})


# ------------------------------------------------------------------ correo: ajustes, verificación y prueba
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_codes = {}


class ProfileIn(BaseModel):
    email: Optional[str] = Field(default=None, max_length=120)
    notify_email: Optional[bool] = None
    notify_kinds: Optional[List[str]] = None


@router.patch("/api/profile")
def update_profile(data: ProfileIn, user=Depends(core.current_user)):
    con = core.db()
    if data.email is not None:
        email = data.email.strip().lower()
        if email and not EMAIL_RE.match(email):
            con.close()
            raise HTTPException(422, "Escribe un correo válido.")
        if email != (user.get("email") or ""):
            con.execute("UPDATE users SET email=?, email_verified=0, rev=rev+1, synced=0 WHERE id=?", (email, user["id"]))
    if data.notify_email is not None:
        con.execute("UPDATE users SET notify_email=?, rev=rev+1, synced=0 WHERE id=?", (1 if data.notify_email else 0, user["id"]))
    if data.notify_kinds is not None:
        kinds = ",".join(k for k in data.notify_kinds if k in pl.KINDS)
        con.execute("UPDATE users SET notify_kinds=?, rev=rev+1, synced=0 WHERE id=?", (kinds, user["id"]))
    con.commit()
    row = con.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    out = core.public_user(dict(row), con)
    con.close()
    core.SYNC_WAKE.set()
    return out


@router.post("/api/email/send-code")
def send_code(user=Depends(core.current_user)):
    if not user.get("email"):
        raise HTTPException(400, "Primero guarda tu correo.")
    if not mailer.configured():
        raise HTTPException(503, "El envío de correos no está configurado en este servidor.")
    prev = _codes.get(user["id"])
    if prev and time.time() - prev["sent"] < 45:
        raise HTTPException(429, "Espera unos segundos antes de pedir otro código.")
    if not mailer.allowed(user["id"]):
        raise HTTPException(429, "Se alcanzó el límite diario de correos.")
    code = f"{secrets.randbelow(1000000):06d}"
    _codes[user["id"]] = {"code": code, "exp": time.time() + 900, "tries": 0, "sent": time.time()}
    try:
        mailer.send(user["email"], "Tu código de MindReset", mailer.wrap("Verifica tu correo", f"<p>Tu código es:</p><p style='font-size:30px;letter-spacing:6px;font-weight:bold;color:#6A3EC8'>{code}</p><p>Vence en 15 minutos.</p>"), user["id"])
    except Exception as exc:
        log.warning("No se pudo enviar el código: %s", exc)
        raise HTTPException(502, "No se pudo enviar el correo. Revisa la configuración e inténtalo de nuevo.")
    return {"ok": True}


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=6)


@router.post("/api/email/verify")
def verify_code(data: CodeIn, user=Depends(core.current_user)):
    c = _codes.get(user["id"])
    if not c or c["exp"] < time.time():
        raise HTTPException(400, "El código venció. Pide uno nuevo.")
    c["tries"] += 1
    if c["tries"] > 5:
        _codes.pop(user["id"], None)
        raise HTTPException(429, "Demasiados intentos. Pide un código nuevo.")
    if data.code != c["code"]:
        raise HTTPException(400, "Código incorrecto.")
    _codes.pop(user["id"], None)
    con = core.db()
    con.execute("UPDATE users SET email_verified=1, rev=rev+1, synced=0 WHERE id=?", (user["id"],))
    con.commit()
    con.close()
    core.SYNC_WAKE.set()
    return {"ok": True}


@router.post("/api/email/test")
def test_email(user=Depends(student)):
    if not (user.get("email") and user.get("email_verified")):
        raise HTTPException(400, "Verifica tu correo primero.")
    if not mailer.allowed(user["id"]):
        raise HTTPException(429, "Se alcanzó el límite diario de correos.")
    try:
        mailer.send(user["email"], "⏰ Prueba de recordatorio de MindReset",
                    mailer.wrap("Así se verán tus recordatorios", "<p>En 15 minutos: <b>Pausa activa</b>.</p><p>Estírate, toma agua y mira lejos de la pantalla.</p>", APP_URL), user["id"])
    except Exception as exc:
        raise HTTPException(502, f"No se pudo enviar: {exc}")
    return {"ok": True}


# ------------------------------------------------------------------ recordatorios (15 minutos antes)
TIPS = {"rest": "Aprovecha para respirar, estirarte y tomar agua.", "sleep": "Apaga pantallas y baja las luces: tu sueño te lo agradece.",
        "study": "Deja el celular lejos y trabaja solo en esto. ¡Tú puedes!", "class": "Prepara tus materiales con calma.",
        "deadline": "Revisa lo último y respira: ya hiciste lo más difícil.", "exam": "Respira 4-6 antes de empezar y lee todo primero."}


def reminders_once(now_utc=None):
    """Envía correos de actividades que empiezan en ≤15 min. Devuelve cuántos envió."""
    now = (now_utc or datetime.now(timezone.utc)).astimezone(core.TZ)
    lo = now.strftime("%Y-%m-%dT%H:%M")
    hi = (now + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M")
    con = core.db()
    rows = con.execute("""SELECT e.*, u.email, u.display_name, u.notify_kinds FROM events e JOIN users u ON u.id=e.user_id
                          WHERE e.notified=0 AND u.notify_email=1 AND u.email_verified=1 AND u.email!='' AND u.active=1
                          AND e.start_at>? AND e.start_at<=? ORDER BY e.start_at""", (lo, hi)).fetchall()
    sent = 0
    for r in rows:
        kinds = (r["notify_kinds"] or DEFAULT_NOTIFY).split(",")
        if r["kind"] not in kinds:
            con.execute("UPDATE events SET notified=1 WHERE id=?", (r["id"],))
            continue
        if not mailer.allowed(r["user_id"]):
            log.warning("Límite de correos alcanzado; se omite un recordatorio")
            continue
        s, e = r["start_at"][11:], r["end_at"][11:]
        first = r["display_name"].split()[0]
        body = (f"<p>Hola {first},</p><p>En 15 minutos: <b>{r['title']}</b> ({s}–{e}).</p><p>{TIPS.get(r['kind'], 'Que te vaya muy bien.')}</p>")
        try:
            mailer.send(r["email"], f"⏰ En 15 min: {r['title']}", mailer.wrap("Tu próxima actividad", body, APP_URL), r["user_id"])
            con.execute("UPDATE events SET notified=1, rev=rev+1, synced=0 WHERE id=?", (r["id"],))
            sent += 1
        except Exception as exc:
            log.warning("No se pudo enviar el recordatorio: %s", exc)
    con.commit()
    con.close()
    if sent:
        core.SYNC_WAKE.set()
    return sent


def reminder_loop():
    while True:
        time.sleep(60)
        try:
            if mailer.configured():
                reminders_once()
        except Exception as exc:
            log.warning("Fallo en el ciclo de recordatorios: %s", exc)


def start_reminders():
    threading.Thread(target=reminder_loop, daemon=True, name="reminders").start()
