"""Chequeo profundo, señales de Mindi e informes del estudiante."""
import json
from datetime import date, datetime, timedelta
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import app as core
import deep
import survey as sv
from routes_calendar import today_local, user_events

router = APIRouter()
student = core.require_roles("student")


def _latest_two(con, uid):
    rows = con.execute("SELECT * FROM checkins WHERE student_id=? ORDER BY id DESC LIMIT 6", (uid,)).fetchall()
    return [core.shape_checkin(r, include_note=False) for r in rows]


def signals_for(con, uid):
    today = today_local()
    cis = _latest_two(con, uid)
    evs = [{k: r[k] for k in ("start_at", "end_at", "kind")} for r in user_events(con, uid, today.isoformat(), (today + timedelta(days=8)).isoformat())]
    return deep.compute_signals(cis, evs, today), cis, evs


@router.get("/api/signals")
def my_signals(user=Depends(student)):
    con = core.db()
    sigs, _, _ = signals_for(con, user["id"])
    con.close()
    return [{"id": s["id"], "level": s["level"], "text": s["student"]} for s in sigs]


class QuestionsReq(BaseModel):
    chat: List[str] = Field(default_factory=list, max_length=12)


@router.post("/api/deep/questions")
def deep_questions(data: QuestionsReq, user=Depends(student)):
    con = core.db()
    _, cis, evs = signals_for(con, user["id"])
    con.close()
    if not cis:
        raise HTTPException(400, "Primero completa la encuesta del día.")
    c = cis[0]
    sched = deep.schedule_summary(evs, today_local())
    chat = [t[:300] for t in data.chat][-8:]
    questions, source = deep.build_questions(c["answers"], c["features"], c["label"], sched, chat)
    return {"questions": questions, "source": source}


class SubmitReq(BaseModel):
    questions: List[dict] = Field(min_length=3, max_length=3)
    answers: Dict[str, str]


@router.post("/api/deep/submit")
def deep_submit(data: SubmitReq, user=Depends(student)):
    qa = []
    for q in data.questions:
        try:
            qid, title = str(q["id"]), str(q["title"])[:200]
            opts = {str(o["id"]): str(o["label"])[:90] for o in q["options"]}
        except Exception:
            raise HTTPException(422, "Formato de preguntas inválido.")
        pick = data.answers.get(qid)
        if pick not in opts:
            raise HTTPException(422, "Falta responder alguna pregunta.")
        qa.append({"qid": qid, "question": title, "answer": opts[pick], "tag": pick if pick in deep.REC else None})
    con = core.db()
    sigs, cis, evs = signals_for(con, user["id"])
    if not cis:
        con.close()
        raise HTTPException(400, "Primero completa la encuesta del día.")
    c = cis[0]
    sched = deep.schedule_summary(evs, today_local())
    prev = cis[1]["label"] if len(cis) > 1 else None
    first = user["display_name"].split()[0]
    result, source = deep.analyze(first, c["answers"], c["features"], c["label"], c["alert_level"], qa, sched, prev)
    cur = con.execute("""INSERT INTO reports(student_id,checkin_id,created_at,level,label,psych_report,student_summary,qa,recommendations,source)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""",
                      (user["id"], c["id"], core.now_iso(), c["alert_level"], c["label"], result["psych_report"], result["student_summary"],
                       json.dumps(qa, ensure_ascii=False), json.dumps(result["recommendations"], ensure_ascii=False), source))
    con.commit()
    con.close()
    core.SYNC_WAKE.set()
    return {"id": cur.lastrowid, "source": source, **result}


@router.get("/api/my-reports")
def my_reports(user=Depends(student)):
    con = core.db()
    rows = con.execute("SELECT * FROM reports WHERE student_id=? ORDER BY id DESC LIMIT 10", (user["id"],)).fetchall()
    con.close()
    return [{"id": r["id"], "created_at": r["created_at"], "label": r["label"], "student_summary": r["student_summary"], "psych_report": r["psych_report"],
             "recommendations": json.loads(r["recommendations"]), "qa": json.loads(r["qa"])} for r in rows]
