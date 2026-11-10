"""Ronda 100 -- evaluación comparativa de recuperación ANTES/DESPUÉS del
contexto jerárquico, sobre un corpus SINTÉTICO (no son los documentos reales
de AGENTE UDL: la validación final en LOTE01_Bachillerato queda pendiente).

Uso, desde la raíz de cualquier versión del código (no escribe nada en el
proyecto; todo es en memoria; sin red, con los modelos ya descargados en
data/models del repositorio indicado en --modelos):

    python3 evaluacion_recuperacion.py --codigo <raíz_del_código> --modelos <dir_data_models> \
        --salida resultados.json [--etiqueta antes|despues]

Mide, por modo de búsqueda (semántica, textual, híbrida, híbrida+reranking)
y con/sin filtro estructurado de campus:
- fragmento: R@1, R@3, MRR y posición del fragmento correcto;
- fuente: R@3, MRR y posición de la fuente correcta (primer fragmento de la
  fuente esperada), métrica DISTINTA a la de fragmento.
Un caso solo cuenta como acierto de fragmento si el fragmento recuperado
contiene el texto verificable esperado (no basta la fuente correcta).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PLAN = """# Bachillerato — Plantel {plantel}

Programa de bachillerato general en modalidad escolarizada del plantel {plantel}.

## Plan de estudios

### 1er. semestre
* Matemáticas I
* Química I
* Ética I
* Taller de Lectura y Redacción I

### 4to. semestre
* Matemáticas IV
* Biología II
* Legalidad Empresarial
* Mercadotecnia

### Área Económico-Administrativa y Humanidades

#### 5.º semestre
* Geografía
* Estructura Socioeconómica de México
* Economía I
* Matemáticas Financieras I
* Derecho I
* Finanzas
* {marca_ea5}

#### 6.º semestre
* Filosofía
* Ecología y Medio Ambiente
* Economía II
* Derecho II
* {marca_ea6}

### Área Físico-Matemática y Químico-Biológicas

#### 5.º semestre
* Geografía
* Estructura Socioeconómica de México
* Temas Selectos de Química I
* Temas Selectos de Física I
* Cálculo diferencial
* Finanzas
* {marca_fm5}

#### 6.º semestre
* Filosofía
* Ecología y Medio Ambiente
* Temas Selectos de Química II
* Cálculo Integral
* {marca_fm6}

## Requisitos de ingreso
Aprobación del examen de admisión, acta de nacimiento y certificado de secundaria.
"""

DOCS = {
    "requisitos_ingreso.md": ("informacion_admisiones", "documento_completo", ["hilario_medina", "torres_landa"],
        "# Requisitos de ingreso\nPara ingresar al bachillerato se requiere certificado de secundaria, acta de "
        "nacimiento, CURP, cuatro fotografías y aprobar el examen de admisión.\n"),
    "cualidades_aspirante.md": ("informacion_academica", "documento_completo", ["hilario_medina", "torres_landa"],
        "# Perfil del aspirante\nEl aspirante debe tener interés por el estudio, disciplina, responsabilidad, "
        "trabajo en equipo y buena comunicación oral y escrita.\n"),
    "areas_formacion.md": ("informacion_academica", "documento_completo", ["hilario_medina", "torres_landa"],
        "# Áreas de formación\nEl bachillerato ofrece dos áreas de formación propedéutica a partir del quinto "
        "semestre: Económico-Administrativa y Humanidades, y Físico-Matemática y Químico-Biológicas.\n"),
    "reglamento.md": ("reglamento", "por_articulo", ["hilario_medina", "torres_landa"],
        "Artículo 4. Las inscripciones se realizan cada semestre en las fechas publicadas.\n"
        "Artículo 5. El alumno podrá solicitar baja temporal hasta por dos semestres.\n"
        "Artículo 6. La calificación mínima aprobatoria es seis.\n"),
    "calendario.md": ("informacion_academica", "por_tamanio", ["hilario_medina", "torres_landa"],
        "Calendario escolar. Las clases del semestre inician en agosto y terminan en diciembre. "
        "El periodo de exámenes finales es la segunda semana de diciembre. Las vacaciones de invierno "
        "comienzan después de la entrega de calificaciones.\n"),
}

CASOS = [
    # (id, grupo, consulta, fuente esperada, texto verificable del fragmento, campus del filtro)
    ("A", "area", "¿Qué materias se cursan en quinto semestre del área Económico-Administrativa en el plantel Torres Landa?",
     "bachillerato_torres_landa.md", "TL-EA-5", "torres_landa"),
    ("B", "area", "¿Qué materias se cursan en quinto semestre del área Físico-Matemática en el plantel Torres Landa?",
     "bachillerato_torres_landa.md", "TL-FM-5", "torres_landa"),
    ("C1", "plantel", "¿Qué materias se cursan en quinto semestre del área Económico-Administrativa en el plantel Hilario Medina?",
     "bachillerato_hilario_medina.md", "HM-EA-5", "hilario_medina"),
    ("C2", "plantel", "materias de sexto semestre del área Físico-Matemática en Hilario Medina",
     "bachillerato_hilario_medina.md", "HM-FM-6", "hilario_medina"),
    ("D1", "ordinal", "materias del 5.º semestre del área Económico-Administrativa en Torres Landa",
     "bachillerato_torres_landa.md", "TL-EA-5", "torres_landa"),
    ("D2", "ordinal", "materias del semestre 5 del área Económico-Administrativa en Torres Landa",
     "bachillerato_torres_landa.md", "TL-EA-5", "torres_landa"),
    ("D3", "ordinal", "materias de 6to semestre área Económico-Administrativa Torres Landa",
     "bachillerato_torres_landa.md", "TL-EA-6", "torres_landa"),
    ("D4", "ordinal", "¿Qué materias lleva el primer semestre en Torres Landa?",
     "bachillerato_torres_landa.md", "Taller de Lectura y Redacción I", "torres_landa"),
    ("D5", "falso_positivo", "¿Qué dice el artículo 5 del reglamento sobre la baja temporal?",
     "reglamento.md", "Artículo 5.", None),
    ("E1", "compartida", "¿Cuáles son los requisitos de ingreso al bachillerato?",
     "requisitos_ingreso.md", "CURP", None),
    ("E2", "compartida", "¿Qué áreas de formación ofrece el bachillerato?",
     "areas_formacion.md", "dos áreas de formación", None),
    ("E3", "compartida", "¿Qué cualidades debe tener el aspirante?",
     "cualidades_aspirante.md", "disciplina, responsabilidad", None),
    ("F1", "regresion_estrategias", "¿Cuándo inician las clases del semestre?",
     "calendario.md", "inician en agosto", None),
    ("F2", "regresion_estrategias", "calificación mínima aprobatoria",
     "reglamento.md", "Artículo 6.", None),
]


def _plan(plantel: str, sigla: str) -> str:
    return PLAN.format(plantel=plantel, marca_ea5=f"Clave {sigla}-EA-5", marca_ea6=f"Clave {sigla}-EA-6",
                       marca_fm5=f"Clave {sigla}-FM-5", marca_fm6=f"Clave {sigla}-FM-6")


def construir(codigo: Path, modelos: Path, tmp: Path):
    sys.path.insert(0, str(codigo))
    sys.path.insert(0, str(codigo / "tests" / "unit" / "application"))
    from application.ingestion.service import IngestionService
    from application.rag.service import RagService
    from domain.documents.entities import Source, SourceType
    from domain.ingestion.entities import FragmentationStrategy
    from fakes_documents import InMemorySourceRepository
    from fakes_ingestion import (
        InMemoryChunkRepository, InMemoryExtractionRepository, InMemoryFragmentationPolicyRepository,
    )
    from fakes_metadata import InMemoryMetadataSchemaRepository, InMemorySourceMetadataRepository
    from fakes_rag import FakeVectorStore, InMemoryIndexInfoRepository
    from infrastructure.embeddings.fastembed_provider import FastEmbedEmbeddingProvider
    from infrastructure.extraction.text_extractors import TxtExtractor
    from infrastructure.rerankers.fastembed_cross_encoder import FastEmbedReranker

    extractor = TxtExtractor()
    sources, chunks = InMemorySourceRepository(), InMemoryChunkRepository()
    policies = InMemoryFragmentationPolicyRepository()
    ingestion = IngestionService(sources, extractor, InMemoryExtractionRepository(), policies, chunks,
                                 InMemoryMetadataSchemaRepository(), InMemorySourceMetadataRepository())
    rag = RagService(chunks, FastEmbedEmbeddingProvider(cache_dir=modelos), FakeVectorStore(),
                     InMemoryIndexInfoRepository(), source_repository=sources,
                     reranker=FastEmbedReranker(cache_dir=modelos))
    estrategias = {"programa_academico": FragmentationStrategy.POR_ENCABEZADO,
                   "documento_completo": FragmentationStrategy.DOCUMENTO_COMPLETO,
                   "por_articulo": FragmentationStrategy.POR_ARTICULO,
                   "por_tamanio": FragmentationStrategy.POR_TAMANIO}
    documentos = {
        "bachillerato_torres_landa.md": ("programa_academico", "programa_academico", ["torres_landa"],
                                         _plan("Torres Landa", "TL")),
        "bachillerato_hilario_medina.md": ("programa_academico", "programa_academico", ["hilario_medina"],
                                           _plan("Hilario Medina", "HM")),
        **DOCS,
    }
    campus: dict[str, list[str]] = {}
    ids: dict[str, str] = {}
    for nombre, (tipo, estrategia, planteles, texto) in documentos.items():
        ruta = tmp / nombre
        ruta.write_text(texto, encoding="utf-8")
        ingestion.set_fragmentation_policy("p", tipo, strategy=estrategias[estrategia],
                                           target_tokens=500, overlap_tokens=0 if estrategia != "por_tamanio" else 10,
                                           min_tokens=1 if estrategia != "por_tamanio" else 5)
        src = Source(project_id="p", title=nombre, source_type=SourceType.MARKDOWN, location=str(ruta),
                     document_type_code=tipo, validation_status="validado")
        sources.save(src)
        ids[nombre] = src.id
        campus[src.id] = planteles
        ingestion.extract_source_text("p", src.id)
        ingestion.fragment_source("p", src.id, document_type_code=tipo)
        rag.index_source("p", src.id)
    return rag, ids, campus


def evaluar(rag, ids, campus, usar_rerank: bool):
    def filtrar(resultados, f):
        return [r for r in resultados if f is None or r.chunk.source_id in f][:10]

    # Semántica y textual: se pide de más y se filtra después, igual en ambas
    # versiones del código (la semántica no acepta source_ids en ninguna).
    modos = {
        "semantica": lambda q, f: filtrar(rag.search("p", q, limit=100), f),
        "textual": lambda q, f: filtrar(rag.search_text("p", q, limit=100), f),
        "hibrida": lambda q, f: rag.search_hybrid("p", q, limit=10, source_ids=f),
    }
    if usar_rerank:
        modos["hibrida_rerank"] = lambda q, f: rag.search_hybrid("p", q, limit=10, source_ids=f, rerank=True)
    salida = {}
    for modo, buscar in modos.items():
        for con_filtro in (False, True):
            filas = []
            for cid, grupo, consulta, fuente, marca, plantel in CASOS:
                filtro = None
                if con_filtro and plantel:
                    filtro = {sid for sid, vals in campus.items() if plantel in vals}
                resultados = buscar(consulta, filtro)
                pos_frag = next((i for i, r in enumerate(resultados, 1)
                                 if r.chunk.source_id == ids[fuente] and marca in r.chunk.text), None)
                fuentes_orden = list(dict.fromkeys(r.chunk.source_id for r in resultados))
                pos_fuente = (fuentes_orden.index(ids[fuente]) + 1) if ids[fuente] in fuentes_orden else None
                filas.append({"caso": cid, "grupo": grupo, "pos_fragmento": pos_frag, "pos_fuente": pos_fuente,
                              "top1": resultados[0].chunk.text.splitlines()[0][:60] if resultados else None})
            salida[f"{modo}|{'con_filtro' if con_filtro else 'sin_filtro'}"] = filas
    return salida


def resumen(filas):
    def m(clave, k=None):
        pos = [f[clave] for f in filas]
        if k is not None:
            return round(sum(1 for p in pos if p and p <= k) / len(pos), 3)
        return round(sum(1 / p for p in pos if p) / len(pos), 3)
    return {"frag_R@1": m("pos_fragmento", 1), "frag_R@3": m("pos_fragmento", 3), "frag_MRR": m("pos_fragmento"),
            "fuente_R@3": m("pos_fuente", 3), "fuente_MRR": m("pos_fuente")}


def main() -> int:
    import tempfile

    ap = argparse.ArgumentParser()
    ap.add_argument("--codigo", required=True, type=Path)
    ap.add_argument("--modelos", required=True, type=Path)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--etiqueta", default="")
    ap.add_argument("--sin-rerank", action="store_true")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        rag, ids, campus = construir(a.codigo.resolve(), a.modelos.resolve(), Path(tmp))
        detalle = evaluar(rag, ids, campus, not a.sin_rerank)
    res = {"etiqueta": a.etiqueta, "detalle": detalle,
           "resumen": {k: {"global": resumen(v), **{g: resumen([f for f in v if f["grupo"] == g])
                                                     for g in sorted({f["grupo"] for f in v})}}
                       for k, v in detalle.items()}}
    a.salida.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in res["resumen"].items():
        print(k, v["global"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
