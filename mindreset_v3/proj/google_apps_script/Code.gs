/**
 * MindReset – puente entre la app y esta hoja de Google (v3).
 *
 * INSTALACIÓN (3 minutos):
 *  1. Crea una hoja de cálculo nueva (por ejemplo «MindReset – Base de datos»).
 *  2. Extensiones > Apps Script. Borra el contenido y pega TODO este archivo.
 *  3. Configuración del proyecto (engranaje) > Propiedades del script > Agregar propiedad:
 *       MINDRESET_SECRET = (una clave larga que inventes)
 *  4. Implementar > Nueva implementación > Tipo: Aplicación web
 *       Ejecutar como: Yo        Quién tiene acceso: Cualquier persona
 *     Autoriza los permisos (incluye «enviar correo como tú») y copia la URL que termina en /exec.
 *  5. En la app define MINDRESET_SHEETS_URL (esa URL) y MINDRESET_SHEETS_SECRET (la misma clave).
 *
 * ACTUALIZAR desde una versión anterior: pega este archivo, y luego
 *   Implementar > Administrar implementaciones > ✏️ > Versión: «Nueva versión» > Implementar (autoriza el permiso de correo).
 *   La URL /exec no cambia. Las columnas nuevas se añaden solas al final de cada pestaña.
 *
 * La hoja crea sola las pestañas: Usuarios, Encuestas, Calendario, Informes, Foro_Publicaciones y Foro_Comentarios.
 * IMPORTANTE: contiene hashes de contraseña y datos sensibles de bienestar. Compártela solo con personal autorizado.
 * Los correos salen de TU cuenta de Google (cuota aprox. 100/día con Gmail personal).
 */

const HEADERS = {
  Usuarios: ["id", "usuario", "nombre", "ciclo", "carrera", "rol", "activo", "password_hash", "consentimiento", "creado",
             "email", "email_verificado", "notificar", "tipos_notificacion", "alias", "avatar", "version_consentimiento"],
  Encuestas: ["id", "fecha", "id_estudiante", "estudiante", "ciclo", "carrera",
              "resp_ansiedad", "resp_horas_sueno", "resp_calidad_sueno", "resp_carga_estudio", "resp_estresor", "resp_contacto",
              "ansiedad_0_21", "calidad_sueno_1_5", "carga_estudio_1_10",
              "nivel_estres", "prob_sin_estres", "prob_eustres", "prob_angustia", "alerta",
              "revisado", "nota_psicologia", "fecha_revision", "respuestas_json", "clase", "clase_modelo", "ajuste_respuestas"],
  Calendario: ["id", "id_estudiante", "titulo", "tipo", "inicio", "fin", "notas", "origen", "plan_id", "notificado", "creado"],
  Informes: ["id", "fecha", "id_estudiante", "estudiante", "ciclo", "nivel_estres", "atencion", "informe_psicologia",
             "resumen_estudiante", "preguntas_json", "recomendaciones_json", "fuente", "id_chequeo"],
  Foro_Publicaciones: ["id", "id_autor", "alias", "categoria", "titulo", "texto", "fecha", "oculto"],
  Foro_Comentarios: ["id", "id_publicacion", "id_autor", "alias", "texto", "fecha", "oculto"]
};

function doGet() {
  return out_({ ok: true, service: "mindreset" });
}

function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(25000);
  try {
    const secret = PropertiesService.getScriptProperties().getProperty("MINDRESET_SECRET");
    const req = JSON.parse(e.postData.contents);
    if (!secret || req.secret !== secret) return out_({ ok: false, error: "unauthorized" });

    if (req.action === "ping") return out_({ ok: true, hoja: SpreadsheetApp.getActiveSpreadsheet().getUrl() });
    if (req.action === "upsert") return out_({ ok: true, count: upsert_(req.sheet, req.rows || []) });
    if (req.action === "delete") return out_({ ok: true, count: delete_(req.sheet, req.ids || []) });
    if (req.action === "send_email") {
      MailApp.sendEmail({ to: req.to, subject: req.subject, htmlBody: req.html, name: "MindReset", noReply: true });
      return out_({ ok: true });
    }
    if (req.action === "dump") {
      const res = { ok: true };
      Object.keys(HEADERS).forEach(function (n) { res[n] = readAll_(n); });
      return out_(res);
    }
    return out_({ ok: false, error: "unknown action" });
  } catch (err) {
    return out_({ ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
}

function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function sheet_(name) {
  if (!HEADERS[name]) throw new Error("Hoja no permitida: " + name);
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(name);
  const cols = HEADERS[name].length;
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.setFrozenRows(1);
  }
  const current = sh.getRange(1, 1, 1, cols).getValues()[0];
  if (current.join("|") !== HEADERS[name].join("|")) {   // crea o actualiza (añade columnas nuevas al final)
    sh.getRange(1, 1, 1, cols).setValues([HEADERS[name]]).setFontWeight("bold").setBackground("#E0D6FA");
    // Texto plano: evita que Sheets convierta fechas o interprete «=» como fórmula.
    sh.getRange(1, 1, Math.max(sh.getMaxRows(), 1000), cols).setNumberFormat("@");
  }
  return sh;
}

function upsert_(name, rows) {
  const sh = sheet_(name);
  const headers = HEADERS[name];
  const last = sh.getLastRow();
  const idIndex = {};
  if (last > 1) {
    sh.getRange(2, 1, last - 1, 1).getValues().forEach(function (r, i) { idIndex[String(r[0])] = i + 2; });
  }
  const toAppend = [];
  rows.forEach(function (row) {
    const values = headers.map(function (h) {
      const v = row[h] === undefined || row[h] === null ? "" : String(row[h]);
      return v.length > 49000 ? v.substring(0, 49000) : v;   // límite de celda de Sheets
    });
    const at = idIndex[String(row.id)];
    if (at) sh.getRange(at, 1, 1, headers.length).setValues([values]);
    else toAppend.push(values);
  });
  if (toAppend.length) {
    const start = Math.max(sh.getLastRow(), 1) + 1;
    sh.getRange(start, 1, toAppend.length, headers.length).setNumberFormat("@").setValues(toAppend);
  }
  return rows.length;
}

function delete_(name, ids) {
  const sh = sheet_(name);
  const last = sh.getLastRow();
  if (last < 2) return 0;
  const want = {};
  ids.forEach(function (i) { want[String(i)] = true; });
  const vals = sh.getRange(2, 1, last - 1, 1).getValues();
  let n = 0;
  for (let i = vals.length - 1; i >= 0; i--) {
    if (want[String(vals[i][0])]) { sh.deleteRow(i + 2); n++; }
  }
  return n;
}

function readAll_(name) {
  const sh = sheet_(name);
  const last = sh.getLastRow();
  if (last < 2) return [];
  const headers = HEADERS[name];
  return sh.getRange(2, 1, last - 1, headers.length).getValues().map(function (r) {
    const o = {};
    headers.forEach(function (h, i) { o[h] = String(r[i]); });
    return o;
  });
}
