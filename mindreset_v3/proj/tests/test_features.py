"""Calendario, planificador, correo, chequeo profundo, señales y comunidad."""
import re
from datetime import datetime, timedelta
from conftest import *
import mocks, app as appmod, routes_calendar as rc


def tomorrow():
    return (datetime.now(appmod.TZ).date() + timedelta(days=1))


def test_planner_calendar_flow(client):
    c = client
    H, me = new_student(c, "plan.user", "Plan Usuario")
    # lectura de texto (Gemini simulado) y respaldo básico
    r = c.post("/api/planner/parse", headers=H, json={"text": "Clases de lunes a viernes de 8 a 14, transporte 30 min, informe de estadística el 10 de enero"}).json()
    assert r["source"] == "gemini" and r["fixed"] and r["tasks"] and r["prefs"]["transport_min"] == 30
    saved = appmod.chatbot.GEMINI_API_KEY; appmod.chatbot.GEMINI_API_KEY = ""
    b = c.post("/api/planner/parse", headers=H, json={"text": "Clases de lunes a viernes de 8 a 14. Tarea de estadística que se entrega el viernes y me toma 5 horas."}).json()
    appmod.chatbot.GEMINI_API_KEY = saved
    assert b["source"] == "basic" and b["fixed"][0]["days"] == [0, 1, 2, 3, 4] and b["tasks"][0]["hours"] == 5

    due = (tomorrow() + timedelta(days=5)).isoformat()
    req = {"fixed": b["fixed"], "tasks": [{"title": "Informe de estadística", "due": due, "hours": 5, "kind": "task"}], "prefs": {"transport_min": 40}}
    plan = c.post("/api/planner/generate", headers=H, json=req).json()
    kinds = {e["kind"] for e in plan["events"]}
    assert {"class", "study", "rest", "meal", "sleep", "transport", "deadline"} <= kinds, kinds
    study_days = {e["start_at"][:10] for e in plan["events"] if e["kind"] == "study"}
    assert len(study_days) >= 4 and all(d < due for d in study_days)      # estudio repartido, antes de la entrega
    assert plan["stats"]["study_hours"] == 5.0
    assert c.post("/api/planner/generate", headers=H, json={**req, "tasks": [{"title": "X", "due": "2020-01-01", "hours": 2}]}).json()["warnings"]

    ap = c.post("/api/planner/apply", headers=H, json={"events": plan["events"], "replace_plan": True}).json()
    assert ap["saved"] == len(plan["events"])
    again = c.post("/api/planner/apply", headers=H, json={"events": plan["events"], "replace_plan": True}).json()
    assert again["replaced"] == ap["saved"]                                # reemplaza, no duplica
    s0, s1 = tomorrow().isoformat(), (tomorrow() + timedelta(days=6)).isoformat()
    evs = c.get(f"/api/calendar/events?start={s0}&end={s1}", headers=H).json()
    assert evs and evs[0]["gcal"].startswith("https://calendar.google.com/")

    # añadir una entrega nueva respetando lo existente
    q = c.post("/api/planner/generate", headers=H, json={"mode": "tasks_only", "tasks": [{"title": "Ensayo", "due": (tomorrow() + timedelta(days=4)).isoformat(), "hours": 3}]}).json()
    assert q["events"] and not any(e["kind"] in ("meal", "sleep") for e in q["events"])
    busy = [(e["start_at"], e["end_at"]) for e in evs]
    for e in q["events"]:
        if e["kind"] == "study":
            assert not any(a < e["end_at"] and e["start_at"] < b for a, b in busy if a[:10] == e["start_at"][:10]), "se superpone con algo existente"

    # eventos manuales: crear, editar, borrar (y se refleja en la hoja)
    day = tomorrow().isoformat()
    ev = c.post("/api/calendar/events", headers=H, json={"title": "Cita médica", "kind": "other", "start_at": f"{day}T16:00", "end_at": f"{day}T17:00"}).json()
    assert c.post("/api/calendar/events", headers=H, json={"title": "Mal", "start_at": f"{day}T16:00", "end_at": f"{day}T15:00"}).status_code == 422
    assert c.put(f"/api/calendar/events/{ev['id']}", headers=H, json={"title": "Cita médica 2", "kind": "other", "start_at": f"{day}T16:30", "end_at": f"{day}T17:00"}).json()["title"] == "Cita médica 2"
    assert wait(lambda: mocks.SHEETS["Calendario"].get(str(ev["id"]), {}).get("titulo") == "Cita médica 2")
    H2, _ = new_student(c, "otro.user", "Otro Usuario")
    assert c.delete(f"/api/calendar/events/{ev['id']}", headers=H2).status_code == 404       # no puede borrar lo ajeno
    assert c.delete(f"/api/calendar/events/{ev['id']}", headers=H).status_code == 200
    assert wait(lambda: str(ev["id"]) not in mocks.SHEETS["Calendario"])

    # Google Calendar: feed .ics público con token y exportación
    info = c.get("/api/calendar/feed-info", headers=H).json()
    assert info["feed_url"].startswith("https://mindreset.test/cal/") and info["google_subscribe"].startswith("https://calendar.google.com/calendar/r?cid=")
    ics = c.get(info["feed_url"].replace("https://mindreset.test", "")).text
    assert ics.startswith("BEGIN:VCALENDAR") and "BEGIN:VEVENT" in ics and "TRIGGER:-PT15M" in ics and "Estudio" in ics
    assert c.get("/cal/token-falso.ics").status_code == 404
    assert "VEVENT" in c.get("/api/calendar/export.ics", headers=H).text


def test_email_verification_and_reminders(client):
    c = client
    H, me = new_student(c, "mail.user", "Mail Usuario", email="mail.user@mail.test")
    assert c.post("/api/email/test", headers=H).status_code == 400                    # sin verificar no se envía
    assert c.post("/api/email/send-code", headers=H).status_code == 200
    code = re.search(r">(\d{6})<", mocks.MAILS[-1]["html"]).group(1)
    assert mocks.MAILS[-1]["to"] == "mail.user@mail.test"
    assert c.post("/api/email/verify", headers=H, json={"code": "000000" if code != "000000" else "111111"}).status_code == 400
    assert c.post("/api/email/verify", headers=H, json={"code": code}).status_code == 200
    assert c.get("/api/me", headers=H).json()["email_verified"] is True

    now = datetime.now(appmod.TZ)
    mk = lambda title, mins, kind: c.post("/api/calendar/events", headers=H, json={
        "title": title, "kind": kind, "start_at": (now + timedelta(minutes=mins)).strftime("%Y-%m-%dT%H:%M"),
        "end_at": (now + timedelta(minutes=mins + 20)).strftime("%Y-%m-%dT%H:%M")}).json()
    mk("Pausa activa", 10, "rest"); mk("Más tarde", 90, "rest"); mk("Comida", 5, "meal")
    before = len(mocks.MAILS)
    assert rc.reminders_once() == 1                                                    # solo lo que empieza en ≤15 min y es de un tipo avisable
    assert len(mocks.MAILS) == before + 1 and "En 15 min: Pausa activa" in mocks.MAILS[-1]["subject"]
    assert rc.reminders_once() == 0                                                    # no repite
    # preferencias: desactivar recordatorios
    assert c.patch("/api/profile", headers=H, json={"notify_email": False}).json()["notify_email"] is False
    mk("Otra pausa", 8, "rest")
    assert rc.reminders_once() == 0
    # cambiar de correo exige verificar de nuevo
    assert c.patch("/api/profile", headers=H, json={"email": "nuevo@mail.test"}).json()["email_verified"] is False


def test_deep_checkin_and_recommendations(client):
    c = client
    H, me = new_student(c, "deep.user", "Deep Usuario")
    assert c.post("/api/deep/questions", headers=H, json={"chat": []}).status_code == 400   # antes necesita la encuesta
    c.post("/api/checkins", headers=H, json={"answers": ANS_HIGH})
    # con Gemini (simulado)
    g = c.post("/api/deep/questions", headers=H, json={"chat": ["no logro dormir y tengo examen"]}).json()
    assert g["source"] == "gemini" and len(g["questions"]) == 3
    # reglas: preguntas adaptadas a las respuestas (sueño muy malo, carga alta, preocupación diaria)
    saved = appmod.chatbot.GEMINI_API_KEY; appmod.chatbot.GEMINI_API_KEY = ""
    b = c.post("/api/deep/questions", headers=H, json={"chat": ["no logro dormir"]}).json()
    assert b["source"] == "basic" and len(b["questions"]) == 3
    ids = [q["id"] for q in b["questions"]]
    assert "sleep_pre" in ids and ("anxiety_when" in ids or "task_hard" in ids)
    ans = {q["id"]: q["options"][0]["id"] for q in b["questions"]}
    assert c.post("/api/deep/submit", headers=H, json={"questions": b["questions"], "answers": {**ans, ids[0]: "no-existe"}}).status_code == 422
    sub = c.post("/api/deep/submit", headers=H, json={"questions": b["questions"], "answers": ans}).json()
    appmod.chatbot.GEMINI_API_KEY = saved
    assert sub["source"] == "basic" and sub["recommendations"] and "psych_report" in sub and any(r["calendar"] for r in sub["recommendations"])
    # añadir al calendario las actividades sugeridas
    items = [r["calendar"] for r in sub["recommendations"] if r["calendar"]]
    add = c.post("/api/calendar/add-activities", headers=H, json={"items": items}).json()
    assert add["added"] >= 1
    evs = c.get(f"/api/calendar/events?start={tomorrow().isoformat()}&end={(tomorrow() + timedelta(days=7)).isoformat()}", headers=H).json()
    assert any(e["source"] == "mindi" for e in evs)
    # el informe llega al panel del psicólogo y a la hoja
    assert wait(lambda: any(r["id_estudiante"] == str(me["id"]) for r in mocks.SHEETS["Informes"].values()))
    PH, _ = login(c, "psicologo1", "PsicoDemo2026!")
    det = c.get(f"/api/students/{me['id']}", headers=PH).json()
    assert det["reports"] and det["reports"][0]["psych_report"] and len(det["reports"][0]["qa"]) == 3
    assert "schedule" in det and "signals" in det
    # con Gemini el análisis lo redacta Gemini
    gq = c.post("/api/deep/questions", headers=H, json={"chat": []}).json()
    gs = c.post("/api/deep/submit", headers=H, json={"questions": gq["questions"], "answers": {q["id"]: q["options"][1]["id"] for q in gq["questions"]}}).json()
    assert gs["source"] == "gemini" and gs["recommendations"][0]["calendar"]["kind"] == "rest"
    prompt = [r for r in mocks.GEMINI_REQUESTS if "student_summary" in str(r["body"].get("generationConfig", {}))][-1]["body"]["contents"][0]["parts"][0]["text"]
    assert "Pausa activa" not in prompt and "Cita" not in prompt                       # no se envían títulos del calendario


def test_signals_and_chat_offer(client):
    c = client
    H, me = new_student(c, "sig.user", "Sig Usuario")
    c.post("/api/checkins", headers=H, json={"answers": ANS_LOW})
    c.post("/api/checkins", headers=H, json={"answers": ANS_HIGH})
    sig = c.get("/api/signals", headers=H).json()
    assert any(s["id"] == "trend_up" for s in sig)
    # un día sobrecargado dispara aviso
    day = (tomorrow() + timedelta(days=1)).isoformat()
    c.post("/api/calendar/events", headers=H, json={"title": "Turno largo", "kind": "work", "start_at": f"{day}T06:00", "end_at": f"{day}T18:30"})
    sig = c.get("/api/signals", headers=H).json()
    assert any(s["id"] == "overload_day" for s in sig)
    PH, _ = login(c, "psicologo1", "PsicoDemo2026!")
    det = c.get(f"/api/students/{me['id']}", headers=PH).json()
    assert any(s["id"] == "overload_day" for s in det["signals"]) and "Turno largo" not in str(det["signals"])
    # Mindi detecta decaimiento sostenido en la conversación y ofrece (no avisa solo)
    h = [{"role": "user", "text": "estoy muy estresada con todo"}, {"role": "bot", "text": "te escucho"}]
    r = c.post("/api/chat", headers=H, json={"message": "ya no aguanto, estoy agotada", "history": h}).json()
    assert r["offer_support"] is True
    r2 = c.post("/api/chat", headers=H, json={"message": "sigo agotada", "history": h, "offered": True}).json()
    assert r2["offer_support"] is False


def test_community(client):
    c = client
    A, a = new_student(c, "com.a", "Carla Pérez")
    B, b = new_student(c, "com.b", "Beto Ruiz")
    assert c.post("/api/community/posts", headers=A, json={"category": "Estrés", "title": "Hola", "body": "Primer mensaje"}).status_code == 400   # sin perfil
    assert c.put("/api/community/profile", headers=A, json={"alias": "Carla Pérez", "avatar": "p1"}).status_code == 422        # alias = nombre real
    assert c.put("/api/community/profile", headers=A, json={"alias": "ab", "avatar": "p1"}).status_code == 422
    assert c.put("/api/community/profile", headers=A, json={"alias": "Luna Serena", "avatar": "p9"}).status_code == 422
    assert c.put("/api/community/profile", headers=A, json={"alias": "Nube Azul", "avatar": "p3"}).status_code == 200
    assert c.put("/api/community/profile", headers=B, json={"alias": "nube azul", "avatar": "p2"}).status_code == 409           # alias único
    photo = "data:image/jpeg;base64," + "A" * 400
    assert c.put("/api/community/profile", headers=B, json={"alias": "Gato Zen", "avatar": photo}).status_code == 200
    post = c.post("/api/community/posts", headers=A, json={"category": "Sueño", "title": "No duermo bien", "body": "Me cuesta dormir en semana de parciales"}).json()
    assert post["support"] is False
    assert c.post(f"/api/community/posts/{post['id']}/comments", headers=B, json={"body": "A mí me ayudó la respiración 4-6"}).status_code == 200
    lst = c.get("/api/community/posts?q=cuesta%20dormir%20en%20semana", headers=A).json()["posts"]
    assert len(lst) == 1 and lst[0]["alias"] == "Nube Azul" and lst[0]["comments"] == 1 and "Carla" not in str(lst)       # anónimo
    assert c.get("/api/community/posts?q=zzzzzz", headers=A).json()["posts"] == []
    assert c.get("/api/community/posts?q=100%25", headers=A).status_code == 200                                               # % no rompe la búsqueda
    d = c.get(f"/api/community/posts/{post['id']}", headers=B).json()
    assert d["comments"][0]["alias"] == "Gato Zen" and d["comments"][0]["avatar"].startswith("data:image") and d["comments"][0]["mine"] is True
    cr = c.post("/api/community/posts", headers=B, json={"category": "Ánimo", "title": "Mal día", "body": "A veces pienso en quitarme la vida"}).json()
    assert cr["support"] is True and cr["resources"]                                                                          # recibe ayuda
    assert c.delete(f"/api/community/posts/{post['id']}", headers=B).status_code == 404                                       # no es suyo
    PH, _ = login(c, "psicologo1", "PsicoDemo2026!")
    assert c.get("/api/community/posts", headers=PH).status_code == 200
    assert c.delete(f"/api/community/posts/{post['id']}", headers=PH).status_code == 200                                      # moderación
    assert all(p["id"] != post["id"] for p in c.get("/api/community/posts", headers=A).json()["posts"])
    assert wait(lambda: mocks.SHEETS["Foro_Publicaciones"].get(str(post["id"]), {}).get("oculto") == "1")
