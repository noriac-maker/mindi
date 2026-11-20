"""Sugerencias basadas en reglas simples y transparentes.

Son ORIENTATIVAS: el psicólogo decide si interviene y cómo. Ninguna regla
implica diagnóstico. Se evita proponer acciones invasivas (llamadas no
solicitadas, avisar a terceros, etc.) salvo que el estudiante lo haya pedido.
"""

from survey import STRESS_LABELS


def _ans(checkin, qid):
    return (checkin.get("answers") or {}).get(qid)


def action_plan(checkin, previous=None):
    """checkin / previous: dicts con answers, predicted_class, alert_level, features."""
    cls = checkin["predicted_class"]
    alert = checkin["alert_level"]
    f = checkin.get("features") or {}
    anx, sleep, load = f.get("anxiety_level", 0), f.get("sleep_quality", 3), f.get("study_load", 2)
    hours = _ans(checkin, "sleep_hours")
    stressor = _ans(checkin, "stressor")
    wants = _ans(checkin, "wants_contact")

    actions = []

    if wants == "c_yes":
        actions.append({
            "tone": "priority",
            "title": "Pidió que lo/la contacten",
            "detail": "Escríbele en las próximas 48 horas. Es su decisión, así que basta un mensaje breve y cercano.",
        })
    elif wants == "c_maybe":
        actions.append({
            "tone": "soft",
            "title": "Dijo «tal vez más adelante»",
            "detail": "Respeta su ritmo. Puedes dejar una invitación abierta sin insistir.",
        })

    if alert == "alto":
        actions.append({
            "tone": "priority",
            "title": "Acercamiento cálido en 24–48 h",
            "detail": "Invítalo/a a conversar sin exigir respuesta. Ofrece una charla breve (20–30 min) en el formato que prefiera.",
        })
    elif alert == "medio":
        actions.append({
            "tone": "follow",
            "title": "Seguimiento en unos 7 días",
            "detail": "Pídele, con amabilidad, repetir la encuesta. Si el nivel sube, ahí conviene el acercamiento.",
        })
    else:
        actions.append({
            "tone": "ok",
            "title": "No requiere acción por ahora",
            "detail": "Si lo deseas, un mensaje breve de refuerzo positivo ayuda a mantener el hábito de registrarse.",
        })

    if sleep <= 2 or hours == "h0":
        actions.append({
            "tone": "soft",
            "title": "Conversar sobre su descanso",
            "detail": "Explora con curiosidad su rutina de sueño: horarios, pantallas, preocupaciones por la noche.",
        })
    if load >= 4 or stressor in ("s_tasks", "s_time"):
        actions.append({
            "tone": "soft",
            "title": "Ayudarle a organizar su carga",
            "detail": "Ofrece una guía simple para priorizar entregas. Solo si él/ella lo pide, coordina flexibilidad con tutoría.",
        })
    if anx >= 12:
        actions.append({
            "tone": "soft",
            "title": "Compartir una técnica de calma",
            "detail": "Por ejemplo respiración 4-6 (inhalar 4 s, exhalar 6 s) o una pausa activa de 5 minutos entre bloques de estudio.",
        })
    if stressor == "s_money":
        actions.append({
            "tone": "soft",
            "title": "Orientar sobre apoyos disponibles",
            "detail": "Revisa si existen becas, ayudas o servicios de bienestar de la institución que pueda considerar.",
        })
    elif stressor == "s_people":
        actions.append({
            "tone": "soft",
            "title": "Ofrecer un espacio de escucha",
            "detail": "Deja que cuente solo lo que quiera. Evita preguntas detalladas en el primer contacto.",
        })
    elif stressor == "s_health":
        actions.append({
            "tone": "soft",
            "title": "Sugerir revisión de salud si persiste",
            "detail": "Si el cansancio o las molestias continúan, recomienda una consulta médica además del apoyo psicológico.",
        })
    elif stressor == "s_exams":
        actions.append({
            "tone": "soft",
            "title": "Preparación para evaluaciones",
            "detail": "Comparte hábitos de estudio por bloques cortos y recuérdale que el descanso también mejora el rendimiento.",
        })

    if previous is not None:
        if cls > previous["predicted_class"]:
            actions.insert(1 if actions and actions[0]["tone"] == "priority" else 0, {
                "tone": "follow",
                "title": "Su nivel subió desde el registro anterior",
                "detail": f"Pasó de {STRESS_LABELS[previous['predicted_class']]} a {STRESS_LABELS[cls]}. Un check-in amable puede ser oportuno.",
            })
        elif cls < previous["predicted_class"]:
            actions.append({
                "tone": "ok",
                "title": "Mejoró respecto al registro anterior",
                "detail": f"Pasó de {STRESS_LABELS[previous['predicted_class']]} a {STRESS_LABELS[cls]}. Reconocer su avance puede motivarle.",
            })

    return actions[:6]


def suggested_message(first_name):
    return (
        f"Hola {first_name}, soy del servicio de psicología de la universidad. "
        "Quería saludarte y saber cómo vienes con este momento del ciclo. "
        "Si te apetece conversar, tengo espacio esta semana: puede ser una charla corta, "
        "presencial o virtual, como te resulte más cómodo. Sin ningún compromiso; "
        "y si prefieres no responder, también está bien. ¡Un abrazo!"
    )


def student_tips(checkin):
    """Consejos breves y concretos para el estudiante (nunca diagnósticos)."""
    f = checkin["features"]
    hours = _ans(checkin, "sleep_hours")
    stressor = _ans(checkin, "stressor")
    tips = []

    if f["anxiety_level"] >= 12:
        tips.append({
            "title": "Una pausa para calmar el cuerpo",
            "detail": "Prueba la respiración 4-6: inhala contando hasta 4, exhala contando hasta 6. Repítelo 5 veces antes de empezar a estudiar.",
        })
    if f["sleep_quality"] <= 2 or hours in ("h0", "h1"):
        tips.append({
            "title": "Cuida tu descanso esta semana",
            "detail": "Elige una hora fija para apagar pantallas, por ejemplo 30 minutos antes de dormir. Mover tu hora de dormir 15 minutos antes ya suma.",
        })
    if f["study_load"] >= 4 or stressor in ("s_tasks", "s_time"):
        tips.append({
            "title": "Divide lo pesado en pasos pequeños",
            "detail": "Escribe tus 3 entregas más cercanas y elige solo la primera. Por ejemplo: «hoy, 40 minutos para el esquema del informe».",
        })
    if stressor == "s_exams":
        tips.append({
            "title": "Estudia en bloques cortos",
            "detail": "25 minutos de estudio y 5 de descanso, cuatro veces, y luego una pausa más larga. Tu memoria lo agradece.",
        })
    if stressor == "s_money":
        tips.append({
            "title": "No cargues solo/a con lo económico",
            "detail": "Consulta en bienestar universitario si hay apoyos o becas. Preguntar no te compromete a nada.",
        })
    if stressor == "s_people":
        tips.append({
            "title": "Habla con alguien de confianza",
            "detail": "Contarle a una persona cercana, aunque sea en un mensaje corto, suele aliviar más de lo que parece.",
        })
    if not tips:
        tips.append({
            "title": "Sigue con lo que te funciona",
            "detail": "Anota una cosa que hiciste bien esta semana. Reconocerlo ayuda a mantener el ritmo.",
        })
    return tips[:3]
