"""Ronda 102 -- evaluación del Simulador con los CINCO archivos reales de
LOTE01_Bachillerato (entregados por NEXOM con manifiesto.csv), antes y
después de las correcciones C1/C2/C4.

Separa, para cada consulta, tres etapas (petición de NEXOM: "separar las
métricas de recuperación inicial de las posteriores al reordenamiento
conversacional"):

  lab   -- Búsqueda RAG del Laboratorio: consulta original, híbrida, sin
           filtros (top 20).
  pool  -- recuperación inicial del Simulador: texto de búsqueda del
           Simulador, fuentes permitidas por los filtros, pool de 20.
  final -- resultado del Simulador tras el reordenamiento conversacional
           (top 5, lo que recibe el agente).

Cada etapa se mide con y sin reranking (RagService con o sin cross-encoder;
así el script corre igual en el código anterior, donde el Simulador no
tenía ajuste propio de reranking). Un acierto de fragmento exige un
fragmento de la fuente esperada que contenga el texto verificable.

Supuestos (no se tiene el proyecto LOTE01 de NEXOM, solo sus documentos):
- Políticas: planes por_encabezado (500/60/80, la del proyecto histórico de
  Bachillerato); documentos compartidos documento_completo.
- Metadatos: nivel_academico = bachillerato en las cinco fuentes; plantel
  (varios valores) según planteles_aplicables / plantel del encabezado YAML.
- Intenciones: las cuatro activas del proyecto histórico de Bachillerato
  (textos reales) más consultar_plan_estudios (supuesta). nivel_academico
  obligatoria, plantel opcional.
- Los documentos se cargan TAL CUAL (con su encabezado YAML); no se
  modifica su estructura ni sus metadatos.

Uso (raíz del código a evaluar; sin red; modelos en data/models):
    python3 evaluacion_simulador.py --codigo <raíz> --documentos <dir con los 5 .md> \
        --salida resultados.json [--etiqueta antes|despues] [--min-tokens 80]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ARCHIVOS = {
    # nombre: (tipo de documento, planteles)
    "bachillerato_hilario_medina.md": ("programa_academico", ["hilario_medina"]),
    "bachillerato_torres_landa.md": ("programa_academico", ["torres_landa"]),
    "requisitos_ingreso.md": ("informacion_admisiones", ["hilario_medina", "torres_landa"]),
    "areas_formacion.md": ("informacion_academica", ["hilario_medina", "torres_landa"]),
    "cualidades_aspirante.md": ("informacion_academica", ["hilario_medina", "torres_landa"]),
}

INTENCIONES = [
    # Textos reales del proyecto histórico de Bachillerato (activas).
    ("consultar_requisitos_bachillerato",
     "Consultar los requisitos de ingreso al programa de bachillerato de la Universidad de León, diferenciando "
     "esta consulta de requisitos correspondientes a licenciaturas, maestrías, posgrados u otros niveles educativos.",
     ["¿Cuáles son los requisitos para entrar al bachillerato?", "¿Qué necesito para ingresar al bachillerato?",
      "¿Qué documentos necesito para entrar al bachillerato?"],
     ["¿Cuáles son los requisitos para entrar a una maestría?", "¿Qué necesito para ingresar a una licenciatura?",
      "Requisitos para estudiar un posgrado", "¿Cuáles son los requisitos de admisión para una maestría?",
      "¿Qué documentos necesito para entrar a una universidad?"]),
    ("consultar_areas_programa", "",
     ["¿Qué áreas se ofrecen en el bachillerato?", "¿Qué áreas tiene el bachillerato?", "¿Qué ofrece el programa?"],
     ["¿Cuáles son los requisitos de ingreso?", "¿Qué cualidades debe tener un aspirante?"]),
    ("consultar_cualidades_aspirante",
     "Consultar las cualidades o características esperadas del aspirante al bachillerato.",
     ["¿Qué cualidades debe tener un aspirante?", "¿Cuál es el perfil del aspirante?",
      "¿Qué características debe tener quien quiera entrar?"],
     ["¿Cuáles son los requisitos de ingreso?", "¿Qué áreas se ofrecen?"]),
    ("consultar_informacion_programa", "Consultar información general del programa de bachillerato.",
     ["Dame información del bachillerato", "¿Cómo es el programa de bachillerato?",
      "¿Qué información tienen sobre el bachillerato?"],
     ["¿Cuáles son los requisitos de ingreso?", "¿Qué cualidades debe tener un aspirante?"]),
    # Supuesta (el proyecto histórico no la tenía).
    ("consultar_plan_estudios", "Consultar las materias del plan de estudios del bachillerato por semestre y área.",
     ["¿Qué materias tiene el bachillerato?", "¿Qué materias se cursan en quinto semestre?",
      "¿Cuál es el plan de estudios del área Físico-Matemática?"],
     ["¿Cuáles son los requisitos de ingreso?"]),
]

CASOS = [
    # (id, grupo, consulta, fuente esperada, texto verificable)
    ("R1", "requisitos", "¿Cuáles son los requisitos para ingresar al Bachillerato de la Universidad de León?",
     "requisitos_ingreso.md", "Acta de nacimiento con vigencia"),
    ("R2", "requisitos", "¿Qué documentos necesito para entrar al bachillerato?",
     "requisitos_ingreso.md", "CURP: original"),
    ("R3", "requisitos", "Requisitos de ingreso al bachillerato en el plantel Torres Landa",
     "requisitos_ingreso.md", "CURP: original"),
    ("S1", "compartido", "¿Qué áreas se ofrecen en el bachillerato?",
     "areas_formacion.md", "se indican las siguientes áreas"),
    ("S2", "compartido", "¿Qué cualidades debe tener un aspirante al bachillerato?",
     "cualidades_aspirante.md", "Gusto por el estudio"),
    ("G1", "general", "Dame información del bachillerato del plantel Torres Landa",
     "bachillerato_torres_landa.md", "Plantel: Torres Landa."),
    ("G2", "general", "¿Cómo es el programa de bachillerato en Hilario Medina?",
     "bachillerato_hilario_medina.md", "Plantel: Hilario Medina."),
    ("P1", "plan", "¿Qué materias se cursan en quinto semestre del área Económico-Administrativa del "
     "bachillerato en el plantel Torres Landa?", "bachillerato_torres_landa.md", "Contabilidad I"),
    ("P2", "plan", "¿Qué materias se cursan en quinto semestre del área Físico-Matemática y Químico-Biológicas del "
     "bachillerato en el plantel Torres Landa?", "bachillerato_torres_landa.md", "Dibujo I"),
    ("P3", "plan", "¿Qué materias se cursan en sexto semestre del área Físico-Matemática y Químico-Biológicas del "
     "bachillerato en el plantel Hilario Medina?", "bachillerato_hilario_medina.md", "Cálculo Integral"),
    ("P4", "plan", "¿Qué materias lleva el primer semestre del bachillerato en Torres Landa?",
     "bachillerato_torres_landa.md", "Metodología de la Investigación"),
    ("P5", "ordinal", "materias del 5.º semestre del área Económico-Administrativa del bachillerato en Hilario Medina",
     "bachillerato_hilario_medina.md", "Economía I"),
    ("P6", "ordinal", "materias de 6to semestre del área Económico-Administrativa del bachillerato en Torres Landa",
     "bachillerato_torres_landa.md", "Proyecto Emprendedor"),
    ("O1", "general", "¿Cuál es el reconocimiento de validez oficial del bachillerato en el plantel Torres Landa?",
     "bachillerato_torres_landa.md", "04/0235"),
]


def _documentos(directorio: Path) -> dict[str, Path]:
    """Nombre real -> archivo. Acepta los nombres reales o los del
    manifiesto (ruta_archivo)."""
    rutas = {n: directorio / n for n in ARCHIVOS if (directorio / n).exists()}
    manifiesto = directorio / "manifiesto.csv"
    if len(rutas) < len(ARCHIVOS) and manifiesto.exists():
        for fila in csv.DictReader(manifiesto.open(encoding="utf-8")):
            if fila["titulo"] in ARCHIVOS and (directorio / fila["ruta_archivo"]).exists():
                rutas[fila["titulo"]] = directorio / fila["ruta_archivo"]
    faltan = sorted(set(ARCHIVOS) - set(rutas))
    if faltan:
        raise SystemExit(f"Faltan documentos: {faltan}")
    return rutas


def construir(codigo: Path, modelos: Path, documentos: Path, min_tokens: int):
    sys.path.insert(0, str(codigo))
    sys.path.insert(0, str(codigo / "tests" / "unit" / "application"))
    from fakes_conversational import (
        InMemoryChannelingSchemeRepository, InMemoryConversationalVariableRepository,
        InMemoryGuardrailRuleRepository, InMemoryIntentRepository,
    )
    from fakes_documents import InMemorySourceRepository
    from fakes_ingestion import (
        InMemoryChunkRepository, InMemoryExtractionRepository, InMemoryFragmentationPolicyRepository,
    )
    from fakes_metadata import (
        InMemoryCatalogRepository, InMemoryMetadataSchemaRepository, InMemorySourceMetadataRepository,
    )
    from fakes_rag import FakeVectorStore, InMemoryIndexInfoRepository

    from application.conversational.queries.simulate_conversation import SimulateConversation
    from application.ingestion.service import IngestionService
    from application.metadata.service import MetadataService
    from application.rag.service import RagService
    from domain.conversational.entities import ConversationalVariable, Intent
    from domain.documents.entities import Source, SourceType
    from domain.ingestion.entities import FragmentationStrategy
    from infrastructure.embeddings.fastembed_provider import FastEmbedEmbeddingProvider
    from infrastructure.extraction.text_extractors import TxtExtractor
    from infrastructure.rerankers.fastembed_cross_encoder import FastEmbedReranker

    P = "lote01"
    fuentes, chunks = InMemorySourceRepository(), InMemoryChunkRepository()
    esquemas, catalogos, valores = (InMemoryMetadataSchemaRepository(), InMemoryCatalogRepository(),
                                    InMemorySourceMetadataRepository())
    meta = MetadataService(esquemas, catalogos, valores, fuentes)
    ing = IngestionService(fuentes, TxtExtractor(), InMemoryExtractionRepository(),
                           InMemoryFragmentationPolicyRepository(), chunks, esquemas, valores)
    embeddings = FastEmbedEmbeddingProvider(cache_dir=modelos)
    vectores, info = FakeVectorStore(), InMemoryIndexInfoRepository()
    rag_con = RagService(chunks, embeddings, vectores, info, source_repository=fuentes,
                         reranker=FastEmbedReranker(cache_dir=modelos))
    rag_sin = RagService(chunks, embeddings, vectores, info, source_repository=fuentes)

    sid = meta.create_schema(P).id
    cat_nivel = meta.create_catalog(P, "nivel")
    meta.add_catalog_entry(P, cat_nivel.id, "bachillerato", "Bachillerato")
    meta.add_field_definition(P, sid, "nivel_academico", "Nivel académico", "seleccion_unica",
                              inherited_by_chunks=True, catalog_id=cat_nivel.id)
    cat_plantel = meta.create_catalog(P, "plantel")
    meta.add_catalog_entry(P, cat_plantel.id, "hilario_medina", "Hilario Medina")
    meta.add_catalog_entry(P, cat_plantel.id, "torres_landa", "Torres Landa")
    meta.add_field_definition(P, sid, "plantel", "Plantel", "seleccion_multiple",
                              inherited_by_chunks=True, catalog_id=cat_plantel.id, multiple=True)
    ing.set_fragmentation_policy(P, "programa_academico", strategy=FragmentationStrategy.POR_ENCABEZADO,
                                 target_tokens=500, overlap_tokens=60 if min_tokens >= 60 else 0,
                                 min_tokens=min_tokens)
    for tipo in ("informacion_admisiones", "informacion_academica"):
        ing.set_fragmentation_policy(P, tipo, strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)

    titulo_de: dict[str, str] = {}
    for nombre, ruta in _documentos(documentos).items():
        tipo, planteles = ARCHIVOS[nombre]
        src = Source(project_id=P, title=nombre, source_type=SourceType.MARKDOWN, location=str(ruta),
                     document_type_code=tipo, validation_status="validado")
        fuentes.save(src)
        titulo_de[src.id] = nombre
        meta.set_source_metadata_value(P, sid, src.id, "nivel_academico", "bachillerato")
        meta.set_source_metadata_value(P, sid, src.id, "plantel", planteles)
        ing.extract_source_text(P, src.id)
        ing.fragment_source(P, src.id, schema_id=sid, document_type_code=tipo)
        rag_con.index_source(P, src.id)

    intents, variables = InMemoryIntentRepository(), InMemoryConversationalVariableRepository()
    variables.save(ConversationalVariable(project_id=P, code="nivel_academico", label="Nivel académico",
                                          metadata_field_id="nivel_academico"))
    variables.save(ConversationalVariable(project_id=P, code="plantel", label="Plantel",
                                          metadata_field_id="plantel"))
    for nombre, descripcion, positivos, negativos in INTENCIONES:
        intents.save(Intent(project_id=P, name=nombre, description=descripcion, positive_examples=positivos,
                            negative_examples=negativos, priority=50, required_variables=["nivel_academico"],
                            optional_variables=["plantel"]))

    def simulador(rag):
        return SimulateConversation(intents, variables, InMemoryGuardrailRuleRepository(),
                                    InMemoryChannelingSchemeRepository(), valores, rag, source_repository=fuentes,
                                    schema_repository=esquemas, catalog_repository=catalogos)

    return P, {"con_reranking": (rag_con, simulador(rag_con)), "sin_reranking": (rag_sin, simulador(rag_sin))}, \
        titulo_de, fuentes, variables


def _posiciones(resultados, titulo_de, fuente, texto):
    pos_fuente = pos_frag = None
    for i, r in enumerate(resultados, 1):
        if titulo_de[r.chunk.source_id] != fuente:
            continue
        pos_fuente = pos_fuente or i
        if texto in (r.chunk.text or ""):
            pos_frag = pos_frag or i
    return pos_fuente, pos_frag


def _titulo(r, titulo_de):
    """Fuente y título de sección tal como lo ve el Simulador del código
    evaluado (desde la Ronda 102 recibe también el título de la fuente)."""
    from application.conversational.queries import simulate_conversation as sc
    try:
        titulo = sc._section_title(r.chunk, titulo_de[r.chunk.source_id])
    except TypeError:  # código anterior a la Ronda 102
        titulo = sc._section_title(r.chunk)
    return f"{titulo_de[r.chunk.source_id]} «{titulo[:50]}»"


def _metricas(posiciones: list) -> dict:
    n = len(posiciones)
    return {
        "R@1": sum(1 for p in posiciones if p and p <= 1) / n,
        "R@3": sum(1 for p in posiciones if p and p <= 3) / n,
        "R@5": sum(1 for p in posiciones if p and p <= 5) / n,
        "MRR": round(sum(1 / p for p in posiciones if p) / n, 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codigo", type=Path, default=Path("."))
    ap.add_argument("--modelos", type=Path, default=Path("data/models"))
    ap.add_argument("--documentos", type=Path, required=True)
    ap.add_argument("--salida", type=Path)
    ap.add_argument("--etiqueta", default="")
    ap.add_argument("--min-tokens", type=int, default=80,
                    help="min_tokens de la política por_encabezado de los planes (80 = proyecto histórico)")
    ap.add_argument("--variante", choices=["con_reranking", "sin_reranking", "ambas"], default="ambas")
    ap.add_argument("--casos", default="", help="ids separados por coma (vacío = todos); los resultados se "
                    "acumulan en --salida si ya existe, para correr por partes")
    a = ap.parse_args()
    P, variantes, titulo_de, fuentes, variables = construir(
        a.codigo.resolve(), a.modelos.resolve(), a.documentos.resolve(), a.min_tokens)
    salida = {"etiqueta": a.etiqueta, "min_tokens": a.min_tokens, "casos": {}, "metricas": {}}
    if a.salida and a.salida.exists():
        salida = json.loads(a.salida.read_text(encoding="utf-8"))
    elegidos = set(filter(None, a.casos.split(",")))
    for variante, (rag, sim) in variantes.items():
        if a.variante not in ("ambas", variante):
            continue
        print(f"\n===== {variante} =====")
        for cid, grupo, consulta, fuente, texto in CASOS:
            if elegidos and cid not in elegidos:
                continue
            lab = rag.search_hybrid(P, consulta, limit=20, rerank=rag.has_reranker)
            trace = sim.execute(P, consulta, {}, limit=5)
            todas = fuentes.list_for_project(P)
            permitidas = {s.id for s in todas if sim._source_matches_filters(
                P, s.id, variables.list_for_project(P), trace.applied_metadata_filters)}
            pool = rag.search_hybrid(P, trace.retrieval_query or consulta, limit=20, only_usable_sources=True,
                                     rerank=rag.has_reranker, source_ids=permitidas) \
                if trace.applied_metadata_filters else lab
            final = trace.search_results
            r = {
                "grupo": grupo, "consulta": consulta, "intencion": trace.matched_intent_name,
                "accion": trace.action.value, "filtros": trace.applied_metadata_filters,
                "texto_busqueda": trace.retrieval_query,
                "lab": _posiciones(lab, titulo_de, fuente, texto),
                "pool": _posiciones(pool, titulo_de, fuente, texto),
                "final": _posiciones(final, titulo_de, fuente, texto),
                "final_top5": [_titulo(x, titulo_de) for x in final],
            }
            salida["casos"].setdefault(variante, {})[cid] = r
            print(f"{cid:3} {grupo:11} int={trace.matched_intent_name or '-':34} "
                  f"frag lab={r['lab'][1]} pool={r['pool'][1]} final={r['final'][1]}  "
                  f"(fuente final={r['final'][0]}) acción={r['accion']}")
            if r["final"][1] != 1:
                for i, t in enumerate(r["final_top5"], 1):
                    print(f"        {i}. {t}")
    # Métricas sobre todos los casos acumulados, por variante, etapa y grupo.
    for variante, casos in salida["casos"].items():
        salida["metricas"][variante] = {}
        grupos = ["todos", *sorted({c["grupo"] for c in casos.values()})]
        for grupo in grupos:
            elegidos_g = [c for c in casos.values() if grupo in ("todos", c["grupo"])]
            salida["metricas"][variante][grupo] = {
                etapa: _metricas([c[etapa][1] for c in elegidos_g]) for etapa in ("lab", "pool", "final")
            }
        print(f"\n[{variante}] {len(casos)} casos")
        for etapa, m in salida["metricas"][variante]["todos"].items():
            print(f"  {etapa:6} {m}")
    if a.salida:
        a.salida.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
