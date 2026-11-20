"""Restauración completa desde la hoja con una base local vacía."""
import os
from conftest import *
import mocks, app as appmod
from fastapi.testclient import TestClient


def test_restore_everything_from_sheet(client):
    assert wait(lambda: client.get("/health").json()["google_sheets"]["pending_rows"] == 0)
    expected = {k: len(v) for k, v in mocks.SHEETS.items()}
    appmod.TOKENS.clear()
    os.environ["MINDRESET_DB"] = os.path.join(TMP, "nueva.db"); appmod.DB_PATH = os.environ["MINDRESET_DB"]
    with TestClient(appmod.app) as c2:
        con = appmod.db()
        counts = {t: con.execute(f"select count(*) from {t}").fetchone()[0] for t in ("users", "checkins", "events", "reports", "posts", "comments")}
        con.close()
        assert counts["users"] == expected["Usuarios"] and counts["checkins"] == expected["Encuestas"] and counts["events"] == expected["Calendario"]
        assert counts["reports"] == expected["Informes"] and counts["posts"] == expected["Foro_Publicaciones"] and counts["comments"] == expected["Foro_Comentarios"]
        H, me = login(c2, "deep.user", "clave12345")
        assert me["email"].endswith("@mail.test") and c2.get("/api/my-reports", headers=H).json()
        H, me = login(c2, "com.b", "clave12345")
        assert me["alias"] == "Gato Zen" and me["avatar"].startswith("data:image")
        assert wait(lambda: c2.get("/health").json()["google_sheets"]["pending_rows"] == 0)
        assert {k: len(v) for k, v in mocks.SHEETS.items()} == expected            # no duplicó nada
