"""Encuesta de MindReset.

Cada pregunta muestra opciones descriptivas (nunca números). Las preguntas con
`feeds` alimentan al modelo; el resto es contexto para el psicólogo.

IMPORTANTE – escalas deducidas de los umbrales del árbol de decisión (.joblib);
confírmalas con el diccionario de datos del entrenamiento:
  * anxiety_level  (0–21): cada opción es el punto medio de una banda tipo GAD-7 (0–4, 5–9, 10–14, 15–21).
  * sleep_quality  (0–5):  0 = casi nada reparador … 5 = muy bueno (el árbol parte en 0.5 y 1.5).
  * study_load     (0–5):  0 = casi sin carga … 5 = desbordante (el árbol parte en 0.5, 1.5, 2.5 y 3.5).
Si el diccionario indica otra dirección o escala, cambia SOLO los `value` de aquí.
"""

QUESTIONS = [
    {
        "id": "anxiety",
        "feeds": "anxiety_level",
        "title": "En las últimas dos semanas, ¿con qué frecuencia te has sentido nervioso/a o preocupado/a por tus estudios y actividades?",
        "help": "Piensa en esos momentos en que la mente va a mil, el estómago se aprieta o cuesta relajarse.",
        "options": [
            {"id": "a0", "label": "Casi nunca", "hint": "La mayor parte del tiempo me siento tranquilo/a.", "value": 2},
            {"id": "a1", "label": "Algunos días", "hint": "Me pasa una o dos veces por semana, por ejemplo antes de un examen.", "value": 7},
            {"id": "a2", "label": "Más de la mitad de los días", "hint": "Varios días seguidos me cuesta relajarme.", "value": 12},
            {"id": "a3", "label": "Casi todos los días", "hint": "La preocupación me acompaña gran parte del día.", "value": 18},
        ],
    },
    {
        "id": "sleep_hours",
        "feeds": None,
        "title": "En promedio, ¿cuántas horas duermes por noche entre semana?",
        "help": "Cuenta solo el tiempo que realmente duermes, no el que pasas en la cama.",
        "options": [
            {"id": "h0", "label": "Entre 1 y 3 horas", "hint": "Duermo muy poco, a veces me quedo despierto/a toda la noche."},
            {"id": "h1", "label": "Entre 4 y 6 horas", "hint": "Duermo poco, sobre todo en semanas de exámenes."},
            {"id": "h2", "label": "Entre 7 y 9 horas", "hint": "Duermo lo que suele recomendarse."},
            {"id": "h3", "label": "Más de 9 horas", "hint": "Duermo mucho y aun así me cuesta levantarme."},
        ],
    },
    {
        "id": "sleep_quality",
        "feeds": "sleep_quality",
        "title": "¿Cómo describirías la calidad de tu sueño en este último tiempo?",
        "help": "Más allá de las horas: ¿descansas de verdad cuando duermes?",
        "options": [
            {"id": "q0", "label": "Casi no descanso", "hint": "Paso las noches en vela o duermo a ratos muy cortos.", "value": 0},
            {"id": "q1", "label": "Muy mala", "hint": "Casi siempre me cuesta dormirme o me despierto agotado/a.", "value": 1},
            {"id": "q2", "label": "Mala", "hint": "Me despierto varias veces o me levanto sin energía.", "value": 2},
            {"id": "q3", "label": "Regular", "hint": "Algunas noches descanso bien y otras no.", "value": 3},
            {"id": "q4", "label": "Buena", "hint": "Casi siempre me levanto con energía suficiente.", "value": 4},
            {"id": "q5", "label": "Muy buena", "hint": "Descanso profundo y despierto con ganas de empezar el día.", "value": 5},
        ],
    },
    {
        "id": "study_load",
        "feeds": "study_load",
        "title": "¿Qué tan pesada sientes tu carga de estudio (tareas, trabajos y evaluaciones) en estas semanas?",
        "help": "Piensa en lo que tienes pendiente ahora, no en un ciclo ideal.",
        "options": [
            {"id": "l0", "label": "Casi sin carga", "hint": "Tengo muy pocas tareas y bastante tiempo libre.", "value": 0},
            {"id": "l1", "label": "Muy ligera", "hint": "Cumplo con todo y aún me sobra tiempo para mí.", "value": 1},
            {"id": "l2", "label": "Manejable", "hint": "Estudio con regularidad, sin apuros y con tiempo para descansar.", "value": 2},
            {"id": "l3", "label": "Pesada, pero llevadera", "hint": "Estudio casi todos los días, aunque todavía me organizo.", "value": 3},
            {"id": "l4", "label": "Muy pesada", "hint": "Tengo varias entregas o exámenes juntos y sacrifico descanso.", "value": 4},
            {"id": "l5", "label": "Desbordante", "hint": "Siento que no llego a todo, por más que me esfuerce.", "value": 5},
        ],
    },
    {
        "id": "stressor",
        "feeds": None,
        "title": "Ahora mismo, ¿qué es lo que más te está pesando?",
        "help": "Elige lo que más se acerque; si hay varias cosas, la que pese más.",
        "options": [
            {"id": "s_exams", "label": "Exámenes y notas", "hint": "Miedo a no rendir lo esperado."},
            {"id": "s_tasks", "label": "Trabajos y entregas", "hint": "Muchas tareas a la vez o con fechas muy cercanas."},
            {"id": "s_time", "label": "Organizar mi tiempo", "hint": "No sé por dónde empezar o me distraigo con facilidad."},
            {"id": "s_money", "label": "Dinero o trabajo", "hint": "Pagos, pasajes o un trabajo que quita tiempo de estudio."},
            {"id": "s_people", "label": "Familia o relaciones", "hint": "Situaciones con personas cercanas que me preocupan."},
            {"id": "s_health", "label": "Salud o cansancio", "hint": "Me siento agotado/a o con molestias físicas."},
            {"id": "s_none", "label": "Nada en particular", "hint": "Me siento relativamente bien."},
        ],
    },
    {
        "id": "wants_contact",
        "feeds": None,
        "title": "¿Te gustaría que alguien del servicio de psicología te escriba para conversar?",
        "help": "Es totalmente voluntario. Tu respuesta no cambia tu resultado.",
        "options": [
            {"id": "c_no", "label": "No por ahora, gracias", "hint": "Prefiero seguir por mi cuenta."},
            {"id": "c_maybe", "label": "Tal vez más adelante", "hint": "Quiero pensarlo con calma."},
            {"id": "c_yes", "label": "Sí, me gustaría que me contacten", "hint": "Me vendría bien hablar con una persona."},
        ],
    },
]

QUESTION_BY_ID = {q["id"]: q for q in QUESTIONS}
FEATURES = ("anxiety_level", "sleep_quality", "study_load")

STRESS_LABELS = {0: "Sin estrés", 1: "Eustrés", 2: "Angustia"}
STRESS_DESCRIPTIONS = {
    0: "Hoy no se ven señales de estrés que te estén pesando.",
    1: "Tienes un estrés manejable: de ese que activa y ayuda a cumplir metas, mientras no se acumule.",
    2: "El estrés está pesando más de lo cómodo. Mereces apoyo y descanso, y no tienes que resolverlo solo/a.",
}


def public_survey():
    """Versión para el navegador: sin valores numéricos del modelo."""
    return [
        {
            "id": q["id"],
            "title": q["title"],
            "help": q["help"],
            "options": [{"id": o["id"], "label": o["label"], "hint": o["hint"]} for o in q["options"]],
        }
        for q in QUESTIONS
    ]


def validate_answers(answers):
    """Devuelve (answers_limpias, error)."""
    if not isinstance(answers, dict):
        return None, "Formato de respuestas inválido."
    clean = {}
    for q in QUESTIONS:
        oid = answers.get(q["id"])
        if oid is None:
            return None, "Falta responder: " + q["title"]
        if not any(o["id"] == oid for o in q["options"]):
            return None, "Opción inválida en una de las preguntas."
        clean[q["id"]] = oid
    return clean, None


def option(qid, oid):
    for o in QUESTION_BY_ID[qid]["options"]:
        if o["id"] == oid:
            return o
    return None


def answers_to_features(answers):
    feats = {}
    for q in QUESTIONS:
        if q["feeds"]:
            feats[q["feeds"]] = float(option(q["id"], answers[q["id"]])["value"])
    return feats


def readable_answers(answers):
    """Lista legible para el panel del psicólogo."""
    out = []
    for q in QUESTIONS:
        oid = (answers or {}).get(q["id"])
        o = option(q["id"], oid) if oid else None
        out.append({
            "qid": q["id"],
            "question": q["title"],
            "answer": o["label"] if o else "—",
            "hint": o["hint"] if o else "",
            "feeds_model": bool(q["feeds"]),
            "position": [i for i, x in enumerate(q["options"]) if x["id"] == oid][0] if o else None,
            "total_options": len(q["options"]),
        })
    return out


# --- Capa de seguridad sobre el modelo ---------------------------------------------------------
# El árbol suministrado no es monótono (p. ej. ansiedad casi diaria + buen sueño + poca carga → «Sin
# estrés»). Para no tranquilizar en falso a quien reporta señales claras, estas reglas pueden SUBIR la
# alerta/nivel, nunca bajarlos. Son transparentes y el psicólogo ve tanto el valor del modelo como el ajuste.
SIGNAL_POINTS = {
    "anxiety": {"a2": 2, "a3": 3},
    "sleep_quality": {"q0": 3, "q1": 2, "q2": 1},
    "study_load": {"l5": 2, "l4": 1},
}
SIGNAL_NAMES = {"anxiety": "Preocupación", "sleep_quality": "Sueño", "study_load": "Carga"}
FLOOR_TO_CLASS = {"bajo": 0, "medio": 1, "alto": 2}


def signal_floor(answers):
    """Devuelve (nivel_mínimo, razones). Medio con ≥3 puntos, alto con ≥6."""
    pts, reasons = 0, []
    for qid, table in SIGNAL_POINTS.items():
        p = table.get((answers or {}).get(qid), 0)
        if p:
            pts += p
            reasons.append(f"{SIGNAL_NAMES[qid]}: {option(qid, answers[qid])['label'].lower()}")
    return ("alto" if pts >= 6 else "medio" if pts >= 3 else "bajo"), reasons
