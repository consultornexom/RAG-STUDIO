"""Ronda 105 -- experimento controlado (solo lectura, en memoria) sobre la
REPRESENTACIÓN de los fragmentos: ¿cuánto se parece la consulta del
incidente a cada variante de texto, con el modelo de embeddings real del
proyecto y con el cross-encoder?

Variantes construidas a partir de los archivos reales de LOTE01
(tests/fixtures/lote01_bachillerato, copias íntegras verificadas por hash):
  REQ_completo         requisitos_ingreso.md tal cual (documento_completo, con YAML)
  REQ_sin_yaml         el mismo texto sin el bloque YAML
  REQ_contenido        solo la sección "## Contenido"
  REQ_contenido_ctx    "# Requisitos de ingreso — Bachillerato UDL" + "## Contenido"
  PUENTE_TL            sección "Información compartida aplicable a este plantel" (Torres Landa)
  PUENTE_TL_sin_refs   la misma sin las líneas que nombran archivos .md
  PROCEDENCIA_TL       sección "Procedencia" del plan Torres Landa
  INFO_GENERAL_TL      sección "Información general" del plan Torres Landa

No modifica archivos, índices ni evidencias.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
DOCS = RAIZ / "tests" / "fixtures" / "lote01_bachillerato"
MODELOS = RAIZ / "data" / "models"

CONSULTAS = {
    "texto_busqueda_simulador": "¿Qué documentos necesito para entrar ?",
    "consulta_original": "¿Qué documentos necesito para entrar al bachillerato?",
}


def seccion(texto: str, titulo: str) -> str:
    m = re.search(r"(?m)^(#{2,6}) " + re.escape(titulo) + r"\s*$", texto)
    if not m:
        raise SystemExit(f"sin sección {titulo}")
    nivel = len(m.group(1))
    resto = texto[m.start():]
    salto = resto.find("\n") + 1
    fin = re.search(r"(?m)^#{1," + str(nivel) + r"} ", resto[salto:])
    return (resto[: salto + fin.start()] if fin else resto).strip()


def sin_yaml(texto: str) -> str:
    if texto.startswith("---"):
        fin = texto.find("\n---", 3)
        return texto[fin + 4:].lstrip("\n")
    return texto


def coseno(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def main() -> int:
    from infrastructure.embeddings.fastembed_provider import FastEmbedEmbeddingProvider
    from infrastructure.rerankers.fastembed_cross_encoder import FastEmbedReranker

    req = (DOCS / "requisitos_ingreso.md").read_text(encoding="utf-8")
    tl = (DOCS / "bachillerato_torres_landa.md").read_text(encoding="utf-8")
    puente = seccion(tl, "Información compartida aplicable a este plantel")
    variantes = {
        "REQ_completo": req,
        "REQ_sin_yaml": sin_yaml(req),
        "REQ_contenido": seccion(req, "Contenido"),
        "REQ_contenido_ctx": "# Requisitos de ingreso — Bachillerato UDL\n\n" + seccion(req, "Contenido"),
        "PUENTE_TL": puente,
        "PUENTE_TL_sin_refs": "\n".join(linea for linea in puente.split("\n") if ".md" not in linea),
        "PROCEDENCIA_TL": seccion(tl, "Procedencia"),
        "INFO_GENERAL_TL": seccion(tl, "Información general"),
    }
    emb = FastEmbedEmbeddingProvider(cache_dir=MODELOS)
    rer = FastEmbedReranker(cache_dir=MODELOS)
    vectores = dict(zip(variantes, emb.embed_texts(list(variantes.values())), strict=True))
    print(f"modelo de embeddings: {emb.model_name}; reranker: {rer.model_name}\n")
    for nombre_q, q in CONSULTAS.items():
        vq = emb.embed_query(q)
        puntajes = rer.score(q, list(variantes.values()))
        print(f"Consulta [{nombre_q}]: {q!r}")
        filas = sorted(((coseno(vq, vectores[k]), k, p) for k, p in zip(variantes, puntajes, strict=True)),
                       key=lambda f: f[0], reverse=True)
        for cos, k, p in filas:
            palabras = len(re.findall(r"\w+", variantes[k]))
            print(f"   coseno {cos:.3f}  reranker {p:+7.3f}  palabras {palabras:4}  {k}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
