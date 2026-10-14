"""Prueba de integración real (ejecuta el JS de verdad con Node, no un
doble ni un análisis estático) de un detalle fino cerrado en la misma
Ronda 12: sin ninguna guarda, un segundo clic en "Enviar" (o Enter
repetido) mientras la primera solicitud todavía no respondía disparaba
una SEGUNDA llamada a `fetch` que leía `conversationState` en el mismo
estado que la primera -- si las respuestas llegaban fuera de orden, la
última en resolver pisaba silenciosamente el estado de conversación de
la que resolvió antes.

Usa un `fetch` doble cuya promesa NO se resuelve sola -- se guarda la
función `resolve` para dispararla a mano, exactamente en el momento en
que la prueba necesita simular "la primera solicitud sigue en
curso"."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from interfaces.api.widget_assets import WIDGET_JS

_HARNESS = r"""
"use strict";
var fetchCalls = [];
var pendingResolvers = [];

global.fetch = function (url, options) {
  fetchCalls.push({ url: url, body: JSON.parse(options.body) });
  return new Promise(function (resolve) {
    pendingResolvers.push(resolve);
  });
};

function respondTo(index, body) {
  pendingResolvers[index]({
    ok: true, status: 200,
    json: function () { return Promise.resolve(body); },
  });
}

var createdElements = [];
function makeElement(tag) {
  var listeners = {};
  var el = {
    tagName: tag, attrs: {}, children: [], dataset: {}, classList: { set: {} },
    disabled: false,
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
  readyState: "complete",
  body: makeElement("body"),
  createElement: function (tag) { return makeElement(tag); },
  addEventListener: function () {},
};
global.window = { RAGSTUDIO_WIDGET_CONFIG: undefined };
console.error = function () {};

// --- Código real de WIDGET_JS (el mismo que sirve GET /widget.js) ---
%(widget_js)s

function flushMicrotasks() { return new Promise(function (resolve) { setTimeout(resolve, 0); }); }

var inputEl = createdElements.filter(function (e) { return e.tagName === "input"; })[0];
var sendBtn = createdElements.filter(function (e) { return e.tagName === "button" && e._text === "Enviar"; })[0];

async function run() {
  var snapshots = {};

  inputEl.value = "primera pregunta";
  sendBtn.trigger("click");
  await flushMicrotasks();
  snapshots.afterFirstClick = { calls: fetchCalls.length, inputDisabled: inputEl.disabled, btnDisabled: sendBtn.disabled };

  // Segundo intento MIENTRAS la primera solicitud sigue sin resolver
  // -- debe ser ignorado por completo, ni siquiera debe llegar a leer
  // el input (que además ya está deshabilitado en un navegador real).
  inputEl.value = "segunda pregunta, todavia en vuelo";
  sendBtn.trigger("click");
  await flushMicrotasks();
  snapshots.afterSecondClickWhileInFlight = { calls: fetchCalls.length, inputDisabled: inputEl.disabled, btnDisabled: sendBtn.disabled };

  // Ahora sí se resuelve la primera solicitud -- se libera el envío.
  respondTo(0, {
    action: "responder", response_text: null, matched_intent: "X", confidence: 0.9,
    sources: [{ source_id: "s1", chunk_id: "c1", text: "respuesta", score: 0.9 }],
    snapshot_version: 1, log_id: "log-1", latency_ms: 1.0, missing_variables: [],
  });
  await flushMicrotasks(); await flushMicrotasks();
  snapshots.afterFirstResolves = { calls: fetchCalls.length, inputDisabled: inputEl.disabled, btnDisabled: sendBtn.disabled };

  // Con el envío liberado, un tercer intento SÍ debe producir una
  // llamada nueva.
  inputEl.value = "tercera pregunta";
  sendBtn.trigger("click");
  await flushMicrotasks();
  snapshots.afterThirdClick = { calls: fetchCalls.length };

  console.log(JSON.stringify({ ok: true, snapshots: snapshots, calls: fetchCalls }));
}
run();
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no disponible en este entorno")
def test_a_second_send_is_ignored_while_the_first_request_is_still_in_flight(tmp_path):
    harness_path = tmp_path / "widget_send_in_flight_harness.js"
    harness_path.write_text(_HARNESS % {"widget_js": WIDGET_JS}, encoding="utf-8")

    result = subprocess.run(["node", str(harness_path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    snapshots = payload["snapshots"]

    assert snapshots["afterFirstClick"] == {"calls": 1, "inputDisabled": True, "btnDisabled": True}
    # El punto central: el segundo clic, mientras el primero sigue en
    # vuelo, NO produjo una segunda llamada a fetch.
    assert snapshots["afterSecondClickWhileInFlight"] == {"calls": 1, "inputDisabled": True, "btnDisabled": True}
    # Al resolver la primera solicitud, el campo se reactiva.
    assert snapshots["afterFirstResolves"] == {"calls": 1, "inputDisabled": False, "btnDisabled": False}
    # Con el envío ya liberado, un tercer intento sí llega al servidor.
    assert snapshots["afterThirdClick"] == {"calls": 2}

    # Y el cuerpo de esa segunda llamada real es la TERCERA pregunta
    # (no la segunda, que nunca se envió) -- confirma que no quedó
    # nada de la solicitud bloqueada mezclado con la siguiente.
    assert payload["calls"][1]["body"]["message"] == "tercera pregunta"
