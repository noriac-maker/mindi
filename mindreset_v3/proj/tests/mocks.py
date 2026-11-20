"""Servidores falsos: imitan Google Apps Script (con su redirección 302, hojas, borrado y correo) y Gemini."""
import json, threading, uuid
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET = "test-secret"
SHEETS = defaultdict(dict)       # hoja -> id -> fila
MAILS = []                        # correos "enviados"
GEMINI_REQUESTS = []
_results = {}


class SheetsHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        act = body.get("action")
        if body.get("secret") != SECRET:
            out = {"ok": False, "error": "unauthorized"}
        elif act == "upsert":
            for row in body["rows"]:
                SHEETS[body["sheet"]][str(row["id"])] = {k: ("" if v is None else str(v)) for k, v in row.items()}
            out = {"ok": True, "count": len(body["rows"])}
        elif act == "delete":
            for i in body["ids"]:
                SHEETS[body["sheet"]].pop(str(i), None)
            out = {"ok": True}
        elif act == "send_email":
            MAILS.append({"to": body["to"], "subject": body["subject"], "html": body["html"]})
            out = {"ok": True}
        elif act == "dump":
            out = {"ok": True, **{k: list(v.values()) for k, v in SHEETS.items()}}
        else:
            out = {"ok": False, "error": "unknown action"}
        rid = uuid.uuid4().hex
        _results[rid] = out
        self.send_response(302)                      # Apps Script responde así a los POST
        self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/result/{rid}")
        self.end_headers()

    def do_GET(self):
        rid = self.path.rsplit("/", 1)[-1]
        data = json.dumps(_results.pop(rid, {"ok": False, "error": "gone"})).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(data)


class GeminiHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        GEMINI_REQUESTS.append({"path": self.path, "key": self.headers.get("x-goog-api-key"), "body": body})
        if self.headers.get("x-goog-api-key") != "fake-key":
            self.send_response(403); self.end_headers(); self.wfile.write(b"{}"); return
        props = ((body.get("generationConfig") or {}).get("responseSchema") or {}).get("properties", {})
        if "questions" in props:
            out = {"questions": [{"title": f"Pregunta personalizada {i}", "help": "ayuda", "options": [{"label": "Opción A", "hint": "a"}, {"label": "Opción B", "hint": "b"}, {"label": "Opción C"}]} for i in (1, 2, 3)]}
        elif "student_summary" in props:
            out = {"student_summary": "Gracias por contarme más. Armé ideas para ti.", "psych_report": "Informe breve de prueba: factores sueño y carga. Seguimiento en 7 días.",
                   "recommendations": [{"title": "Pausa de respiración", "detail": "Respira 4-6 cinco veces.", "calendar": {"title": "Respiración 4-6", "kind": "rest", "minutes": 5, "days": [0, 1, 2, 3, 4], "time_pref": "16:30"}},
                                       {"title": "Habla con alguien", "detail": "Escribe a un amigo.", "calendar": None}]}
        elif "fixed" in props:
            out = {"fixed": [{"title": "Clases", "kind": "class", "days": [0, 1, 2, 3, 4], "start": "08:00", "end": "14:00"}],
                   "tasks": [{"title": "Informe de estadística", "due": "2099-01-10", "hours": 4, "kind": "task"}], "prefs": {"transport_min": 30}, "unparsed": []}
        else:
            out = {"reply": "Hola, te entiendo. Prueba **respirar 4-6**.", "suggestions": ["Quiero otro consejo", "Tengo examen"]}
        payload = {"candidates": [{"content": {"parts": [{"text": json.dumps(out)}]}}]}
        data = json.dumps(payload).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(data)


def start(handler, port=0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
