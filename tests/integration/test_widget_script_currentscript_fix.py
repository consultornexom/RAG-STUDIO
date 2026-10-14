"""Prueba de integración real (ejecuta el JS de verdad, con Node -- no
un doble ni un análisis estático del código fuente) del hallazgo A1 de
la auditoría Ronda 10: `document.currentScript` solo tiene valor
mientras un <script> se ejecuta de forma síncrona; en cuanto el
arranque del widget se difiere a un listener de `DOMContentLoaded`
(el caso normal de un <script> sin defer/async, exactamente el que
genera `_build_widget_snippet`), ya es `null`. Antes de la corrección,
`readConfig()` leía `document.currentScript` DENTRO de `init()`, así
que `data-project-id`/`data-api-base`/`data-widget-token` nunca se
resolvían en ese caso y el widget no se dibujaba.

Esta prueba construye un DOM mínimo en Node (sin jsdom, sin
dependencias nuevas: solo objetos planos que imitan lo que WIDGET_JS
de verdad usa) que reproduce exactamente ese escenario -- readyState
"loading" en el momento en que el <script> se ejecuta -- y corre el
código real servido por `GET /widget.js` (la misma constante
`WIDGET_JS`, no una copia)."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from interfaces.api.widget_assets import WIDGET_JS

_HARNESS = r"""
"use strict";
var errors = [];
var appended = [];

function makeElement(tag) {
  var el = {
    tagName: tag, attrs: {}, children: [], dataset: {}, classList: { set: {}, },
    setAttribute: function (k, v) { this.attrs[k] = v; },
    appendChild: function (child) { this.children.push(child); appended.push(child.tagName || "text"); },
    addEventListener: function () {},
    focus: function () {},
    scrollTop: 0, scrollHeight: 0, value: "",
  };
  el.classList.toggle = function (name) {
    el.classList.set[name] = !el.classList.set[name];
  };
  el.classList.contains = function (name) { return !!el.classList.set[name]; };
  Object.defineProperty(el, "textContent", {
    get: function () { return this._text || ""; },
    set: function (v) { this._text = v; },
  });
  el.attachShadow = function () { return makeElement("shadow-root"); };
  return el;
}

// --- El <script> tal cual lo genera _build_widget_snippet: con
// data-project-id/data-api-base/data-widget-token en su dataset,
// exactamente como el navegador los expondría a partir de los
// atributos data-* del HTML. ---
var scriptEl = makeElement("script");
scriptEl.dataset = { projectId: "p1", apiBase: "https://ejemplo.test", widgetToken: "tok-123", title: "Asistente" };

var domContentLoadedCallback = null;
global.document = {
  currentScript: scriptEl,  // válido solo mientras el script corre de forma síncrona
  readyState: "loading",    // el caso normal: el <script> se ejecuta ANTES de que termine el parseo
  body: makeElement("body"),
  createElement: function (tag) { return makeElement(tag); },
  addEventListener: function (event, cb) {
    if (event === "DOMContentLoaded") { domContentLoadedCallback = cb; }
  },
};
global.window = { RAGSTUDIO_WIDGET_CONFIG: undefined };
var console_error_orig = console.error;
console.error = function (msg) { errors.push(String(msg)); };

// --- Código real de WIDGET_JS (el mismo que sirve GET /widget.js) ---
%(widget_js)s

// En este punto, si el arranque se difirió (readyState era "loading"),
// domContentLoadedCallback quedó registrado y TODAVÍA no corrió --
// exactamente como pasaría en un navegador real, donde currentScript
// ya volvió a ser null para cuando el evento se dispara.
if (domContentLoadedCallback === null) {
  console.log(JSON.stringify({ ok: false, reason: "no se registró DOMContentLoaded -- ¿init() corrió antes de tiempo?" }));
  process.exit(1);
}

// Simula que currentScript ya expiró (así es en un navegador real
// para cuando DOMContentLoaded se dispara) y dispara el evento.
global.document.currentScript = null;
domContentLoadedCallback();

console.log(JSON.stringify({ ok: true, errors: errors, appended: appended }));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no disponible en este entorno")
def test_widget_resolves_config_from_a_script_tag_executed_before_dom_content_loaded(tmp_path):
    harness_path = tmp_path / "widget_currentscript_harness.js"
    harness_path.write_text(_HARNESS % {"widget_js": WIDGET_JS}, encoding="utf-8")

    result = subprocess.run(
        ["node", str(harness_path)], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True

    # El bug (hallazgo A1): con document.currentScript leído dentro de
    # init(), config.projectId/apiBase quedaban undefined y el widget
    # registraba exactamente este error, sin dibujar nada.
    assert not any("Falta data-project-id o data-api-base" in e for e in payload["errors"]), (
        f"el widget no resolvió su configuración -- errores: {payload['errors']!r}"
    )
    # Con la configuración resuelta, init() sí llega a construir la
    # burbuja y el panel (input, botón, contenedores) -- una señal
    # concreta e independiente de que el widget se dibujó de verdad,
    # no solo de que no haya registrado el error.
    assert {"input", "button"}.issubset(set(payload["appended"]))
