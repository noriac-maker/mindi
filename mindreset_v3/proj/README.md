# MindReset v2

Prototipo de bienestar estudiantil: encuesta de estrés → modelo ML → panel para psicología, y un asistente (**Mindi**, con Gemini) para el estudiante.

## Qué hay de nuevo
- **Encuesta** de 6 preguntas con opciones descriptivas (nunca números), una por pantalla. Tres alimentan el modelo; las otras (horas de sueño, qué más pesa, deseo de contacto) son contexto para psicología.
- **Estudiante**: tras iniciar sesión ve primero la encuesta (una vez al día) y luego su resultado + consejos simples. Después, **chat con Mindi**: pastel, ejemplos tocables, sugerencias de seguimiento, botón para pedir contacto con psicología.
- **Psicología**: resumen (alertas, distribución, por ciclo), lista filtrable (nombre, ciclo, carrera, nivel de estrés, estado) y **detalle por estudiante**: respuestas, nivel de estrés, evolución, plan de acción sugerido, mensaje de acercamiento editable y notas.
- **Google Sheets** como base visible/respaldo (ver abajo). Registro de estudiantes con consentimiento.

## Ejecutar
```bash
pip install -r requirements.txt
uvicorn app:app --reload          # http://localhost:8000
# o: docker compose up --build
```
Cuentas demo: `estudiante1` / `MindReset2026!` · `psicologo1` / `PsicoDemo2026!` · `adminmindreset` / `AdminMindReset2026!` (cámbialas antes de cualquier uso real). Se siembran 8 estudiantes de ejemplo si Sheets no está configurado.

## Chatbot con Gemini
1. Crea una clave en https://aistudio.google.com/apikey.
2. `export GEMINI_API_KEY=...` (opcional `GEMINI_MODEL`, por defecto `gemini-2.5-flash`).

Sin clave —o si Gemini falla— Mindi responde en **modo básico** (consejos con ejemplos por tema); el chip del chat lo indica. A Gemini solo se envía: el historial reciente del chat, el nombre de pila y el nivel de estrés del último chequeo. Mensajes con lenguaje de crisis **no** se envían a Gemini: se responde con la Línea 113 y WhatsApp 955 557 000 (revisa `HELP_RESOURCES` en `chatbot.py`, los menús cambian).

## Google Sheets
La app guarda en SQLite (rápido) y **sincroniza cada ~10 s** con la hoja (pestañas `Usuarios` y `Encuestas`); si la hoja no responde reintenta sola. Si la base local está vacía (p. ej. hosting efímero), **restaura desde la hoja** al arrancar.
1. Crea una hoja nueva → Extensiones → Apps Script → pega `google_apps_script/Code.gs`.
2. Propiedades del script: `MINDRESET_SECRET` = una clave larga.
3. Implementar → Aplicación web → ejecutar como *Yo*, acceso *Cualquier persona* → copia la URL `/exec`.
4. Variables: `MINDRESET_SHEETS_URL` y `MINDRESET_SHEETS_SECRET`.
Estado en `/health`; el admin puede forzar `POST /api/admin/sheets/sync` o `/restore`.
⚠️ La hoja contiene hashes de contraseña y datos sensibles: compártela solo con personal autorizado.

## Privacidad
- Psicología ve nombre, ciclo, respuestas y resultado. **No** ve las conversaciones con Mindi (no se guardan en servidor).
- Psicología solo recibe un aviso de contacto si el estudiante lo pide (pregunta 6, botón o chat con confirmación).

## ⚠️ Sobre el modelo (léelo)
1. **Escalas**: los umbrales del árbol indican que `study_load` y `sleep_quality` se entrenaron en **0–5** (la v1 usaba carga 1–10, lo que saturaba el modelo). `survey.py` documenta el mapeo; confírmalo con el diccionario de datos.
2. **El árbol es contraintuitivo en tramos** (p. ej. ansiedad casi diaria + buen sueño + poca carga → «Sin estrés»). Por eso existe una capa de señales (`survey.signal_floor`) que solo puede **subir** la alerta según las respuestas; el panel muestra el valor del modelo y el ajuste. Recomendado: reentrenar/validar antes de uso real.
3. Ansiedad: cada opción es el punto medio de una banda tipo GAD-7 (supuesto, no instrumento validado).
Los resultados son orientativos y no constituyen diagnóstico.

## Pruebas
`python -m pytest tests -q` (sin internet: simula Apps Script, incluida su redirección 302, y Gemini).


---
# Novedades de la v3

**Diseño:** paleta MindReset (#6A3EC8, #B89DFF, #00BFA6, #B2F0E6, #FF7B7B, #FFF9F0, #4B5E7C), modo claro y modo oscuro (botón 🌙/☀️; recuerda tu elección y respeta el tema del dispositivo).

**Calendario** (`Calendario` en el menú del estudiante): vistas día / semana / mes; asistente «Crear mi calendario» (texto libre + cuestionario) y «Tengo una entrega» (reparte el estudio en varios días sin sobrecargar); actividades manuales; vínculo con Google Calendar (suscripción iCal + botón «Añadir a Google» por actividad + descarga .ics); recordatorios por correo 15 min antes.

**Mindi personalizado:** «Chequeo profundo» (3 preguntas adaptadas a la encuesta, al chat y al horario) → recomendaciones → «¿Desea añadir estas actividades a su calendario?». Cada chequeo genera un **informe breve** para el panel de psicología (y se guarda en la hoja `Informes`). Mindi muestra señales de decaimiento y, si detecta varias en el chat, **ofrece** avisar a psicología (solo con permiso del estudiante).

**Comunidad anónima:** alias + 5 avatares kawaii o foto subida; foro con búsqueda y categorías; psicología puede ocultar publicaciones.

**Términos y Condiciones:** texto completo en `static/terminos.md` (se abre en ventana desde el registro). Reemplaza los textos entre [corchetes] (institución, correo de privacidad, responsable, fecha) antes de usarlo con personas reales y **hazlo revisar por un abogado**. El registro exige 4 casillas separadas, sin marcar.

## Pasos para actualizar tu despliegue
1. **GitHub:** sube/reemplaza todos los archivos del proyecto (incluida la carpeta `static/` y los nuevos `.py`).
2. **Apps Script:** pega el nuevo `google_apps_script/Code.gs`, guarda y *Implementar → Administrar implementaciones → Editar (lápiz) → Versión nueva → Implementar*. Acepta el permiso nuevo de **enviar correo** (MailApp). Así se crean las pestañas Calendario, Informes, Comunidad…
3. **Render → Environment:** añade `MINDRESET_APP_URL` = la URL pública de tu app (sin `/` final; sirve para los enlaces de Google Calendar). Opcional: `MINDRESET_HIDE_DEMO=1` para ocultar las credenciales de demostración del login.
4. **Seguridad:** cambia el secreto de Sheets (`MINDRESET_SECRET` en el script y `MINDRESET_SHEETS_SECRET` en Render) porque se compartió en un chat. Cambia también las contraseñas de las cuentas demo antes de usar datos reales.
5. Pruebas locales: `python -m pytest tests -q`.

Nota: Render gratis duerme tras ~15 min sin uso; los recordatorios por correo solo salen mientras la app está despierta. Para recordatorios fiables usa un plan siempre activo o un ping periódico a `/health`.
