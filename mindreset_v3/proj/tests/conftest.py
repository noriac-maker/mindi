import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pytest
import mocks

sheets_srv = mocks.start(mocks.SheetsHandler)
gem_srv = mocks.start(mocks.GeminiHandler)
TMP = tempfile.mkdtemp()
os.environ.update({
    "MINDRESET_DB": os.path.join(TMP, "t.db"), "MINDRESET_SYNC_INTERVAL": "0.3",
    "MINDRESET_SHEETS_URL": f"http://127.0.0.1:{sheets_srv.server_port}/exec", "MINDRESET_SHEETS_SECRET": mocks.SECRET,
    "MINDRESET_SEED_DEMO": "1", "GEMINI_API_KEY": "fake-key", "GEMINI_API_BASE": f"http://127.0.0.1:{gem_srv.server_port}/v1beta",
    "MINDRESET_APP_URL": "https://mindreset.test",
})
from fastapi.testclient import TestClient
import app as appmod


def wait(cond, secs=8):
    t = time.time()
    while time.time() - t < secs:
        if cond():
            return True
        time.sleep(0.1)
    return False


@pytest.fixture(scope="session")
def client():
    with TestClient(appmod.app) as c:
        yield c


def login(c, u, p):
    r = c.post("/api/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}, r.json()["user"]


CONSENTS = dict(consent_terms=True, consent_data=True, consent_visibility=True, consent_tool=True)


def new_student(c, username, name="Ana Prueba", email=None):
    r = c.post("/api/register", json={"username": username, "password": "clave12345", "display_name": name, "ciclo": 4, "carrera": "Psicología",
                                      "email": email or f"{username}@mail.test", **CONSENTS})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}, r.json()["user"]


ANS_HIGH = {"anxiety": "a3", "sleep_hours": "h0", "sleep_quality": "q1", "study_load": "l5", "stressor": "s_tasks", "wants_contact": "c_yes"}
ANS_LOW = {"anxiety": "a0", "sleep_hours": "h2", "sleep_quality": "q5", "study_load": "l1", "stressor": "s_none", "wants_contact": "c_no"}
