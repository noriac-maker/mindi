"""Cliente de Google Sheets vía Google Apps Script (Web App).

No requiere proyecto de Google Cloud ni cuenta de servicio: la hoja publica un
script (google_apps_script/Code.gs) y esta app le envía datos con un secreto
compartido. Variables de entorno:
    MINDRESET_SHEETS_URL     URL de la Web App (termina en /exec)
    MINDRESET_SHEETS_SECRET  el mismo secreto guardado en las propiedades del script
"""
import json
import os
import urllib.request

SHEETS_URL = os.getenv("MINDRESET_SHEETS_URL", "").strip()
SHEETS_SECRET = os.getenv("MINDRESET_SHEETS_SECRET", "").strip()

# Las cabeceras de cada pestaña viven en google_apps_script/Code.gs (HEADERS) y las claves de los dicts en app.py.


def enabled():
    return bool(SHEETS_URL and SHEETS_SECRET)


def call(action, timeout=30, **data):
    """POST JSON a la Web App. urllib sigue la redirección 302 de Apps Script (la respuesta se lee por GET)."""
    payload = json.dumps({"secret": SHEETS_SECRET, "action": action, **data}).encode("utf-8")
    req = urllib.request.Request(SHEETS_URL, data=payload, headers={"Content-Type": "text/plain;charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    try:
        out = json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError("La Web App no devolvió JSON (¿publicaste con acceso «Cualquier persona»?).")
    if not out.get("ok"):
        raise RuntimeError(out.get("error", "Error desconocido en la hoja"))
    return out


def upsert(sheet, rows):
    return call("upsert", sheet=sheet, rows=rows)


def dump():
    return call("dump")


def delete(sheet, ids):
    return call("delete", sheet=sheet, ids=ids)
