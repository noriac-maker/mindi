"""Envío de correos (recordatorios y verificación).

Por defecto usa el mismo puente de Google Apps Script que la hoja de cálculo (HTTPS), porque el plan gratuito de
Render bloquea los puertos SMTP. Si defines SMTP_HOST (+ SMTP_PORT/SMTP_USER/SMTP_PASSWORD/SMTP_FROM) usa SMTP.
Cuota orientativa de Apps Script: ~100 correos/día con Gmail personal.
"""
import os
import smtplib
import threading
import time
from email.message import EmailMessage

import sheets

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER).strip()
DAILY_LIMIT = int(os.getenv("MINDRESET_MAIL_DAILY_LIMIT", "90"))
PER_USER_LIMIT = int(os.getenv("MINDRESET_MAIL_PER_USER", "12"))

_lock = threading.Lock()
_count = {"day": time.strftime("%Y-%m-%d"), "total": 0, "users": {}}


def configured():
    return bool(SMTP_HOST or sheets.enabled())


def allowed(user_id):
    """Control de cuota diaria global y por usuario (evita agotar el límite del proveedor)."""
    with _lock:
        today = time.strftime("%Y-%m-%d")
        if _count["day"] != today:
            _count.update(day=today, total=0, users={})
        return _count["total"] < DAILY_LIMIT and _count["users"].get(user_id, 0) < PER_USER_LIMIT


def _bump(user_id):
    with _lock:
        _count["total"] += 1
        _count["users"][user_id] = _count["users"].get(user_id, 0) + 1


def send(to, subject, html, user_id=None):
    if SMTP_HOST:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, SMTP_FROM or SMTP_USER, to
        msg.set_content("Abre este mensaje en un cliente que muestre HTML.")
        msg.add_alternative(html, subtype="html")
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            s.starttls()
            if SMTP_USER:
                s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)
    elif sheets.enabled():
        sheets.call("send_email", to=to, subject=subject, html=html)
    else:
        raise RuntimeError("El envío de correos no está configurado.")
    if user_id is not None:
        _bump(user_id)


def wrap(title, body_html, app_url=""):
    link = f'<p style="margin-top:18px"><a href="{app_url}" style="background:#6A3EC8;color:#fff;padding:10px 18px;border-radius:12px;text-decoration:none;font-weight:bold">Abrir MindReset</a></p>' if app_url else ""
    return (f'<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;background:#FFF9F0;border-radius:18px;padding:24px;color:#4B5E7C">'
            f'<h2 style="color:#6A3EC8;margin:0 0 10px">{title}</h2>{body_html}{link}'
            f'<p style="font-size:12px;color:#8a96ab;margin-top:22px">Recibes este correo porque activaste los recordatorios en MindReset. '
            f'Puedes desactivarlos en Calendario → Recordatorios.</p></div>')
