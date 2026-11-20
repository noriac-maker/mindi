"""Flujo base (encuesta, roles, panel, Sheets, chat, crisis)."""
from conftest import *
import mocks, app as appmod


def test_base_flow(client):
    c = client
    assert c.get("/health").json()["model_loaded"]
    assert wait(lambda: len(mocks.SHEETS["Usuarios"]) >= 20 and len(mocks.SHEETS["Encuestas"]) >= 10)
    row = next(iter(mocks.SHEETS["Encuestas"].values()))
    assert row["nivel_estres"] in ("Sin estrés", "Eustrés", "Angustia") and row["resp_ansiedad"]

    # consentimientos y validación de registro
    base = dict(username="xuser1", password="clave12345", display_name="X Y", ciclo=4, carrera="Psi", email="x1@mail.test", **CONSENTS)
    for k in CONSENTS:
        assert c.post("/api/register", json={**base, k: False}).status_code == 400
    assert c.post("/api/register", json={**base, "email": "no-es-correo"}).status_code == 422
    H, me = new_student(c, "ana.test")
    assert me["email"] == "ana.test@mail.test" and me["email_verified"] is False and me["checked_today"] is False
    assert c.post("/api/register", json={**base, "username": "Ana.Test"}).status_code == 409

    qs = c.get("/api/survey", headers=H).json()["questions"]
    assert len(qs) == 6 and all("value" not in o for q in qs for o in q["options"])
    assert c.post("/api/checkins", headers=H, json={"answers": {**ANS_HIGH, "anxiety": "zzz"}}).status_code == 422
    res = c.post("/api/checkins", headers=H, json={"answers": ANS_HIGH}).json()
    assert res["label"] == "Angustia" and res["tips"]
    low = c.post("/api/checkins", headers=H, json={"answers": ANS_LOW}).json()
    assert low["predicted_class"] <= res["predicted_class"]

    assert c.get("/api/students", headers=H).status_code == 403
    PH, _ = login(c, "psicologo1", "PsicoDemo2026!")
    d = c.get("/api/dashboard", headers=PH).json()
    assert d["students_with_checkin"] >= 7 and d["by_ciclo"] and "mindi_alerts" in d
    lst = c.get("/api/students", headers=PH).json()
    sid = next(s["student_id"] for s in lst if s["name"] == "Ana Prueba")
    det = c.get(f"/api/students/{sid}", headers=PH).json()
    assert len(det["checkins"]) == 2 and det["checkins"][0]["plan"] and det["progress"]["n"] == 2 and det["progress"]["direction"] == "mejora"

    assert c.post("/api/contact-request", headers=H).status_code == 200
    cid = det["checkins"][0]["id"]
    assert c.patch(f"/api/checkins/{cid}", headers=PH, json={"reviewed": True, "psych_note": "=cmd|' /C calc'!A0 Contacté"}).status_code == 200
    assert wait(lambda: mocks.SHEETS["Encuestas"].get(str(cid), {}).get("revisado") == "1")
    assert wait(lambda: c.get("/health").json()["google_sheets"]["pending_rows"] == 0)
    assert "'=cmd" in c.get("/api/export.csv", headers=PH).text

    # chat: Gemini simulado, crisis, respaldo y límite
    ch = c.post("/api/chat", headers=H, json={"message": "Tengo examen mañana", "history": [{"role": "bot", "text": "hola!"}, {"role": "user", "text": "hola"}]}).json()
    assert ch["source"] == "gemini" and ch["suggestions"] and ch["offer_support"] is False
    g = mocks.GEMINI_REQUESTS[-1]
    assert [t["role"] for t in g["body"]["contents"]] == ["user"] and "Ana" in g["body"]["systemInstruction"]["parts"][0]["text"]
    n = len(mocks.GEMINI_REQUESTS)
    cr = c.post("/api/chat", headers=H, json={"message": "a veces pienso en quitarme la vida"}).json()
    assert cr["crisis"] and "113" in cr["reply"] and len(mocks.GEMINI_REQUESTS) == n
    saved = appmod.chatbot.GEMINI_API_KEY
    appmod.chatbot.GEMINI_API_KEY = "mala"
    assert c.post("/api/chat", headers=H, json={"message": "no puedo dormir"}).json()["source"] == "basic"
    appmod.chatbot.GEMINI_API_KEY = saved
