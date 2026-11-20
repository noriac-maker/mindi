"""Planificador de horario de MindReset.

Reparte compromisos fijos, transporte, comidas, descansos, rutina de sueño y sesiones de estudio
(repartidas en varios días antes de cada entrega) sin saturar al estudiante. Todo en hora local
(MINDRESET_TZ); las fechas se guardan como "YYYY-MM-DDTHH:MM".
"""
import math
import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import quote

DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
KINDS = {"class", "study", "work", "transport", "meal", "rest", "sleep", "deadline", "exam", "other"}
KIND_LABEL = {"class": "Clase", "study": "Estudio", "work": "Trabajo", "transport": "Transporte", "meal": "Comida",
              "rest": "Descanso", "sleep": "Sueño", "deadline": "Entrega", "exam": "Examen", "other": "Otra actividad"}

DEFAULT_PREFS = {"wake": "07:00", "sleep": "23:00", "transport_min": 0,
                 "breakfast": "07:30", "lunch": "13:00", "dinner": "20:00", "meal_min": 30,
                 "max_study_hours": 4, "session_min": 60, "rest_min": 60}


def to_min(hhmm):
    h, m = str(hhmm).split(":")[:2]
    return int(h) * 60 + int(m)


def to_hhmm(m):
    m = int(m)
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


def stamp(d, minute):
    if minute >= 1440:
        d, minute = d + timedelta(days=1), minute - 1440
    return f"{d.isoformat()}T{to_hhmm(minute)}"


def parse_stamp(s):
    d, t = s.split("T")
    return date.fromisoformat(d), to_min(t[:5])


def norm(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


# ------------------------------------------------------------------ estructura de un día
class Day:
    def __init__(self, d):
        self.d, self.busy, self.events, self.study = d, [], [], 0

    def free(self, s, e):
        return all(e <= bs or s >= be for bs, be in self.busy)

    def add(self, s, e, title, kind, notes="", block=True):
        self.events.append({"title": title, "kind": kind, "start_at": stamp(self.d, s), "end_at": stamp(self.d, e), "notes": notes})
        if block:
            self.busy.append((s, e))

    def find(self, length, windows, step=15):
        for ws, we in windows:
            t = ws
            while t + length <= we:
                if self.free(t, t + length):
                    return t
                t += step
        return None


def _clip(windows, lo, hi):
    out = []
    for a, b in windows:
        a, b = max(a, lo), min(b, hi)
        if b - a >= 15:
            out.append((a, b))
    return out


def _sizes(total_min, session):
    n = max(1, math.ceil(total_min / session))
    sizes = [session] * (n - 1) + [total_min - session * (n - 1)]
    if n > 1 and sizes[-1] < 20:
        sizes.pop()
        sizes[-1] = min(sizes[-1] + (total_min - session * (n - 1)), 90)
    return [int(s) for s in sizes]


def _load_existing(days, existing):
    by = {dy.d: dy for dy in days}
    for ev in existing or []:
        try:
            d1, s = parse_stamp(ev["start_at"])
            d2, e = parse_stamp(ev["end_at"])
        except Exception:
            continue
        if d1 in by:
            by[d1].busy.append((s, e if d2 == d1 else 1440))


# ------------------------------------------------------------------ generación del plan
def generate_plan(fixed, tasks, prefs, start, existing=None, mode="full"):
    """mode: 'full' (rutina completa + estudio) o 'tasks_only' (solo estudio, respetando lo existente)."""
    p = {**DEFAULT_PREFS, **{k: v for k, v in (prefs or {}).items() if v not in (None, "")}}
    wake, sleep = to_min(p["wake"]), to_min(p["sleep"])
    if sleep <= wake:
        sleep = 23 * 60
    awake = (wake, sleep - 30)
    T = max(0, min(int(float(p["transport_min"])), 180))
    meal_min = int(p["meal_min"])
    warnings = []

    clean_tasks = []
    for t in tasks or []:
        try:
            due = date.fromisoformat(t["due"])
            hours = max(0.5, min(float(t.get("hours") or 3), 40))
        except Exception:
            continue
        title = (t.get("title") or "Tarea").strip()[:80]
        kind = "exam" if t.get("kind") == "exam" else "deadline"
        if due < start:
            warnings.append(f"«{title}» tiene una fecha que ya pasó ({due.strftime('%d/%m')}); no se planificó.")
            continue
        clean_tasks.append({"title": title, "due": due, "hours": hours, "kind": kind,
                            "due_time": t.get("due_time") or ("08:00" if kind == "exam" else "18:00")})

    last = max([t["due"] for t in clean_tasks], default=start + timedelta(days=6))
    end = min(max(last, start + timedelta(days=6)), start + timedelta(days=27))
    days = [Day(start + timedelta(n)) for n in range((end - start).days + 1)]
    _load_existing(days, existing)

    meal_missing = {}
    if mode == "full":
        for dy in days:
            wd = dy.d.weekday()
            main = []
            for f in fixed or []:
                if wd in (f.get("days") or []):
                    s, e = to_min(f["start"]), to_min(f["end"])
                    if e <= s:
                        continue
                    kind = f.get("kind") if f.get("kind") in KINDS else "class"
                    dy.add(s, e, (f.get("title") or KIND_LABEL[kind])[:80], kind)
                    if kind in ("class", "work"):
                        main.append((s, e))
            if T and main:
                first, lastend = min(s for s, _ in main), max(e for _, e in main)
                dy.add(max(0, first - T), first, "Transporte (ida)", "transport", "Tiempo de traslado", block=True)
                dy.add(lastend, min(1440, lastend + T), "Transporte (vuelta)", "transport", "Tiempo de traslado", block=True)
            for name, key, default_off in (("Desayuno", "breakfast", 0), ("Almuerzo", "lunch", 0), ("Cena", "dinner", 0)):
                want = to_min(p[key])
                if key == "breakfast":
                    want = max(want, wake + 15)
                placed = False
                for off in [x for k in range(0, 181, 15) for x in ((k, -k) if k else (0,))]:
                    s = want + off
                    if awake[0] <= s and s + meal_min <= awake[1] + 30 and dy.free(s, s + meal_min):
                        dy.add(s, s + meal_min, name, "meal", "Come con calma, sin pantallas si puedes")
                        placed = True
                        break
                if not placed:
                    meal_missing.setdefault(name, []).append(f"{DAYS[wd][:3]} {dy.d.strftime('%d/%m')}")
            sleep_s = sleep - 30
            if dy.free(sleep_s, sleep):
                dy.add(sleep_s, sleep, "Rutina para dormir", "sleep", "Apaga pantallas, luces tenues y respira 4-6")
            else:
                warnings.append(f"El {DAYS[wd]} {dy.d.strftime('%d/%m')} tu agenda llega muy cerca de la hora de dormir.")
            rest = int(p["rest_min"])
            for length in (rest, 30):
                slot = dy.find(length, _clip([(17 * 60, 21 * 60), (14 * 60 + 30, 17 * 60), (9 * 60, 12 * 60)], *awake))
                if slot is not None:
                    dy.add(slot, slot + length, "Descanso / tiempo libre", "rest", "Tiempo para ti: caminar, música, amigos")
                    break
            else:
                warnings.append(f"El {DAYS[wd]} {dy.d.strftime('%d/%m')} no queda tiempo libre para descansar; conviene mover algo.")

    tips = {"Desayuno": "considera despertar 30 min antes o llevar algo para el camino",
            "Almuerzo": "reserva al menos 30 min libres a mediodía", "Cena": "intenta cenar antes de tu rutina para dormir"}
    for name, ds in meal_missing.items():
        warnings.append(f"No encontré espacio para {name.lower()} en: {', '.join(ds[:6])}{'…' if len(ds) > 6 else ''}. Para comer bien, {tips[name]}.")

    windows = _clip([(max(wake + 60, 8 * 60), 13 * 60), (15 * 60, 19 * 60), (19 * 60 + 30, min(22 * 60, sleep - 60))], *awake)
    cap_base = int(float(p["max_study_hours"]) * 60)
    per_task_day = {}
    for task in sorted(clean_tasks, key=lambda t: t["due"]):
        eligible = [dy for dy in days if dy.d < task["due"]] or [days[0]]
        if task["due"] == start:
            warnings.append(f"«{task['title']}» vence el primer día del plan: hay muy poco margen.")
        total = int(task["hours"] * 60)
        sizes = _sizes(total, int(p["session_min"]))
        unplaced = 0
        for i, size in enumerate(sizes, 1):
            cands = sorted(eligible, key=lambda dy: (dy.study + per_task_day.get((task["title"], dy.d), 0) * 0.5, dy.d))
            done = False
            for dy in cands:
                cap = cap_base * (0.6 if dy.d.weekday() >= 5 else 1)
                if dy.study + size > cap:
                    continue
                reserve = size + (10 if size >= 50 else 0)
                slot = dy.find(reserve, windows)
                if slot is None:
                    continue
                label = "Examen" if task["kind"] == "exam" else "Entrega"
                dy.add(slot, slot + size, f"Estudio: {task['title']}", "study", f"Sesión {i} de {len(sizes)} · prepara tu {label.lower()}")
                if size >= 50:
                    dy.add(slot + size, slot + size + 10, "Pausa corta", "rest", "Estírate, toma agua, mira lejos")
                dy.study += size
                per_task_day[(task["title"], dy.d)] = per_task_day.get((task["title"], dy.d), 0) + size
                done = True
                break
            if not done:
                unplaced += size
        if unplaced:
            warnings.append(f"No encontré espacio para {unplaced} min de «{task['title']}» antes del {task['due'].strftime('%d/%m')}. "
                            "Prueba subir las horas de estudio por día o pedir más plazo.")
        for dy in days:
            if dy.d == task["due"]:
                label = "Examen" if task["kind"] == "exam" else "Entrega"
                s = to_min(task["due_time"])
                dy.add(s, min(1440, s + 15), f"{label}: {task['title']}", task["kind"], "Fecha límite", block=False)

    events = sorted((ev for dy in days for ev in dy.events), key=lambda e: e["start_at"])
    study_h = sum((to_min(e["end_at"][11:]) - to_min(e["start_at"][11:])) for e in events if e["kind"] == "study") / 60
    rest_n = sum(1 for e in events if e["kind"] == "rest")
    return {"events": events, "warnings": warnings,
            "stats": {"days": len(days), "study_hours": round(study_h, 1), "rest_blocks": rest_n,
                      "start": start.isoformat(), "end": days[-1].d.isoformat()}}


def place_activities(items, start, existing, prefs=None, span=7):
    """Coloca actividades sugeridas (recomendaciones) en huecos libres de los próximos días."""
    p = {**DEFAULT_PREFS, **(prefs or {})}
    wake, sleep = to_min(p["wake"]), to_min(p["sleep"])
    awake = (wake, sleep)
    days = [Day(start + timedelta(n)) for n in range(span)]
    _load_existing(days, existing)
    pref_windows = {"morning": [(9 * 60, 12 * 60)], "afternoon": [(15 * 60, 18 * 60)], "evening": [(18 * 60 + 30, 21 * 60 + 30)]}
    added, skipped = [], []
    for it in items:
        title = str(it.get("title") or "Actividad")[:80]
        kind = it.get("kind") if it.get("kind") in KINDS else "other"
        mins = max(5, min(int(it.get("minutes") or 15), 180))
        wanted = it.get("days")
        pref = str(it.get("time_pref") or "afternoon")
        placed_any = False
        for dy in days:
            if wanted is not None and dy.d.weekday() not in wanted:
                continue
            if re.fullmatch(r"\d{1,2}:\d{2}", pref):
                want = to_min(pref)
                wins = [(want + off, want + off + mins) for off in (0, 15, -15, 30, -30, 60, -60, 90, -90)]
                slot = next((a for a, b in wins if awake[0] <= a and b <= awake[1] and dy.free(a, b)), None)
                if slot is None:
                    slot = dy.find(mins, _clip([(9 * 60, 21 * 60)], *awake))
            else:
                slot = dy.find(mins, _clip(pref_windows.get(pref, pref_windows["afternoon"]), *awake))
            if slot is None:
                continue
            dy.add(slot, slot + mins, title, kind, str(it.get("notes") or "Sugerido por Mindi"))
            placed_any = True
        if not placed_any:
            skipped.append(title)
    for dy in days:
        added.extend(dy.events)
    added.sort(key=lambda e: e["start_at"])
    return {"events": added, "skipped": skipped}


# ------------------------------------------------------------------ lectura de texto libre (modo básico)
_MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
           "setiembre": 9, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
_WD = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
_WD_RE = "|".join(_WD)


def _parse_date(t, today):
    if "pasado manana" in t:
        return today + timedelta(days=2)
    if re.search(r"\bmanana\b", t):
        return today + timedelta(days=1)
    if re.search(r"\bhoy\b", t):
        return today
    m = re.search(r"\b(\d{1,2})\s*(?:de\s+)?(" + "|".join(_MONTHS) + r")\b", t)
    if m:
        d = date(today.year, _MONTHS[m.group(2)], min(int(m.group(1)), 28 if _MONTHS[m.group(2)] == 2 else 30 if _MONTHS[m.group(2)] in (4, 6, 9, 11) else 31))
        return d if d >= today else d.replace(year=today.year + 1)
    m = re.search(r"\b(\d{1,2})/(\d{1,2})\b", t)
    if m and 1 <= int(m.group(2)) <= 12:
        try:
            d = date(today.year, int(m.group(2)), int(m.group(1)))
            return d if d >= today else d.replace(year=today.year + 1)
        except ValueError:
            pass
    m = re.search(r"\b(" + _WD_RE + r")\b", t)
    if m:
        delta = (_WD[m.group(1)] - today.weekday()) % 7
        return today + timedelta(days=delta or 7)
    m = re.search(r"\bel\s+(?:dia\s+)?(\d{1,2})\b", t)
    if m and 1 <= int(m.group(1)) <= 28:
        n = int(m.group(1))
        d = today.replace(day=n) if n >= today.day else (today.replace(day=1) + timedelta(days=32)).replace(day=n)
        return d
    return None


def _parse_days(t):
    if re.search(r"todos los dias|diario|cada dia", t):
        return list(range(7))
    if re.search(r"fin(?:es)? de semana", t):
        return [5, 6]
    m = re.search(r"(" + _WD_RE + r")\s+(?:a|hasta|al)\s+(" + _WD_RE + r")", t)
    if m:
        a, b = _WD[m.group(1)], _WD[m.group(2)]
        return list(range(a, b + 1)) if a <= b else list(range(a, 7)) + list(range(0, b + 1))
    found = sorted({_WD[w] for w in re.findall(r"\b(" + _WD_RE + r")s?\b", t)})
    return found


def _parse_range(t):
    m = re.search(r"(?:de|desde)\s+(?:las\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|h|hrs)?\s*(?:a|hasta|-)\s*(?:las\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|h|hrs)?", t)
    if not m:
        return None
    h1, m1, s1, h2, m2, s2 = int(m.group(1)), int(m.group(2) or 0), m.group(3), int(m.group(4)), int(m.group(5) or 0), m.group(6)
    if (s2 == "pm" or s1 == "pm") and h2 < 12:
        h2 += 12
    if s1 == "pm" and h1 < 12:
        h1 += 12
    if h2 <= h1 and h2 < 12 and not s2:
        h2 += 12
    if h1 > 23 or h2 > 24:
        return None
    return f"{h1:02d}:{m1:02d}", f"{min(h2, 24) % 24:02d}:{m2:02d}" if h2 < 24 else "23:59"


_TASK_WORDS = r"(tarea|trabajo|informe|proyecto|examen|exposicion|presentacion|practica|ensayo|parcial|quiz|laboratorio|monografia|prueba)"


def parse_text(text, today):
    """Lectura sencilla de frases como «tengo una tarea de estadística que se entrega el viernes (5 horas)».
    Devuelve {fixed, tasks, prefs, unparsed}. Con Gemini se usa un análisis más flexible."""
    out = {"fixed": [], "tasks": [], "prefs": {}, "unparsed": []}
    for raw in re.split(r"[.;\n]+", text or ""):
        sent = raw.strip()
        if len(sent) < 4:
            continue
        t = norm(sent)
        used = False

        m = re.search(r"(?:transporte|bus|metro|combi|viaje|trayecto|camino|traslado)[^\d]{0,40}(\d{1,3})\s*(min|minutos|hora|horas|h)\b", t)
        if m:
            mins = int(m.group(1)) * (60 if m.group(2).startswith("h") else 1)
            if re.search(r"ida y vuelta|total", t):
                mins //= 2
            out["prefs"]["transport_min"] = min(mins, 180)
            used = True

        m = re.search(r"(?:despierto|levanto)[^\d]{0,20}(\d{1,2})(?::(\d{2}))?", t)
        if m and int(m.group(1)) < 12:
            out["prefs"]["wake"] = f"{int(m.group(1)):02d}:{m.group(2) or '00'}"
            used = True
        m = re.search(r"(?:duermo|acuesto|dormir)[^\d]{0,20}(\d{1,2})(?::(\d{2}))?\s*(pm|am)?", t)
        if m:
            h = int(m.group(1)) + (12 if (m.group(3) == "pm" or int(m.group(1)) < 12 and not m.group(3) and int(m.group(1)) >= 8) and int(m.group(1)) < 12 else 0)
            if 20 <= h <= 24:
                out["prefs"]["sleep"] = f"{h % 24:02d}:{m.group(2) or '00'}"
                used = True

        has_task_word = re.search(r"\b" + _TASK_WORDS + r"\b", t)
        deadline = re.search(r"entrega|entregar|vence|plazo|fecha limite|hasta el|para el|es el|presento|rindo|tengo (?:un|una) (?:examen|parcial|prueba)", t)
        due = _parse_date(t, today) if (has_task_word or deadline) else None
        if has_task_word and due and (deadline or re.search(r"examen|parcial|prueba|quiz", t)):
            kind = "exam" if re.search(r"examen|parcial|prueba|quiz", t) else "task"
            mm = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:horas|hrs|h)\b", t)
            hours = float(mm.group(1).replace(",", ".")) if mm else (6 if kind == "exam" else 3)
            sm = re.search(r"\b" + _TASK_WORDS + r"\b(?:\s+(?:de|sobre|del|para)\s+([a-z0-9áéíóúñ ]+?))?(?:\s+(?:que|se|para|y|el|me|con|es|vence|tiene|toca)\b|,|$)", sent.lower())
            subject = (sm.group(2) or "").strip() if sm and sm.lastindex and sm.lastindex >= 2 else ""
            word = (sm.group(1) if sm else "tarea").capitalize()
            title = f"{word} de {subject}" if subject else word
            out["tasks"].append({"title": title[:60], "due": due.isoformat(), "hours": hours, "kind": "exam" if kind == "exam" else "task"})
            continue

        rng = _parse_range(t)
        days = _parse_days(t)
        if rng and days and not used:
            kind = "work" if re.search(r"trabaj|turno|empleo|oficina", t) else "class" if re.search(r"clase|curso|universidad|taller|laboratorio", t) else "other"
            title = {"work": "Trabajo", "class": "Clases", "other": sent[:40].capitalize()}[kind]
            out["fixed"].append({"title": title, "kind": kind, "days": days, "start": rng[0], "end": rng[1]})
            continue
        if not used:
            out["unparsed"].append(sent)
    return out


# ------------------------------------------------------------------ ICS y enlaces de Google Calendar
def to_utc(stamp_s, tz):
    d, m = parse_stamp(stamp_s)
    return datetime.combine(d, time(m // 60 % 24, m % 60)).replace(tzinfo=tz).astimezone(timezone.utc)


def _ics_escape(s):
    return str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line):
    out, b = [], line.encode("utf-8")
    while len(b) > 73:
        cut = 73
        while cut > 0 and (b[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(b[:cut].decode("utf-8"))
        b = b[cut:]
        b = b" " + b
    out.append(b.decode("utf-8"))
    return "\r\n".join(out)


def make_ics(events, tz, name="MindReset"):
    fmt = "%Y%m%dT%H%M%SZ"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MindReset//ES", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{_ics_escape(name)}", "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H"]
    now = datetime.now(timezone.utc).strftime(fmt)
    for ev in events:
        lines += ["BEGIN:VEVENT", f"UID:mindreset-{ev['id']}@mindreset", f"DTSTAMP:{now}",
                  f"DTSTART:{to_utc(ev['start_at'], tz).strftime(fmt)}", f"DTEND:{to_utc(ev['end_at'], tz).strftime(fmt)}",
                  f"SUMMARY:{_ics_escape(ev['title'])}", f"DESCRIPTION:{_ics_escape((ev.get('notes') or '') + ' · MindReset')}",
                  "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_escape(ev['title'])}", "TRIGGER:-PT15M", "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


def google_link(ev, tz):
    fmt = "%Y%m%dT%H%M%SZ"
    return ("https://calendar.google.com/calendar/render?action=TEMPLATE&text=" + quote(ev["title"])
            + "&dates=" + to_utc(ev["start_at"], tz).strftime(fmt) + "/" + to_utc(ev["end_at"], tz).strftime(fmt)
            + "&details=" + quote((ev.get("notes") or "") + " (MindReset)"))
