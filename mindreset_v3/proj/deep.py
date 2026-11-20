"""Chequeo profundo de Mindi: 3 preguntas personalizadas, análisis, recomendaciones con actividades para el
calendario, informe corto para psicología y señales de alerta.

Con GEMINI_API_KEY, Gemini redacta preguntas y análisis; sin clave (o si falla) se usan reglas transparentes.
A Gemini nunca se envían nombres de eventos del calendario, solo cifras agregadas.
"""
from datetime import date, datetime, timedelta

import chatbot
import survey as sv
from planner import KINDS, to_min, DAYS

# ------------------------------------------------------------------ banco de preguntas (modo reglas)
# topic -> (título, ayuda, [(tag, etiqueta, pista)])
QB = {
    "sleep_pre": ("Cuando se acerca la hora de dormir, ¿qué suele pasarte?", "Elige lo que más se parezca a tus noches.",
                  [("screens", "Me quedo con el celular o series hasta tarde", "Redes, videos o juegos"),
                   ("worry", "Mi mente repasa preocupaciones", "Pendientes, dudas o miedos"),
                   ("late_study", "Termino tareas muy tarde", "Estudio o trabajo hasta la madrugada"),
                   ("env", "El ambiente no ayuda", "Ruido, luz o poco espacio"),
                   ("unknown", "No lo sé, simplemente no logro dormir", "No identifico un motivo claro")]),
    "anxiety_when": ("¿En qué momentos se siente más fuerte tu preocupación?", "Piensa en la última semana.",
                     [("before_exam", "Antes de exámenes o exposiciones", "Me aceleran los nervios"),
                      ("reviewing", "Al revisar todo lo que tengo pendiente", "La lista me abruma"),
                      ("night", "Por la noche, cuando todo se calma", "Los pensamientos se multiplican"),
                      ("group", "En trabajos grupales", "Dependo de otros para avanzar"),
                      ("no_reason", "Sin un motivo claro", "Aparece de pronto")]),
    "task_hard": ("De tus tareas y trabajos, ¿qué se te hace más difícil?", "Elige lo más frecuente.",
                  [("start", "Empezar", "Postergo y luego me agobio"),
                   ("finish", "Terminar a tiempo", "Me falta tiempo al final"),
                   ("understand", "Entender el tema", "Siento que no lo domino"),
                   ("group", "Coordinar con mi grupo", "Cuesta ponernos de acuerdo"),
                   ("amount", "La cantidad total", "Son demasiadas cosas a la vez")]),
    "exam_prep": ("Cuando te preparas para una evaluación, ¿cómo sueles estudiar?", "No hay respuestas incorrectas.",
                  [("last_minute", "Me concentro en los últimos días", "Estudio mucho de golpe"),
                   ("plan_ok", "Reparto el estudio con anticipación", "Me siento bastante organizado/a"),
                   ("memorize", "Memorizo y releo apuntes", "Repaso una y otra vez"),
                   ("blank", "Me bloqueo durante la prueba", "Se me va lo estudiado")]),
    "work_hours": ("¿Cuántas horas a la semana dedicas a trabajar o ayudar en un negocio?", "Incluye trabajos informales.",
                   [("w0", "No trabajo", "Me dedico solo a estudiar"), ("w1", "Menos de 10 horas", "Algo ocasional"),
                    ("w2", "Entre 10 y 20 horas", "Medio tiempo"), ("w3", "Más de 20 horas", "Casi un trabajo completo")]),
    "support": ("Cuando algo te preocupa, ¿con quién sueles hablar?", "Contar con alguien protege mucho.",
                [("friends", "Con amigos o compañeros", "Me escuchan y me entienden"), ("family", "Con mi familia", "Confío en ellos"),
                 ("tutor", "Con un docente o tutor", "Busco orientación académica"), ("nobody", "Prefiero no contarlo a nadie", "Me lo guardo")]),
    "energy": ("¿Cómo ha estado tu energía durante el día?", "Piensa en cómo te sientes a media tarde.",
               [("tired_always", "Cansado/a casi todo el día", "Cuesta arrancar y mantenerme"), ("afternoon_drop", "Baja por la tarde", "Me da sueño o desgano"),
                ("aches", "Con molestias físicas", "Dolor de cabeza, espalda o estómago"), ("fine", "Bastante bien", "Me siento con energía")]),
    "schedule_heavy": ("Tu semana se ve muy cargada. ¿Qué te pasa en los días de más actividades?", "Mindi lo notó en tu calendario.",
                       [("no_pause", "Casi no tengo pausas", "Paso de una actividad a otra"), ("skip_meals", "Me salto comidas", "Como rápido o a deshoras"),
                        ("weekends", "Pierdo mis fines de semana", "Estudio o trabajo sábado y domingo"), ("flex", "Podría mover algunas cosas", "Tengo cierta flexibilidad")]),
    "rest_time": ("¿Cuánto tiempo libre real tienes en un día normal?", "Tiempo libre es el que no es estudio ni obligaciones.",
                  [("none", "Casi nada", "Todo el día está ocupado"), ("little", "Algo, pero lo uso con el celular", "Termino más cansado/a"),
                   ("enough", "Sí tengo y lo disfruto", "Me ayuda a recargar energía")]),
    "disconnect": ("¿Qué te ayuda más a desconectar?", "Lo que realmente te funciona.",
                   [("music", "Música o series", "Algo tranquilo"), ("sport", "Movimiento o deporte", "Caminar, correr o bailar"),
                    ("friends_time", "Tiempo con amigos o familia", "Conversar y reír"), ("nothing", "Aún no encuentro algo que me ayude", "Me cuesta desconectar")]),
    "meals": ("¿Cómo son tus comidas durante la semana?", "Comer a horas ayuda al ánimo y la concentración.",
              [("regular", "Como a mis horas", "Desayuno, almuerzo y cena"), ("skip", "Me salto alguna comida", "Casi siempre el desayuno o el almuerzo"),
               ("late", "Como muy tarde o muy rápido", "Sin tiempo para sentarme")]),
}

# tag -> (título, detalle, actividad para el calendario o None)
REC = {
    "screens": ("Apaga pantallas 30 minutos antes de dormir", "Pon una alarma suave a las 22:30 y deja el celular lejos de la cama. Puedes leer algo ligero o escuchar música tranquila.",
                {"title": "Pantallas apagadas y luces tenues", "kind": "sleep", "minutes": 30, "days": None, "time_pref": "22:30"}),
    "worry": ("Descarga mental de 10 minutos", "Antes de acostarte, anota en una hoja lo que te preocupa y el primer paso para mañana. Así tu mente no tiene que recordarlo de noche.",
              {"title": "Descarga mental (anota tus pendientes)", "kind": "rest", "minutes": 10, "days": None, "time_pref": "21:30"}),
    "late_study": ("Ponle una hora de cierre al estudio", "Decide una hora límite, por ejemplo 21:30, y deja lo que falte para mañana en tu lista. Dormir bien también mejora cómo aprendes.",
                   {"title": "Cierre del estudio del día", "kind": "other", "minutes": 15, "days": None, "time_pref": "21:30"}),
    "env": ("Prepara tu espacio para dormir", "Prueba tapones o música suave, cortinas que bloqueen la luz y un horario fijo. Pequeños cambios suman.", None),
    "unknown": ("Rutina corta antes de dormir", "Respira 4-6 (inhala 4 segundos, exhala 6) durante 5 repeticiones en la cama. Hazlo a la misma hora cada noche.",
                {"title": "Respiración 4-6 para dormir", "kind": "sleep", "minutes": 10, "days": None, "time_pref": "22:30"}),
    "before_exam": ("Simulacro corto antes de evaluar", "Dos días antes, resuelve 5 preguntas sin apuntes y practica la respiración 4-6 antes de entrar al examen.",
                    {"title": "Simulacro corto de preguntas", "kind": "study", "minutes": 30, "days": [0, 2, 4], "time_pref": "afternoon"}),
    "reviewing": ("Revisión semanal de pendientes", "Una vez por semana, ordena tus pendientes en «hoy / esta semana / puede esperar». Verlos en papel pesa menos que en la cabeza.",
                  {"title": "Revisión semanal de pendientes", "kind": "other", "minutes": 20, "days": [6], "time_pref": "18:00"}),
    "night": ("Respiración 4-6 por la noche", "Cuando los pensamientos se multipliquen, inhala 4 segundos y exhala 6, cinco veces. Baja el ritmo del cuerpo antes de dormir.",
              {"title": "Respiración 4-6 de la noche", "kind": "rest", "minutes": 5, "days": None, "time_pref": "21:45"}),
    "group": ("Acuerdos claros con tu grupo", "Escribe en el chat del grupo quién hace qué y para cuándo. Por ejemplo: «¿Les parece si dividimos las partes hoy y revisamos el jueves?».",
              {"title": "Coordinación breve con el grupo", "kind": "other", "minutes": 15, "days": [1, 3], "time_pref": "afternoon"}),
    "no_reason": ("Pausas de respiración durante el día", "Cuando sientas la preocupación subir, haz 1 minuto de respiración 4-6. Programarlo ayuda a hacerlo hábito.",
                  {"title": "Pausa de respiración 4-6", "kind": "rest", "minutes": 5, "days": [0, 1, 2, 3, 4], "time_pref": "10:30"}),
    "start": ("Empieza solo 15 minutos", "Elige la tarea más pequeña y trabaja 15 minutos con el celular lejos. Lo difícil es arrancar; después suele fluir.",
              {"title": "Arranque de 15 minutos", "kind": "study", "minutes": 15, "days": [0, 1, 2, 3, 4], "time_pref": "afternoon"}),
    "finish": ("Fechas intermedias para tus entregas", "Divide cada entrega en partes y ponles fecha propia. Por ejemplo: esquema el lunes, borrador el miércoles, revisión el jueves.",
               {"title": "Bloque de avance de entregas", "kind": "study", "minutes": 45, "days": [1, 3], "time_pref": "afternoon"}),
    "understand": ("Pide una tutoría breve", "Escríbele a tu docente: «Profesor/a, ¿podría orientarme 15 minutos con el tema X? Me trabo en la parte Y».", None),
    "amount": ("Quédate con tres prioridades al día", "Cada mañana elige solo tres cosas que sí o sí harás hoy; el resto puede esperar.",
               {"title": "Planificar el día (3 prioridades)", "kind": "other", "minutes": 10, "days": [0, 1, 2, 3, 4], "time_pref": "09:00"}),
    "last_minute": ("Reparte el estudio en tres días", "En vez de estudiar todo al final, haz tres sesiones de 50 minutos en días distintos. Recordarás más con menos desgaste.",
                    {"title": "Sesión de estudio repartido", "kind": "study", "minutes": 50, "days": [0, 2, 4], "time_pref": "afternoon"}),
    "memorize": ("Repaso espaciado y con preguntas", "Después de leer, cierra el cuaderno y explícate el tema en voz alta. Repite al día siguiente: refuerza la memoria.",
                 {"title": "Repaso espaciado", "kind": "study", "minutes": 25, "days": [1, 3, 5], "time_pref": "afternoon"}),
    "blank": ("Calma antes de rendir", "Antes de empezar un examen, haz 5 respiraciones 4-6 y lee todo primero. Empieza por la pregunta que mejor domines.",
              {"title": "Simulacro corto de preguntas", "kind": "study", "minutes": 30, "days": [2, 4], "time_pref": "afternoon"}),
    "w2": ("Cuida un bloque de descanso al día", "Con trabajo y estudio juntos, protege 45 minutos solo para ti. Además, consulta en bienestar si existen apoyos para estudiantes que trabajan.",
           {"title": "Descanso protegido", "kind": "rest", "minutes": 45, "days": None, "time_pref": "evening"}),
    "w3": ("Cuida un bloque de descanso al día", "Con tantas horas de trabajo, tu descanso es prioridad. Consulta en bienestar por apoyos para estudiantes que trabajan.",
           {"title": "Descanso protegido", "kind": "rest", "minutes": 45, "days": None, "time_pref": "evening"}),
    "nobody": ("No tienes que cargarlo solo/a", "Puedes escribir en la Comunidad anónima o pedir que psicología te escriba. Contar lo que sientes, aunque sea a una persona, alivia.", None),
    "friends": ("Un mensaje breve a alguien de confianza", "Escribe: «¿Tienes un ratito para conversar? Ando algo cargado/a». Dos o tres veces por semana ayuda.",
                {"title": "Conversar con alguien de confianza", "kind": "other", "minutes": 15, "days": [2, 5], "time_pref": "evening"}),
    "family": ("Un mensaje breve a alguien de confianza", "Escribe: «¿Tienes un ratito para conversar? Ando algo cargado/a». Dos o tres veces por semana ayuda.",
               {"title": "Conversar con alguien de confianza", "kind": "other", "minutes": 15, "days": [2, 5], "time_pref": "evening"}),
    "tutor": ("Agenda una tutoría", "Un docente o tutor puede ayudarte a priorizar y a ver si hay flexibilidad en fechas.", None),
    "tired_always": ("Pausas de movimiento de 10 minutos", "Levántate, estírate y toma agua entre bloques. Si el cansancio dura semanas, consulta con un profesional de salud.",
                     {"title": "Pausa de movimiento", "kind": "rest", "minutes": 10, "days": [0, 1, 2, 3, 4], "time_pref": "11:00"}),
    "afternoon_drop": ("Pausa activa a media tarde", "Camina 10 a 15 minutos o estírate cuando baje tu energía. Suele rendir más que insistir sentado/a.",
                       {"title": "Pausa activa de la tarde", "kind": "rest", "minutes": 15, "days": [0, 1, 2, 3, 4], "time_pref": "15:30"}),
    "aches": ("Cuida las molestias del cuerpo", "Si las molestias se repiten, conviene una consulta médica. Mientras, alterna posturas y haz pausas cada hora.", None),
    "no_pause": ("Mini pausas de 10 minutos", "Entre actividades, tómate 10 minutos sin pantalla. Hacen que rindas mejor en las siguientes horas.",
                 {"title": "Mini pausa", "kind": "rest", "minutes": 10, "days": [0, 1, 2, 3, 4], "time_pref": "15:00"}),
    "skip_meals": ("Protege tus comidas", "Reserva tiempo real para comer. Una comida a horas mejora tu ánimo y tu concentración.",
                   {"title": "Almuerzo protegido", "kind": "meal", "minutes": 30, "days": [0, 1, 2, 3, 4], "time_pref": "13:30"}),
    "weekends": ("Un rato de fin de semana sin estudiar", "Reserva un bloque de descanso real el sábado o domingo. Volverás con más energía.",
                 {"title": "Tiempo libre sin estudio", "kind": "rest", "minutes": 120, "days": [5, 6], "time_pref": "afternoon"}),
    "none": ("45 minutos para ti cada día", "Aunque el día esté lleno, protege un espacio pequeño: caminar, música o conversar sin pantalla.",
             {"title": "Tiempo para mí", "kind": "rest", "minutes": 45, "days": None, "time_pref": "evening"}),
    "little": ("Descanso sin pantalla de 20 minutos", "Usa un rato para estirarte, mirar por la ventana o escuchar música sin celular. Recarga más que seguir en redes.",
               {"title": "Descanso sin pantalla", "kind": "rest", "minutes": 20, "days": None, "time_pref": "afternoon"}),
    "music": ("Tu espacio de música para desconectar", "Aprovecha lo que ya te funciona y ponle horario.",
              {"title": "Música para desconectar", "kind": "rest", "minutes": 30, "days": [1, 3, 5], "time_pref": "evening"}),
    "sport": ("Movimiento ligero esta semana", "Caminar 20 minutos o bailar una canción ayuda al ánimo y al sueño.",
              {"title": "Movimiento ligero", "kind": "rest", "minutes": 20, "days": [1, 3, 5], "time_pref": "afternoon"}),
    "friends_time": ("Tiempo con tu gente", "Agenda un momento para conversar y reír con amigos o familia.",
                     {"title": "Tiempo con amigos o familia", "kind": "rest", "minutes": 45, "days": [5], "time_pref": "afternoon"}),
    "nothing": ("Prueba una actividad de desconexión", "Elige algo simple por 20 minutos: caminar, dibujar o escuchar una playlist. Con probar dos o tres veces sabrás qué te sirve.",
                {"title": "Probar una actividad para desconectar", "kind": "rest", "minutes": 20, "days": [2, 4], "time_pref": "afternoon"}),
    "skip": ("Comidas a tus horas", "Programa tus comidas como si fueran clases: son parte de tu rendimiento.",
             {"title": "Comida protegida", "kind": "meal", "minutes": 30, "days": [0, 1, 2, 3, 4], "time_pref": "12:30"}),
    "late": ("Comidas a tus horas", "Intenta que tu última comida no sea muy tarde y que el almuerzo no sea apurado.",
             {"title": "Comida protegida", "kind": "meal", "minutes": 30, "days": [0, 1, 2, 3, 4], "time_pref": "13:00"}),
    # recomendaciones derivadas del formulario base
    "base_anxiety": ("Respiración 4-6 de 5 minutos", "Inhala contando hasta 4 y exhala contando hasta 6, cinco veces. Ayuda a bajar la activación del cuerpo.",
                     {"title": "Respiración 4-6", "kind": "rest", "minutes": 5, "days": [0, 1, 2, 3, 4], "time_pref": "16:30"}),
    "base_load": ("Un solo bloque enfocado de 25 minutos", "Trabaja 25 minutos en una sola tarea y descansa 5. Repite cuatro veces y haz una pausa larga.",
                  {"title": "Bloque enfocado 25/5", "kind": "study", "minutes": 30, "days": [0, 2, 4], "time_pref": "afternoon"}),
    "base_sleep": ("Hora fija para apagar el día", "Elige una hora para dejar las pantallas y respira 4-6 en la cama. Moverla 15 minutos antes ya suma.",
                   {"title": "Rutina para dormir", "kind": "sleep", "minutes": 30, "days": None, "time_pref": "22:30"}),
}

DRIVER = {"screens": "pantallas hasta tarde", "worry": "preocupaciones nocturnas", "late_study": "estudio hasta muy tarde", "env": "ambiente poco favorable para dormir",
          "unknown": "dificultad para dormir sin causa clara", "before_exam": "nervios antes de evaluaciones", "reviewing": "abrumo ante los pendientes",
          "night": "preocupación nocturna", "group": "trabajos grupales", "no_reason": "preocupación sin causa clara", "start": "dificultad para empezar tareas",
          "finish": "falta de tiempo al cierre de entregas", "understand": "dudas de comprensión", "amount": "cantidad de tareas",
          "last_minute": "estudio concentrado en últimos días", "memorize": "estudio por memorización", "blank": "bloqueo durante evaluaciones",
          "w2": "trabajo de 10 a 20 h semanales", "w3": "trabajo de más de 20 h semanales", "nobody": "poco apoyo percibido", "tired_always": "cansancio casi todo el día",
          "afternoon_drop": "baja de energía por la tarde", "aches": "molestias físicas", "no_pause": "agenda sin pausas", "skip_meals": "comidas saltadas",
          "weekends": "pierde sus fines de semana", "none": "casi sin tiempo libre", "little": "poco tiempo libre real", "nothing": "no encuentra cómo desconectar",
          "skip": "comidas saltadas", "late": "comidas tardías o apuradas"}


# ------------------------------------------------------------------ resumen del horario (solo cifras)
def schedule_summary(events, today):
    """events: dicts con start_at, end_at, kind. Considera los próximos 7 días."""
    load_kinds = {"class", "work", "transport", "study"}
    per_day, rest_days, deadlines, any_ev = {}, set(), [], False
    horizon = today + timedelta(days=7)
    for ev in events:
        try:
            d = date.fromisoformat(ev["start_at"][:10])
        except Exception:
            continue
        if not (today <= d < horizon):
            continue
        any_ev = True
        mins = max(0, to_min(ev["end_at"][11:16]) - to_min(ev["start_at"][11:16])) if ev["end_at"][:10] == ev["start_at"][:10] else 0
        if ev["kind"] in load_kinds:
            per_day[d] = per_day.get(d, 0) + mins
        if ev["kind"] == "rest":
            rest_days.add(d)
        if ev["kind"] in ("deadline", "exam"):
            deadlines.append(d)
    worst = max(per_day.items(), key=lambda kv: kv[1], default=(None, 0))
    avg = (sum(per_day.values()) / len(per_day) / 60) if per_day else 0
    return {"has_events": any_ev, "busy_avg_h": round(avg, 1), "busy_max_h": round(worst[1] / 60, 1),
            "busy_max_day": worst[0].isoformat() if worst[0] else None, "days_without_rest": len([d for d in per_day if d not in rest_days]),
            "deadlines": sorted(d.isoformat() for d in deadlines)}


# ------------------------------------------------------------------ preguntas personalizadas
def _opt(label_map, answers, qid):
    o = sv.option(qid, (answers or {}).get(qid)) if (answers or {}).get(qid) else None
    return o["label"] if o else ""


def _rule_topics(answers, feats, sched, chat_topics):
    sc = {}
    anx, sleep, load = feats["anxiety_level"], feats["sleep_quality"], feats["study_load"]
    stressor, hours = answers.get("stressor"), answers.get("sleep_hours")
    if sleep <= 2 or hours in ("h0", "h1"):
        sc["sleep_pre"] = 3
    if anx >= 12:
        sc["anxiety_when"] = 3
    elif anx >= 7:
        sc["anxiety_when"] = 1.2
    if load >= 4 or stressor in ("s_tasks", "s_time"):
        sc["task_hard"] = 2.6
    if stressor == "s_money":
        sc["work_hours"] = 3
    if stressor == "s_people":
        sc["support"] = 3
    if stressor == "s_health" or sleep <= 1:
        sc["energy"] = 2.5
    if stressor == "s_exams":
        sc["exam_prep"] = 2.6
    if sched.get("busy_max_h", 0) >= 10 or sched.get("busy_avg_h", 0) >= 8:
        sc["schedule_heavy"] = 2.9
    if sched.get("has_events") and sched.get("days_without_rest", 0) >= 2:
        sc["rest_time"] = 2.1
    boost = {"sleep": "sleep_pre", "anxiety": "anxiety_when", "exams": "exam_prep", "tasks": "task_hard", "focus": "energy", "mood": "support"}
    for t in chat_topics:
        if t in boost:
            sc[boost[t]] = sc.get(boost[t], 0) + 1.5
    for k, v in (("support", 1.2), ("disconnect", 1.0), ("rest_time", 0.9), ("meals", 0.8)):
        sc[k] = max(sc.get(k, 0), v)
    return [k for k, _ in sorted(sc.items(), key=lambda kv: -kv[1])][:3]


def _questions_from_topics(topics):
    out = []
    for t in topics:
        title, help_, opts = QB[t]
        out.append({"id": t, "title": title, "help": help_, "options": [{"id": tag, "label": lab, "hint": hint} for tag, lab, hint in opts]})
    return out


def _gemini_questions(answers, feats, label, sched, excerpt, topics):
    readable = {q["qid"]: q["answer"] for q in sv.readable_answers(answers)}
    prompt = (f"Nivel de estrés del último chequeo: {label}.\nRespuestas: preocupación={readable.get('anxiety')}; horas de sueño={readable.get('sleep_hours')}; "
              f"calidad de sueño={readable.get('sleep_quality')}; carga de estudio={readable.get('study_load')}; lo que más pesa={readable.get('stressor')}.\n"
              f"Horario próximo (cifras): {sched}.\nTemas que el estudiante mencionó en el chat: {topics or 'ninguno'}.\n"
              f"Fragmento reciente del chat (puede estar vacío): {excerpt[:1200]}\n\n"
              "Genera EXACTAMENTE 3 preguntas de seguimiento de opción múltiple, cada una con 3 a 5 opciones concretas, que profundicen en lo más relevante "
              "para ESTE estudiante y sirvan para recomendar acciones prácticas (sueño, carga, apoyo, descanso, hábitos). Evita preguntas clínicas, de diagnóstico o sobre "
              "autolesiones. Tono cálido, de tú, frases cortas. Cada opción lleva 'label' (corta) y 'hint' (explicación breve).")
    schema = {"type": "OBJECT", "properties": {"questions": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "title": {"type": "STRING"}, "help": {"type": "STRING"},
        "options": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"label": {"type": "STRING"}, "hint": {"type": "STRING"}}, "required": ["label"]}}},
        "required": ["title", "options"]}}}, "required": ["questions"]}
    data = chatbot.gemini_json("Eres Mindi, asistente de bienestar universitario en Perú. Respondes solo con JSON válido.", prompt, schema)
    qs = []
    for i, q in enumerate((data.get("questions") or [])[:3], 1):
        opts = [o for o in (q.get("options") or []) if str(o.get("label", "")).strip()][:5]
        if len(opts) < 2 or not str(q.get("title", "")).strip():
            continue
        qs.append({"id": f"g{i}", "title": str(q["title"]).strip()[:200], "help": str(q.get("help", "")).strip()[:160],
                   "options": [{"id": f"o{j}", "label": str(o["label"]).strip()[:90], "hint": str(o.get("hint", "")).strip()[:120]} for j, o in enumerate(opts, 1)]})
    if len(qs) != 3:
        raise ValueError("Gemini no devolvió 3 preguntas válidas")
    return qs


def build_questions(answers, feats, label, sched, chat_texts):
    """Devuelve (preguntas, fuente). chat_texts: mensajes del estudiante en la sesión actual (solo para elegir temas)."""
    topics = chatbot.chat_topics(chat_texts or [])
    if chatbot.gemini_available():
        try:
            return _gemini_questions(answers, feats, label, sched, " | ".join((chat_texts or [])[-6:]), topics), "gemini"
        except Exception:
            pass
    return _questions_from_topics(_rule_topics(answers, feats, sched, topics)), "basic"


# ------------------------------------------------------------------ análisis y recomendaciones
def _clean_cal(c):
    if not isinstance(c, dict) or not str(c.get("title", "")).strip():
        return None
    days = c.get("days")
    days = [d for d in days if isinstance(d, int) and 0 <= d <= 6] if isinstance(days, list) else None
    return {"title": str(c["title"]).strip()[:80], "kind": c.get("kind") if c.get("kind") in KINDS else "other",
            "minutes": max(5, min(int(c.get("minutes") or 15), 180)), "days": days or None, "time_pref": str(c.get("time_pref") or "afternoon")[:8]}


def _rule_analysis(first, answers, feats, label, alert, qa, sched, prev_label, psych_user_note=""):
    tags = [a["tag"] for a in qa if a.get("tag") in REC]
    recs, seen = [], set()

    def add(tag):
        t = REC[tag]
        if t[0] in seen:
            return
        seen.add(t[0])
        recs.append({"title": t[0], "detail": t[1], "calendar": t[2]})

    for tag in tags:
        add(tag)
    if feats["anxiety_level"] >= 12:
        add("base_anxiety")
    if feats["study_load"] >= 4:
        add("base_load")
    if feats["sleep_quality"] <= 2:
        add("base_sleep")
    recs = recs[:5] or [{"title": "Sigue con lo que te funciona", "detail": "Anota una cosa que hiciste bien esta semana y repítela.", "calendar": None}]

    drivers = [DRIVER[t] for t in tags if t in DRIVER][:3]
    base_drv = []
    if feats["sleep_quality"] <= 2 or answers.get("sleep_hours") in ("h0", "h1"):
        base_drv.append("sueño insuficiente")
    if feats["anxiety_level"] >= 12:
        base_drv.append("preocupación frecuente")
    if feats["study_load"] >= 4:
        base_drv.append("carga académica muy alta")
    all_drv = list(dict.fromkeys(base_drv + drivers))
    student = (f"Gracias por contarme más, {first}. "
               + (f"Lo que más parece pesar ahora: {', '.join(all_drv[:3])}. " if all_drv else "Te veo con un panorama bastante equilibrado. ")
               + f"Armé {len(recs)} idea{'s' if len(recs) != 1 else ''} pequeña{'s' if len(recs) != 1 else ''} para tu semana; "
               "puedes añadirlas a tu calendario con un toque.")
    sched_txt = ""
    if sched.get("has_events"):
        sched_txt = f" Horario: ~{sched['busy_avg_h']} h/día ocupadas (máx. {sched['busy_max_h']} h)"
        sched_txt += f"; {sched['days_without_rest']} día(s) sin descanso programado." if sched["days_without_rest"] else "."
    trend = ""
    if prev_label and prev_label != label:
        trend = f" Antes: {prev_label}."
    action = {"alto": "contacto cálido en 24–48 h (invitar, sin exigir)", "medio": "seguimiento en ~7 días", "bajo": "sin acción necesaria; refuerzo positivo"}[alert]
    psych = (f"Nivel {label} (atención {alert}).{trend} Factores: {', '.join(all_drv) if all_drv else 'sin factores destacados'}.{sched_txt} "
             f"Entregadas {len(recs)} recomendaciones de autocuidado. Sugerencia: {action}.")
    return {"student_summary": student, "psych_report": psych, "recommendations": recs}


def _gemini_analysis(first, answers, feats, label, alert, qa, sched, prev_label):
    readable = {q["qid"]: q["answer"] for q in sv.readable_answers(answers)}
    qa_txt = "; ".join(f"{a['question']} → {a['answer']}" for a in qa)
    prompt = (f"Estudiante: {first}. Nivel de estrés: {label} (atención {alert}); chequeo anterior: {prev_label or 'ninguno'}.\n"
              f"Formulario: preocupación={readable.get('anxiety')}; horas de sueño={readable.get('sleep_hours')}; calidad de sueño={readable.get('sleep_quality')}; "
              f"carga={readable.get('study_load')}; lo que más pesa={readable.get('stressor')}.\nPreguntas personalizadas: {qa_txt}\nHorario (cifras): {sched}.\n\n"
              "Devuelve: (1) student_summary: 2-3 frases cálidas dirigidas al estudiante; (2) psych_report: informe breve y puntual (máx. 70 palabras) para el profesional de psicología, "
              "factual, sin diagnóstico ni etiquetas clínicas, con factores, hábitos y siguiente paso sugerido; (3) recommendations: 3 a 5 recomendaciones concretas y pequeñas. "
              "Cada una con title, detail (con un ejemplo listo para usar) y calendar opcional {title, kind (class|study|work|transport|meal|rest|sleep|other), minutes, "
              "days (lista 0=lunes..6=domingo, o null para todos), time_pref ('morning'|'afternoon'|'evening' o 'HH:MM')}. No recomiendes medicación.")
    num = {"type": "NUMBER"}
    schema = {"type": "OBJECT", "properties": {
        "student_summary": {"type": "STRING"}, "psych_report": {"type": "STRING"},
        "recommendations": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "title": {"type": "STRING"}, "detail": {"type": "STRING"},
            "calendar": {"type": "OBJECT", "properties": {"title": {"type": "STRING"}, "kind": {"type": "STRING"}, "minutes": num,
                                                          "days": {"type": "ARRAY", "items": num}, "time_pref": {"type": "STRING"}}}},
            "required": ["title", "detail"]}}}, "required": ["student_summary", "psych_report", "recommendations"]}
    data = chatbot.gemini_json("Eres Mindi, asistente de bienestar universitario en Perú. No haces diagnósticos. Respondes solo con JSON válido.", prompt, schema, max_tokens=2200)
    recs = [{"title": str(r["title"]).strip()[:100], "detail": str(r["detail"]).strip()[:400], "calendar": _clean_cal(r.get("calendar"))}
            for r in (data.get("recommendations") or [])[:5] if str(r.get("title", "")).strip()]
    if not recs or not str(data.get("student_summary", "")).strip() or not str(data.get("psych_report", "")).strip():
        raise ValueError("Análisis de Gemini incompleto")
    return {"student_summary": str(data["student_summary"]).strip()[:600], "psych_report": str(data["psych_report"]).strip()[:700], "recommendations": recs}


def analyze(first, answers, feats, label, alert, qa, sched, prev_label=None):
    """qa: [{question, answer, tag}] → (resultado, fuente)."""
    if chatbot.gemini_available():
        try:
            return _gemini_analysis(first, answers, feats, label, alert, qa, sched, prev_label), "gemini"
        except Exception:
            pass
    return _rule_analysis(first, answers, feats, label, alert, qa, sched, prev_label), "basic"


# ------------------------------------------------------------------ señales de alerta
LEVEL_RANK = {"alert": 0, "warn": 1, "info": 2}


def compute_signals(checkins, events, today, now=None):
    """checkins: más reciente primero, dicts con predicted_class, label, created_at, answers.
    Devuelve [{id, level, student, psych}]; 'psych' solo usa cifras, nunca títulos de eventos."""
    out = []
    ci = checkins or []
    if len(ci) >= 2 and ci[0]["predicted_class"] > ci[1]["predicted_class"]:
        out.append({"id": "trend_up", "level": "warn",
                    "student": f"Tu nivel de estrés subió de {ci[1]['label']} a {ci[0]['label']}. Si quieres, armamos juntos un plan más liviano.",
                    "psych": f"Nivel subió de {ci[1]['label']} a {ci[0]['label']} respecto al registro anterior."})
    if len(ci) >= 3 and all(c["predicted_class"] >= 1 for c in ci[:3]) and sum(1 for c in ci[:3] if c["predicted_class"] == 2) >= 2:
        out.append({"id": "sustained_high", "level": "alert",
                    "student": "Llevas varios chequeos seguidos con estrés alto. Mereces apoyo: puedo avisar a psicología si lo deseas.",
                    "psych": "Estrés alto sostenido en los últimos 3 registros."})
    if ci:
        try:
            days = (today - datetime.fromisoformat(ci[0]["created_at"]).date()).days
        except Exception:
            days = 0
        if days >= 7:
            out.append({"id": "no_checkin", "level": "info", "student": f"Hace {days} días que no haces tu chequeo. ¿Hacemos uno rápido?",
                        "psych": f"Sin chequeos hace {days} días."})
    sched = schedule_summary(events or [], today)
    if sched["busy_max_h"] >= 11:
        d = date.fromisoformat(sched["busy_max_day"])
        out.append({"id": "overload_day", "level": "warn",
                    "student": f"El {DAYS[d.weekday()]} {d.strftime('%d/%m')} tendrás unas {sched['busy_max_h']} horas ocupadas. Conviene moverle algo o sumar una pausa.",
                    "psych": f"Día con ~{sched['busy_max_h']} h de actividades programadas en los próximos 7 días."})
    dl = sorted(date.fromisoformat(x) for x in sched["deadlines"])
    if any((dl[j] - dl[i]).days <= 2 for i in range(len(dl)) for j in range(i + 2, len(dl))):
        out.append({"id": "deadline_cluster", "level": "warn", "student": "Tienes varias entregas o exámenes muy juntos. Repartir el estudio desde hoy te va a aliviar.",
                    "psych": "Tres o más entregas/exámenes en un lapso de 3 días."})
    if sched["days_without_rest"] >= 3:
        out.append({"id": "no_rest", "level": "info", "student": "Veo varios días sin descanso programado. Un rato para ti también cuenta como tarea importante.",
                    "psych": f"{sched['days_without_rest']} días de la próxima semana sin descanso programado."})
    if ci and dl:
        a = ci[0].get("answers") or {}
        soon = [d for d in dl if 0 <= (d - today).days <= 3]
        if soon and (a.get("sleep_hours") in ("h0", "h1") or a.get("sleep_quality") in ("q0", "q1")):
            out.append({"id": "exam_low_sleep", "level": "alert", "student": "Tienes una entrega o examen cerca y estás durmiendo poco. Cuidar tu sueño hoy te ayudará más que estudiar de madrugada.",
                        "psych": "Entrega/examen en ≤3 días con sueño insuficiente reportado."})
    out.sort(key=lambda s: LEVEL_RANK[s["level"]])
    return out
