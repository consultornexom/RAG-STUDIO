"""Contenido estático del widget web embebible (ADR-002, Fase 3 --
"primer canal real conectado a la API": un widget web antes que
WhatsApp, según la decisión ya registrada en el ADR).

Se guarda como una constante de Python (no como archivo suelto bajo
`interfaces/api/static/`) a propósito: este proyecto no tiene hoy
ningún mecanismo de `package_data`/`MANIFEST.in` para incluir archivos
no-`.py` en un `pip install -e .[api]` real (solo lo tiene resuelto
`packaging/ragstudio.spec` para el ejecutable de escritorio, que no
empaqueta `interfaces/api/` -- es un servicio hermano con su propio
ciclo de despliegue). Un módulo `.py` normal no necesita ningún
mecanismo nuevo de empaquetado.

Diseño del widget (deliberadamente el más simple que conecta un canal
real de punta a punta, ver "Decisiones confirmadas" del ADR-002):

- Sin build step, sin dependencias externas -- un solo `<script>` que
  cualquier sitio puede pegar, en la misma línea de una integración de
  chat típica (Intercom/Crisp), pero sin ningún SDK de terceros.
- Aislado del CSS del sitio anfitrión con Shadow DOM -- para que los
  estilos del widget nunca choquen con los del sitio que lo embebe, y
  viceversa.
- Sin generación de lenguaje natural, igual que el resto del runtime
  (ADR-001, sección 8; ver `application/runtime/commands/
  handle_incoming_message.py`): cuando la acción es "responder",
  `response_text` siempre llega `None` desde la API -- el widget nunca
  inventa una respuesta; muestra los fragmentos recuperados tal cual,
  etiquetados como tal, en vez de simular una conversación que no
  existe.
- `conversation_id` (Ronda 19, ver Validacion_observaciones_RAG_STUDIO.md):
  el widget guarda el `conversation_id` que la API devuelve en la
  PRIMERA respuesta y lo reenvía en todas las solicitudes siguientes de
  esa misma pestaña -- así el servidor agrupa todos los turnos de este
  visitante bajo una misma conversación (pestaña Monitoreo, banco de
  pruebas), sin que el widget tenga que saber nada de cómo se genera
  ese id. Vive en la misma variable de módulo que el resto del estado
  de esta sección (se pierde al recargar, igual que `conversationState`
  -- ver más abajo), pero es independiente de él: no se reinicia cada
  vez que se resuelve una aclaración, solo al recargar la página.
- Estado de conversación mínimo entre turnos (Ronda 12, ver
  Validacion_observaciones_RAG_STUDIO.md): sigue siendo cierto que
  ningún punto del motor conversacional extrae el valor de una
  variable requerida a partir de texto libre -- eso no cambió, y sigue
  siendo el mismo límite que tiene el Simulador de escritorio. Lo que
  el widget SÍ hace ahora es lo que el Simulador deja en manos de
  quien lo usa manualmente: cuando la respuesta trae `action:
  "aclarar"` y `missing_variables` (nuevo en `MessageResponse`, mismo
  dato que ya exponía `SimulationTrace.missing_variables` al
  Simulador), el widget recuerda cuál era la consulta ORIGINAL y a qué
  variable corresponde la pregunta aclaratoria (siempre la primera de
  `missing_variables` -- coincide con cómo `SimulateConversation`
  arma `clarifying_question`, ver
  `application/conversational/queries/simulate_conversation.py`). La
  siguiente respuesta del visitante se envía entonces como el VALOR de
  esa variable, junto con la consulta original, no como una consulta
  nueva -- así el motor puede resolver la intención con el dato ya
  puesto, sin necesitar ningún cambio en el motor mismo. Limitación
  honesta, no oculta: el widget no puede distinguir "esto responde tu
  pregunta aclaratoria" de "en realidad quiero preguntar otra cosa" --
  si el visitante cambia de tema a media aclaración, su texto se toma
  como el valor de la variable pendiente igual. El estado vive solo en
  memoria de esa pestaña del navegador; se pierde al recargar la
  página (aceptable: recargar es, para cualquier chat de este estilo,
  el gesto implícito de "empezar de nuevo"). Un segundo envío mientras
  el primero sigue en curso (doble clic, Enter repetido) queda
  bloqueado (`sendInFlight`, campo deshabilitado mientras se espera) --
  sin esto, dos respuestas que llegaran fuera de orden podían pisarse
  el estado de conversación entre sí.
- La `X-API-Key` es opcional y pensada solo para un piloto controlado
  de un sitio de confianza (ver docstring de `create_app_from_env`):
  incrustar el secreto operativo completo en un `<script>` público es
  aceptable para un piloto de un solo sitio, no para una integración
  pública con visitantes anónimos arbitrarios -- eso exige un token
  público acotado por proyecto.

  Fase 4: ese token ya existe -- `data-widget-token` (encabezado
  `X-Widget-Token`), emitido con `POST /projects/{id}/widget-tokens`
  (protegido por la API key global, nunca por otro token de widget) y
  revocable en cualquier momento sin afectar la API key ni a otros
  proyectos. `data-api-key` sigue soportado (sigue siendo válido para
  un piloto de un solo sitio de confianza, o para pruebas locales),
  pero para una integración pública real hay que usar
  `data-widget-token`, no la API key global."""
from __future__ import annotations

WIDGET_JS = r"""(function () {
  "use strict";

  // SCRIPT_EL se captura aquí, en el ámbito síncrono de ejecución del
  // propio <script> (auditoría Ronda 10, hallazgo A1): document.currentScript
  // solo tiene valor MIENTRAS el script se está ejecutando de forma
  // síncrona -- en cuanto el arranque se difiere a un listener de
  // DOMContentLoaded (ver más abajo, para el caso normal de un <script>
  // sin defer/async colocado antes de que termine de parsear la
  // página), document.currentScript ya es null. Leerlo dentro de
  // init()/readConfig() -- como hacía este archivo antes de esta
  // auditoría -- significaba que data-project-id/data-api-base/
  // data-widget-token nunca se resolvían en el caso más común (un
  // <script> pegado tal cual en el HTML del sitio del cliente, el
  // mismo snippet que genera "Exportar paquete de entrega al
  // cliente…") y el widget nunca llegaba a dibujarse.
  var SCRIPT_EL = document.currentScript;

  function readConfig() {
    var fromDataset = SCRIPT_EL && SCRIPT_EL.dataset ? SCRIPT_EL.dataset : {};
    var fromGlobal = window.RAGSTUDIO_WIDGET_CONFIG || {};
    return {
      projectId: fromDataset.projectId || fromGlobal.projectId,
      apiBase: (fromDataset.apiBase || fromGlobal.apiBase || "").replace(/\/+$/, ""),
      apiKey: fromDataset.apiKey || fromGlobal.apiKey || null,
      widgetToken: fromDataset.widgetToken || fromGlobal.widgetToken || null,
      title: fromDataset.title || fromGlobal.title || "Asistente",
    };
  }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      if (key === "text") { node.textContent = attrs[key]; } else { node.setAttribute(key, attrs[key]); }
    });
    (children || []).forEach(function (child) { node.appendChild(child); });
    return node;
  }

  function buildStyle() {
    // Colores de marca (auditoría de UI 2026-08-24, "todo el ecosistema
    // comparte la misma identidad"): idénticos a AZUL_OSCURO/AZUL_MEDIO/
    // VIOLETA_ACENTO/GRIS_* de ui/theme.py (interfaz de escritorio),
    // extraídos ambos del mismo ui/LOGO.png -- ver ese módulo para el
    // detalle de la extracción de color. Antes este widget usaba
    // #1F3864, el AZUL_OSCURO original (previo a esa auditoría, cuando
    // RAG STUDIO todavía heredaba la paleta de RAG CONTENT STUDIO).
    var style = document.createElement("style");
    style.textContent = [
      ":host { all: initial; }",
      ".bubble { position: fixed; bottom: 20px; right: 20px; width: 56px; height: 56px;",
      "  border-radius: 28px; background: #152A4E; color: #fff; border: none; cursor: pointer;",
      "  font: 14px sans-serif; box-shadow: 0 2px 8px rgba(0,0,0,.3); z-index: 999999; }",
      ".bubble:hover { background: #2C5A87; }",
      ".panel { position: fixed; bottom: 88px; right: 20px; width: 320px; max-height: 440px;",
      "  display: none; flex-direction: column; background: #fff; border-radius: 12px;",
      "  box-shadow: 0 4px 16px rgba(0,0,0,.3); font: 13px sans-serif; overflow: hidden; z-index: 999999; }",
      ".panel.open { display: flex; }",
      ".head { background: #152A4E; color: #fff; padding: 10px 12px; font-weight: bold;",
      "  border-bottom: 3px solid #6C4FBD; }",
      ".log { flex: 1; overflow-y: auto; padding: 10px; background: #F3F5F9; }",
      ".msg { margin-bottom: 8px; padding: 8px 10px; border-radius: 8px; max-width: 85%; white-space: pre-wrap; }",
      ".msg.user { background: #2C5A87; color: #fff; margin-left: auto; }",
      ".msg.bot { background: #fff; color: #222; border: 1px solid #D6DCE6; }",
      ".msg.err { background: #fdecea; color: #7a2020; border: 1px solid #f3c2c2; }",
      ".src-label { font-size: 11px; color: #666; margin-bottom: 2px; }",
      ".row { display: flex; border-top: 1px solid #D6DCE6; }",
      ".row:focus-within { border-top: 1px solid #6C4FBD; }",
      ".row input { flex: 1; border: none; padding: 10px; font: inherit; }",
      ".row button { border: none; background: #152A4E; color: #fff; padding: 0 14px; cursor: pointer; }",
      ".row button:hover { background: #2C5A87; }",
      ".row button:disabled { background: #A9B4C4; color: #EEF1F5; cursor: default; }",
    ].join("\n");
    return style;
  }

  function renderSourcesAsAnswer(sources) {
    if (!sources || sources.length === 0) {
      return "No encontré información suficiente para responder eso.";
    }
    var lines = ["Esto encontramos en la documentación:"];
    sources.forEach(function (s) { lines.push("- " + s.text); });
    return lines.join("\n");
  }

  function init() {
    var config = readConfig();
    if (!config.projectId || !config.apiBase) {
      console.error("[ragstudio-widget] Falta data-project-id o data-api-base en el <script> del widget.");
      return;
    }

    // Ronda 12: estado de conversación mínimo, en memoria de esta
    // pestaña -- ver docstring del módulo, sección "Estado de
    // conversación mínimo entre turnos". `awaitingVariable` es el
    // nombre de la variable que la ÚLTIMA respuesta pidió aclarar (o
    // null si no hay ninguna aclaración pendiente); `originalQuery`/
    // `variables` son lo que hay que reenviar cuando el visitante
    // conteste esa aclaración.
    var conversationState = { originalQuery: null, variables: {}, awaitingVariable: null };

    function resetConversationState() {
      conversationState = { originalQuery: null, variables: {}, awaitingVariable: null };
    }

    // conversationId (Ronda 19): ver docstring del módulo. Distinto de
    // conversationState -- persiste durante toda la sesión de esta
    // pestaña, no solo mientras se resuelve una aclaración pendiente.
    var conversationId = null;

    // sendInFlight (detalle fino cerrado en la misma Ronda 12): sin
    // esto, un doble clic en "Enviar" (o Enter repetido) mientras la
    // primera solicitud todavía no responde disparaba una SEGUNDA
    // solicitud que leía `conversationState` en el mismo estado que la
    // primera -- si las respuestas llegaban fuera de orden, la que
    // llegara después pisaba el estado de conversación de la que
    // llegó antes, sin ningún error visible, solo una conversación que
    // "olvida" lo que el visitante ya contestó. Bloquear un segundo
    // envío mientras el primero está en curso lo evita de raíz, y de
    // paso deshabilita visualmente el campo mientras se espera.
    var sendInFlight = false;

    var host = document.createElement("div");
    document.body.appendChild(host);
    var root = host.attachShadow({ mode: "open" });
    root.appendChild(buildStyle());

    var log = el("div", { class: "log" });
    var input = el("input", { type: "text", placeholder: "Escribe tu pregunta…" });
    var sendBtn = el("button", { text: "Enviar" });
    var panel = el("div", { class: "panel" }, [
      el("div", { class: "head", text: config.title }),
      log,
      el("div", { class: "row" }, [input, sendBtn]),
    ]);
    var bubble = el("button", { class: "bubble", text: "💬" });
    root.appendChild(panel);
    root.appendChild(bubble);

    function addMessage(text, cls) {
      log.appendChild(el("div", { class: "msg " + cls, text: text }));
      log.scrollTop = log.scrollHeight;
    }

    bubble.addEventListener("click", function () {
      panel.classList.toggle("open");
      if (panel.classList.contains("open")) { input.focus(); }
    });

    function send() {
      if (sendInFlight) { return; }
      var text = input.value.trim();
      if (!text) { return; }
      sendInFlight = true;
      input.disabled = true;
      sendBtn.disabled = true;
      addMessage(text, "user");
      input.value = "";

      // Ronda 12: si la última respuesta pedía aclarar una variable,
      // este texto es el VALOR de esa variable, no una consulta nueva
      // -- se reenvía la consulta original con la variable ya puesta
      // (ver docstring del módulo, "Estado de conversación mínimo").
      var messageToSend;
      var variablesToSend;
      if (conversationState.awaitingVariable) {
        variablesToSend = {};
        Object.keys(conversationState.variables).forEach(function (key) {
          variablesToSend[key] = conversationState.variables[key];
        });
        variablesToSend[conversationState.awaitingVariable] = text;
        messageToSend = conversationState.originalQuery;
      } else {
        messageToSend = text;
        variablesToSend = {};
      }

      var headers = { "Content-Type": "application/json" };
      if (config.widgetToken) { headers["X-Widget-Token"] = config.widgetToken; }
      else if (config.apiKey) { headers["X-API-Key"] = config.apiKey; }
      fetch(config.apiBase + "/projects/" + encodeURIComponent(config.projectId) + "/messages", {
        method: "POST", headers: headers,
        body: JSON.stringify({
          message: messageToSend, variables: variablesToSend, conversation_id: conversationId,
        }),
      }).then(function (response) {
        if (response.status === 401) {
          addMessage("Error de configuración del widget (token o API key inválido).", "err");
          return null;
        }
        if (response.status === 404) {
          addMessage("Este asistente todavía no está disponible.", "err");
          return null;
        }
        if (response.status === 429) {
          // Ronda 11: límite de tasa opcional del servicio.
          addMessage("Estamos recibiendo muchos mensajes en este momento. Intenta de nuevo en unos segundos.", "err");
          return null;
        }
        if (!response.ok) {
          addMessage("Ocurrió un error al contactar al asistente.", "err");
          return null;
        }
        return response.json();
      }).then(function (body) {
        if (!body) { return; }
        // conversationId (Ronda 19): la API siempre devuelve uno --
        // se guarda tal cual para reenviarlo en el siguiente turno,
        // sin que este widget necesite saber cómo se generó.
        conversationId = body.conversation_id;
        if (body.action === "aclarar" && body.missing_variables && body.missing_variables.length > 0) {
          conversationState = {
            originalQuery: messageToSend, variables: variablesToSend,
            awaitingVariable: body.missing_variables[0],
          };
        } else {
          resetConversationState();
        }
        var text2 = body.response_text;
        if (text2 === null || text2 === undefined || text2 === "") {
          text2 = renderSourcesAsAnswer(body.sources);
        }
        addMessage(text2, "bot");
      }).catch(function (error) {
        console.error("[ragstudio-widget] fallo de red:", error);
        addMessage("No se pudo conectar con el asistente.", "err");
      }).then(function () {
        // Se ejecuta siempre, haya terminado bien o mal la solicitud
        // (encadenado después del .catch, así que también corre ante
        // un fallo de red) -- libera el envío siguiente y reactiva el
        // campo, sin duplicar esta limpieza en cada rama de arriba.
        sendInFlight = false;
        input.disabled = false;
        sendBtn.disabled = false;
        input.focus();
      });
    }

    sendBtn.addEventListener("click", send);
    input.addEventListener("keydown", function (event) { if (event.key === "Enter") { send(); } });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
"""
