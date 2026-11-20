"""Asistente conversacional «Mindi».

- Con GEMINI_API_KEY usa la API de Gemini (generateContent, REST).
- Sin clave, o si Gemini falla, responde en «modo básico» con consejos prácticos.
- Antes de cualquier modelo, detecta lenguaje de crisis y responde con recursos de ayuda.
"""
import json
import os
import re
import time
import unicodedata
import urllib.request
import urllib.error

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
# Si el modelo configurado no existe para tu clave (HTTP 404), se prueban estos en orden y se recuerda el que funcione.
_FALLBACK_MODELS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite"]
ACTIVE_MODEL = {"name": None}
GEMINI_API_BASE = os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")

# Recursos de ayuda (Perú). Revísalos periódicamente: los menús telefónicos cambian.
HELP_RESOURCES = {
    "lines": [
        {"name": "Línea 113 (Minsa)", "detail": "Gratuita, 24 horas. Pide la opción de salud mental.", "contact": "113"},
        {"name": "WhatsApp / Telegram Minsa", "detail": "Orientación en salud mental por mensaje.", "contact": "955 557 000"},
        {"name": "Emergencias", "detail": "Si hay peligro inmediato: Policía 105 · SAMU 106.", "contact": "105 / 106"},
    ],
}

SYSTEM_PROMPT = """Eres «Mindi», el asistente de bienestar de MindReset para estudiantes universitarios de Perú.

Cómo hablas:
- Español cercano y cálido, de tú. Frases cortas. Máximo 120 palabras.
- Primero valida lo que la persona siente en una frase; luego ofrece UNA o DOS ideas pequeñas y concretas.
- Siempre que sea útil, da un ejemplo listo para usar (una frase que pueda decirle a un profesor, un mini plan de 25 minutos, un ejercicio de respiración con tiempos).
- Termina con una sola pregunta suave para seguir conversando, o ninguna.

Límites:
- No eres psicólogo: no diagnostiques, no menciones trastornos como etiquetas ni recomiendes medicación.
- No des juicios ni sermones. No minimices («no es para tanto»).
- Si lo que cuenta es intenso, persistente o afecta su vida diaria, sugiere con calidez hablar con el servicio de psicología de su universidad.
- Si menciona hacerse daño, suicidio o violencia: valida, pide que se comunique ahora con la Línea 113 o con una persona de confianza, y no des ningún detalle sobre métodos.
- No inventes datos ni estadísticas. Si no sabes, dilo.
- Puedes usar **negritas** y listas con guiones, pero con moderación.

Formato de salida: JSON con "reply" (tu respuesta) y "suggestions" (2 o 3 frases cortas, de máximo 8 palabras, escritas en primera persona, que el estudiante podría tocar para continuar; por ejemplo «Tengo examen mañana y me bloqueo»)."""

CRISIS_PATTERNS = [
    r"suicid", r"quitarme la vida", r"quitarse la vida", r"matarme", r"no quiero vivir",
    r"no quiero seguir viviendo", r"acabar con mi vida", r"terminar con todo", r"terminar con mi vida",
    r"hacerme dano", r"hacerme daño", r"lastimarme", r"autolesion", r"cortarme las venas",
    r"mejor estar muerto", r"mejor estar muerta", r"ya no vale la pena vivir", r"no vale la pena vivir",
    r"quiero morir", r"quisiera morir", r"desaparecer para siempre",
]
_CRISIS_RE = re.compile("|".join(CRISIS_PATTERNS), re.IGNORECASE)


def _norm(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def is_crisis(text):
    return bool(_CRISIS_RE.search(text.lower()) or _CRISIS_RE.search(_norm(text)))


CRISIS_REPLY = (
    "Gracias por confiarme algo tan difícil. Lo que sientes importa y no tienes que pasarlo solo/a.\n\n"
    "**Por favor, habla ahora con una persona:**\n"
    "- Llama a la **Línea 113** (gratuita, 24 h) y pide la opción de salud mental, o escribe por WhatsApp al **955 557 000**.\n"
    "- Si estás en peligro inmediato: **105** (Policía) o **106** (SAMU).\n"
    "- Busca a alguien cercano que pueda quedarse contigo ahora mismo.\n\n"
    "Si quieres, también puedo avisar al servicio de psicología para que te escriban. Solo lo haré si tú lo pides."
)
CRISIS_SUGGESTIONS = ["Quiero que psicología me contacte", "Prefiero hablar con alguien de confianza", "Necesito calmarme ahora"]


# ----------------------------------------------------------------- contexto

def build_context(first_name, checkin, extra=""):
    if not checkin:
        return f"El estudiante se llama {first_name}. Aún no tiene encuesta registrada." + extra
    f = checkin["features"]
    return (
        f"El estudiante se llama {first_name}. Resultado de su última encuesta de bienestar: {checkin['label']}. "
        f"Frecuencia de preocupación (0–21): {f['anxiety_level']:.0f}; calidad de sueño (0–5): {f['sleep_quality']:.0f}; "
        f"carga de estudio (0–5): {f['study_load']:.0f}. Usa esto solo como contexto suave: no cites números ni "
        "etiquetas, y no lo asustes." + extra
    )


# ------------------------------------------------------------------- Gemini

def gemini_available():
    return bool(GEMINI_API_KEY)


def _post_gemini(body, timeout):
    """Envía la petición probando modelos alternativos si el elegido no existe (404) o rechaza la configuración (400)."""
    first = ACTIVE_MODEL["name"] or GEMINI_MODEL
    names = [first] + [m for m in [GEMINI_MODEL] + _FALLBACK_MODELS if m != first]
    last_exc = None
    for attempt in range(3):  # hasta 3 rondas: Gemini a veces responde 503 («saturado») y a los pocos segundos vuelve
        for name in dict.fromkeys(names):
            b = json.loads(json.dumps(body))
            gc = b.get("generationConfig", {})
            if name.startswith("gemini-2.5-flash"):
                gc["thinkingConfig"] = {"thinkingBudget": 0}  # respuestas rápidas
            else:
                gc.pop("thinkingConfig", None)
                gc["maxOutputTokens"] = max(gc.get("maxOutputTokens", 1500), 1500) + 2500  # margen para el razonamiento interno
            req = urllib.request.Request(f"{GEMINI_API_BASE}/models/{name}:generateContent", data=json.dumps(b).encode("utf-8"),
                                         headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                ACTIVE_MODEL["name"] = name
                return data
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code in (400, 404, 429, 500, 502, 503, 504):
                    continue  # prueba el siguiente modelo
                raise
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                continue
        if attempt < 2:
            time.sleep(1.2 * (attempt + 1))
    raise last_exc


def gemini_reply(history, message, context):
    contents = []
    # Gemini exige empezar con un turno del usuario y alternar roles: se descartan los turnos iniciales del bot
    # (el saludo) y se unen los consecutivos del mismo rol.
    for turn in history[-10:]:
        role = "user" if turn.get("role") == "user" else "model"
        text = str(turn.get("text", ""))[:1500]
        if not text or (not contents and role == "model"):
            continue
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n" + text
        else:
            contents.append({"role": role, "parts": [{"text": text}]})
    if contents and contents[-1]["role"] == "user":
        contents[-1]["parts"][0]["text"] += "\n" + message[:1500]
    else:
        contents.append({"role": "user", "parts": [{"text": message[:1500]}]})

    gen_cfg = {
        "temperature": 0.7,
        "maxOutputTokens": 1500,
        "responseMimeType": "application/json",
        "responseSchema": {
            "type": "OBJECT",
            "properties": {
                "reply": {"type": "STRING"},
                "suggestions": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
            "required": ["reply"],
        },
    }
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT + "\n\nContexto: " + context}]},
        "contents": contents,
        "generationConfig": gen_cfg,
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ],
    }
    data = _post_gemini(body, 25)

    cands = data.get("candidates") or []
    if not cands:
        raise RuntimeError("Gemini no devolvió candidatos (posible bloqueo de seguridad).")
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError("Gemini devolvió una respuesta vacía.")
    try:
        obj = json.loads(text)
        reply = str(obj.get("reply", "")).strip()
        sugg = [str(s).strip() for s in (obj.get("suggestions") or []) if str(s).strip()][:3]
    except (json.JSONDecodeError, AttributeError):
        reply, sugg = text, []
    if not reply:
        raise RuntimeError("Respuesta de Gemini sin texto.")
    return reply, sugg


def gemini_json(system, prompt, schema, max_tokens=1800, temperature=0.5):
    """Llamada de una sola vuelta que devuelve un objeto JSON validado por responseSchema. Lanza excepción si falla."""
    gen_cfg = {"temperature": temperature, "maxOutputTokens": max_tokens, "responseMimeType": "application/json", "responseSchema": schema}
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": prompt[:12000]}]}],
            "generationConfig": gen_cfg}
    data = _post_gemini(body, 30)
    parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError("Gemini devolvió una respuesta vacía.")
    return json.loads(text)


# --- señales de decaimiento en el chat (no son crisis) ---
DISTRESS_PATTERNS = [
    r"no puedo mas", r"no doy mas", r"ya no aguanto", r"agotad", r"sin ganas", r"no tengo ganas", r"me siento mal",
    r"muy estresad", r"estresad[oa] ", r"me supera", r"abrumad", r"desesper", r"colaps", r"ansios", r"no duermo",
    r"no logro dormir", r"llorando", r"he llorado", r"me siento solo", r"me siento sola", r"sin animo", r"desanimad",
    r"no me concentro", r"todo me sale mal", r"no sirvo", r"me bloqueo",
]
_DISTRESS_RE = re.compile("|".join(DISTRESS_PATTERNS))


def distress_hits(texts):
    """Cuántos mensajes de la lista muestran señales de decaimiento o estrés marcado."""
    return sum(1 for t in texts if _DISTRESS_RE.search(_norm(t)))


TOPIC_KEYS = {"sleep": ("dormir", "sueno", "insomnio", "desvel"), "anxiety": ("ansied", "nervio", "preocup", "panico", "agobi", "abrum"),
              "exams": ("examen", "prueba", "parcial", "evaluacion", "final"), "tasks": ("tarea", "trabajo", "entrega", "pendiente", "proyecto", "grupal"),
              "focus": ("concentr", "distra", "foco"), "mood": ("triste", "solo", "sola", "desanim", "sin ganas", "agotad")}


def chat_topics(texts):
    joined = _norm(" ".join(texts))
    return [k for k, keys in TOPIC_KEYS.items() if any(re.search(r"\b" + w, joined) for w in keys)]


# -------------------------------------------------------------- modo básico

_TOPICS = [
    (("dormir", "sueno", "insomnio", "desvel", "despierto"),
     "Dormir mal pesa mucho, y es muy común en época de estudio. Vamos con algo pequeño:\n\n"
     "- **Hora de apagado:** elige una hora fija para dejar el celular, por ejemplo 30 minutos antes de acostarte.\n"
     "- **Descarga mental:** anota en un papel lo pendiente de mañana. Así tu mente no tiene que recordarlo de noche.\n"
     "- **Respiración 4-6:** inhala 4 segundos, exhala 6, repite 5 veces ya en la cama.\n\n"
     "¿A qué hora te estás durmiendo normalmente?",
     ["Me duermo muy tarde", "Me despierto varias veces", "Pienso mucho antes de dormir"]),
    (("examen", "prueba", "evaluacion", "parcial", "final", "nota", "desaprob", "jalar"),
     "Los exámenes activan a cualquiera; no estás solo/a en esto. Un plan sencillo para hoy:\n\n"
     "- **Lista corta:** escribe los 3 temas que más pesan y empieza por el más fácil.\n"
     "- **Bloques 25/5:** 25 minutos de estudio, 5 de descanso, cuatro veces. Luego una pausa de 20.\n"
     "- **Simulacro:** resuelve 5 preguntas de práctica sin mirar apuntes. Es lo que más ayuda a recordar.\n\n"
     "¿Para cuándo es tu examen?",
     ["Es mañana y no he avanzado", "Me bloqueo en el examen", "No sé por dónde empezar"]),
    (("ansied", "nervio", "panico", "preocup", "angusti", "taquicardia", "pecho", "agobi", "abrum"),
     "Gracias por contármelo. Cuando el cuerpo se acelera, ayuda bajarle el ritmo primero:\n\n"
     "- **Respiración 4-6:** inhala 4 segundos, exhala 6, durante 1 minuto.\n"
     "- **Anclaje 5-4-3-2-1:** nombra 5 cosas que ves, 4 que tocas, 3 que oyes, 2 que hueles, 1 que saboreas.\n"
     "- **Tamaño del problema:** pregúntate «¿qué es lo único que puedo hacer hoy?» y hazlo.\n\n"
     "Si esto se repite casi todos los días, conversarlo con psicología puede darte herramientas a tu medida. ¿Quieres que lo veamos?",
     ["Me pasa casi todos los días", "Prefiero probar la respiración", "Quiero hablar con psicología"]),
    (("tarea", "trabajo", "entrega", "organiz", "tiempo", "procrastin", "postergo", "pendiente", "no llego", "carga", "grupal", "grupo"),
     "Cuando todo parece urgente, lo mejor es achicar el panorama:\n\n"
     "- **Tres columnas:** «para hoy», «para esta semana», «puede esperar».\n"
     "- **Primer paso mínimo:** por ejemplo «abrir el documento y escribir el título». Empezar es lo más difícil.\n"
     "- **Pide margen:** puedes escribirle a tu docente: «Hola profesor/a, estoy con varias entregas juntas. ¿Sería posible conversar sobre una fecha alternativa?».\n\n"
     "¿Cuál es la entrega más cercana?",
     ["Tengo tres entregas esta semana", "Me distraigo con el celular", "Ayúdame a armar un plan"]),
    (("concentr", "distra", "atencion", "foco", "mente en blanco"),
     "Concentrarse cuesta más cuando estamos cansados o preocupados. Algo que suele funcionar:\n\n"
     "- **Una sola tarea, 25 minutos,** con el celular en otra habitación o en modo avión.\n"
     "- **Escribe lo que te distrae** en un papel y atiéndelo en el descanso.\n"
     "- **Muévete 2 minutos** entre bloques: estirarte o caminar reactiva la atención.\n\n"
     "¿Qué te distrae más cuando estudias?",
     ["El celular", "Mis preocupaciones", "Estoy muy cansado/a"]),
    (("triste", "solo", "sola", "soledad", "desanim", "motiv", "sin ganas", "cansad", "agotad", "llorar"),
     "Siento que estés pasando por esto. Que te sientas así no te hace menos capaz; a veces es señal de que necesitas pausa y compañía.\n\n"
     "- **Algo pequeño hoy:** una ducha, salir 10 minutos a caminar o tomar agua y comer algo.\n"
     "- **Un mensaje corto** a alguien de confianza: «¿Tienes un ratito para conversar? Ando algo cargado/a».\n"
     "- **No tienes que poder con todo.** Si esto lleva varios días, el servicio de psicología puede acompañarte.\n\n"
     "¿Quieres contarme qué ha estado pasando?",
     ["Llevo varios días así", "Me siento solo/a", "Quiero hablar con psicología"]),
]

_GREETING = (("hola", "buenas", "buen dia", "buenos dias", "buenas tardes", "buenas noches", "hey"),)

DEFAULT_REPLY = (
    "Te leo con atención. Para ayudarte mejor, cuéntame un poco más: **qué está pasando, desde cuándo y cómo te afecta**.\n\n"
    "Por ejemplo: «Tengo un trabajo grupal el viernes, mi grupo no responde y me estoy desvelando». "
    "Con eso puedo sugerirte pasos concretos."
)
DEFAULT_SUGGESTIONS = ["Tengo examen y me bloqueo", "No logro dormir bien", "Siento mucha carga de tareas"]


def basic_reply(message, first_name):
    t = _norm(message)
    if any(g in t.split() or t.startswith(g) for g in _GREETING[0]) and len(t) < 25:
        return (f"¡Hola, {first_name}! Qué bueno verte por aquí. Cuéntame, ¿cómo ha ido tu semana? "
                "Puedes escribirme lo que quieras o tocar una de las ideas de abajo.", DEFAULT_SUGGESTIONS)
    best, best_score = None, 0
    for keys, reply, sugg in _TOPICS:   # gana el tema con más palabras clave; en empate, el primero
        score = sum(1 for k in keys if re.search(r"\b" + re.escape(k), t))
        if score > best_score:
            best, best_score = (reply, sugg), score
    if best:
        return best
    if any(w in t for w in ("gracias", "ok", "vale", "entendido")):
        return ("¡Con gusto! Estoy aquí cuando quieras seguir. Si algo se complica, recuerda que también puedes pedir que psicología te contacte.",
                ["Quiero otro consejo", "Quiero que psicología me contacte"])
    return DEFAULT_REPLY, DEFAULT_SUGGESTIONS