# -*- coding: utf-8 -*-
"""Cliente HTTP mínimo (solo librería estándar, sin agregar `requests`
como dependencia) para un servidor Ollama LOCAL -- http://localhost:11434
por defecto. Este script vive fuera del paquete `ragstudio` real (Fase
-1, RAG 4): es el prototipo aislado del planificador, no un cambio de
producto.

Requiere que el usuario ya haya instalado Ollama y descargado un modelo
en SU PROPIA máquina (ver README_ejecutar_localmente.md de este mismo
directorio) -- el entorno de trabajo de esta consultoría tiene
ollama.com y huggingface.co bloqueados por la lista blanca de red, así
que este cliente no se pudo probar contra un servidor real end-to-end
desde ahí; sí se probó que el esquema de petición/respuesta coincide
con la documentación oficial de la API de Ollama (`/api/generate`,
`/api/show`)."""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


class OllamaUnavailableError(RuntimeError):
    """El servidor Ollama local no respondió -- revisa que `ollama serve`
    esté corriendo (o que el servicio de systemd que instala el script
    oficial ya lo tenga levantado) antes de correr el benchmark."""


@dataclass
class OllamaResponse:
    text: str
    model: str
    model_digest: str  # hash real del modelo, vía /api/show -- para
    # planner_model_version/hash en la huella de ejecución (sección 4
    # del documento de decisión RAG4: "no negociable desde la Fase -1")
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float


class OllamaClient:
    def __init__(self, model: str, host: str = "http://localhost:11434", timeout_s: float = 240.0):
        # Ronda 71: 1 de 94 preguntas de la primera corrida real
        # (Q074) falló por TimeoutError a los 120s -- inferencia en CPU
        # con un modelo de 3B puede variar bastante según la carga de la
        # máquina. 240s deja margen sin volverse indefinido.
        self.model = model
        self.host = host.rstrip("/")
        self.timeout_s = timeout_s
        self._model_digest_cache: str | None = None

    def _post_json(self, path: str, payload: dict) -> dict:
        url = f"{self.host}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise OllamaUnavailableError(
                f"No se pudo conectar a Ollama en {self.host!r} (¿está corriendo 'ollama serve'? "
                f"¿el modelo {self.model!r} ya se descargó con 'ollama pull {self.model}'?)"
            ) from exc

    def model_digest(self) -> str:
        """sha256 corto del manifest del modelo real (vía /api/show) --
        se usa como planner_model_version/hash en la huella de ejecución.
        Se cachea: no cambia entre llamadas de la misma corrida."""
        if self._model_digest_cache is not None:
            return self._model_digest_cache
        try:
            info = self._post_json("/api/show", {"name": self.model})
            raw = json.dumps(info, sort_keys=True).encode("utf-8")
            self._model_digest_cache = hashlib.sha256(raw).hexdigest()[:16]
        except OllamaUnavailableError:
            self._model_digest_cache = "desconocido"
        return self._model_digest_cache

    def generate(self, prompt: str, temperature: float = 0.0, top_p: float = 1.0) -> OllamaResponse:
        """Llamada de una sola vuelta (sin streaming, para simplificar
        el prototipo) a /api/generate. temperature=0.0 por defecto:
        Sistema B debe ser lo más determinista posible dentro de lo que
        permite un LLM, para que la métrica de "estabilidad entre
        ejecuciones" (tabla 10.2) mida variación real del modelo, no
        variación introducida por muestreo aleatorio innecesario."""
        start = time.monotonic()
        result = self._post_json("/api/generate", {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "top_p": top_p},
        })
        latency_ms = (time.monotonic() - start) * 1000
        return OllamaResponse(
            text=result.get("response", ""),
            model=self.model,
            model_digest=self.model_digest(),
            prompt_tokens=result.get("prompt_eval_count", 0),
            completion_tokens=result.get("eval_count", 0),
            latency_ms=latency_ms,
        )
