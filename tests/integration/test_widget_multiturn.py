"""Prueba de integración real (ejecuta el JS de verdad con Node, no un
doble ni un análisis estático) del estado de conversación mínimo
agregado en la Ronda 12 (ver Validacion_observaciones_RAG_STUDIO.md):
cuando el motor responde `action: "aclarar"` con `missing_variables`,
el widget debe recordar la consulta ORIGINAL y reenviarla junto con la
variable ya puesta, en vez de tratar la siguiente respuesta del
visitante como una consulta nueva.

Construye un DOM mínimo en Node (mismo criterio que
test_widget_script_currentscript_fix.py: sin jsdom, sin dependencias
nuevas) con soporte real de `addEventListener`/disparo de eventos (lo
que esa prueba no necesitaba, pero esta sí, para simular un clic real
en "Enviar"), y sustituye `fetch` por un doble que devuelve dos
respuestas canónicas en secuencia -- inspecciona el CUERPO real de
cada llamada, no una suposición sobre qué debería mandar el código."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from interfaces.api.widget_assets import WIDGET_JS

_HARNESS = r"""
"use strict";
var fetchCalls = [];
var fetchResponses = [
  { status: 200, ok: true, body: {
      action: "aclarar", response_text: "¿Podrías indicar 'plantel'?",
      matched_intent: "Consultar horario", confidence: 0.9, sources: [],
      snapshot_version: 1, log_id: "log-1", latency_ms: 1.0, missing_variables: ["plantel"],
  } },
  { status: 200, ok: true, body: {
      action: "responder", response_text: null,
      matched_intent: "Consultar horario", confidence: 0.9,
      sources: [{ source_id: "s1", chunk_id: "c1", text: "El horario es de 9 a 17.", score: 0.9 }],
      snapshot_version: 1, log_id: "log-2", latency_ms: 1.0, missing_variables: [],
  } },
];

global.fetch = function (url, options) {
  var index = fetchCalls.length;
  fetchCalls.push({ url: url, body: JSON.parse(options.body) });
  var response = fetchResponses[index];
  return Promise.resolve({
    ok: response.ok, status: response.status,
    json: function () { return Promise.resolve(response.body); },
  });
};

var createdElements = [];
function makeElement(tag) {
  var listeners = {};
  var el = {
    tagName: tag, attrs: {}, children: [], dataset: {}, classList: { set: {} },
    setAttribute: function (k, v) { this.attrs[k] = v; },
    appendChild: function (child) { this.children.push(child); },
    addEventListener: function (event, cb) {
      listeners[event] = listeners[event] || [];
      listeners[event].push(cb);
    },
    trigger: function (event) { (listeners[event] || []).forEach(function (cb) { cb({ key: "Enter" }); }); },
    focus: function () {},
    scrollTop: 0, scrollHeight: 0, value: "",
  };
  el.classList.toggle = function (name) { el.classList.set[name] = !el.classList.set[name]; };
  el.classList.contains = function (name) { return !!el.classList.set[name]; };
  Object.defineProperty(el, "textContent", {
    get: function () { return this._text || ""; },
    set: function (v) { this._text = v; },
  });
  el.attachShadow = function () { return makeElement("shadow-root"); };
  createdElements.push(el);
  return el;
}

var scriptEl = makeElement("script");
scriptEl.dataset = { projectId: "p1", apiBase: "https://ejemplo.test", widgetToken: "tok-123", title: "Asistente" };

global.document = {
  currentScript: scriptEl,
  readyState: "complete",  // init() corre de inmediato -- el diferido ya lo cubre otra prueba
  body: makeElement("body"),
  createElement: function (tag) { return makeElement(tag); },
  addEventListener: function () {},
};
global.window = { RAGSTUDIO_WIDGET_CONFIG: undefined };
console.error = function () {};  // silenciado a propósito -- no es lo que esta prueba verifica

// --- Código real de WIDGET_JS (el mismo que sirve GET /widget.js) ---
%(widget_js)s

function flushMicrotasks() { return new Promise(function (resolve) { setTimeout(resolve, 0); }); }

var inputEl = createdElements.filter(function (e) { return e.tagName === "input"; })[0];
var sendBtn = createdElements.filter(function (e) { return e.tagName === "button" && e._text === "Enviar"; })[0];

async function run() {
  inputEl.value = "¿cuál es el horario de atención?";
  sendBtn.trigger("click");
  await flushMicrotasks(); await flushMicrotasks();

  inputEl.value = "Campus Norte";
  sendBtn.trigger("click");
  await flushMicrotasks(); await flushMicrotasks();

  console.log(JSON.stringify({ ok: true, calls: fetchCalls }));
}
run();
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no disponible en este entorno")
def test_widget_resends_the_original_query_with_the_variable_once_answered(tmp_path):
    harness_path = tmp_path / "widget_multiturn_harness.js"
    harness_path.write_text(_HARNESS % {"widget_js": WIDGET_JS}, encoding="utf-8")

    result = subprocess.run(["node", str(harness_path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    calls = payload["calls"]
    assert len(calls) == 2

    first_body = calls[0]["body"]
    assert first_body["message"] == "¿cuál es el horario de atención?"
    assert first_body["variables"] == {}

    second_body = calls[1]["body"]
    # El punto central de la Ronda 12: la SEGUNDA llamada reenvía la
    # consulta ORIGINAL (no "Campus Norte", el texto que el visitante
    # acaba de escribir), con la variable pedida ya puesta.
    assert second_body["message"] == "¿cuál es el horario de atención?"
    assert second_body["variables"] == {"plantel": "Campus Norte"}


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no disponible en este entorno")
def test_widget_starts_a_fresh_turn_after_a_final_action(tmp_path):
    # Variante: si la primera respuesta YA es final (no "aclarar"), la
    # segunda pregunta del visitante debe tratarse como una consulta
    # nueva, sin variables heredadas de nada.
    harness = _HARNESS.replace(
        '{ status: 200, ok: true, body: {\n      action: "aclarar"',
        '{ status: 200, ok: true, body: {\n      action: "responder"',
    )
    harness_path = tmp_path / "widget_multiturn_fresh_harness.js"
    harness_path.write_text(harness % {"widget_js": WIDGET_JS}, encoding="utf-8")

    result = subprocess.run(["node", str(harness_path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    second_body = payload["calls"][1]["body"]
    assert second_body["message"] == "Campus Norte"
    assert second_body["variables"] == {}
