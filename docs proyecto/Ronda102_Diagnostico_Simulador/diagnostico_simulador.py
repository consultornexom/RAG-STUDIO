"""Ronda 102 -- DIAGNÓSTICO (sin cambios de código) de la diferencia entre
Búsqueda RAG y el Simulador en la consulta de requisitos de LOTE01_Bachillerato.

Corpus SINTÉTICO que imita la estructura descrita por NEXOM (no son los
documentos reales): dos planes de bachillerato fragmentados por encabezado,
cuya sección "Requisitos de ingreso" solo remite al archivo de requisitos, y
documentos compartidos con documento_completo (requisitos_ingreso.md,
áreas de formación, cualidades del aspirante). Todas las fuentes tienen
nivel_academico = bachillerato (por eso el filtro no descarta ninguna).

Muestra cada etapa del Simulador por separado:
  1) Búsqueda RAG tal como en el Laboratorio (consulta original, sin filtro).
  2) Texto de búsqueda del Simulador tras quitar los valores filtrados.
  3) Candidatos que recibe el Simulador (pool de 20) con y sin reranking.
  4) Afinidad título-intención de cada candidato y orden final (top 5).

Uso (raíz del repositorio, sin red, modelos en data/models):
    python3 "docs proyecto/Ronda102_Diagnostico_Simulador/diagnostico_simulador.py" [--codigo .] [--modelos data/models]
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

PLAN = """# Bachillerato — Plantel {p}

## Información general
El Bachillerato de la Universidad de León en el plantel {p} es un programa escolarizado de seis semestres.

## Plan de estudios

### 1er. semestre
* Matemáticas I
* Química I

### Área Económico-Administrativa y Humanidades

#### 5.º semestre
* Economía I
* Derecho I

## Requisitos de ingreso
Los requisitos de ingreso se describen en el archivo requisitos_ingreso.md.
"""

REQUISITOS = """{titulo}

Para ingresar al Bachillerato de la Universidad de León, el aspirante debe presentar:

* Certificado de secundaria original y dos copias.
* Acta de nacimiento con vigencia no mayor a seis meses.
* CURP actualizada.
* Cuatro fotografías tamaño infantil.
* Comprobante de pago del examen de admisión.

## Proceso de admisión
1. Registro en línea en el portal de admisiones.
2. Aplicación del examen de admisión y del examen psicométrico.
3. Entrevista con la coordinación académica del plantel.
4. Publicación de resultados e inscripción.

## Observaciones
La documentación se entrega en la ventanilla de servicios escolares de cada plantel.
"""

COMPARTIDOS = {
    "areas_formacion.md": "# Áreas de formación\nEl bachillerato ofrece dos áreas a partir del quinto semestre: "
                          "Económico-Administrativa y Humanidades, y Físico-Matemática y Químico-Biológicas.\n",
    "cualidades_aspirante.md": "# Perfil del aspirante\nEl aspirante debe tener interés por el estudio, "
                               "disciplina y responsabilidad.\n",
}

CONSULTA = "¿Cuáles son los requisitos para ingresar al Bachillerato de la Universidad de León?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codigo", type=Path, default=Path("."))
    ap.add_argument("--modelos", type=Path, default=Path("data/models"))
    ap.add_argument("--titulo-requisitos", default="# Requisitos de ingreso al Bachillerato",
                    help="primera línea de requisitos_ingreso.md (documento_completo la usa como título)")
    a = ap.parse_args()
    raiz = a.codigo.resolve()
    sys.path.insert(0, str(raiz))
    sys.path.insert(0, str(raiz / "tests" / "unit" / "application"))
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

    from application.conversational.queries.simulate_conversation import SimulateConversation, _section_title
    from application.ingestion.service import IngestionService
    from application.metadata.service import MetadataService
    from application.rag.service import RagService
    from domain.conversational.entities import ConversationalVariable, Intent
    from domain.conversational.section_affinity import SectionAffinity
    from domain.documents.entities import Source, SourceType
    from domain.ingestion.entities import FragmentationStrategy
    from infrastructure.embeddings.fastembed_provider import FastEmbedEmbeddingProvider
    from infrastructure.extraction.text_extractors import TxtExtractor
    from infrastructure.rerankers.fastembed_cross_encoder import FastEmbedReranker

    P = "p"
    fuentes, chunks = InMemorySourceRepository(), InMemoryChunkRepository()
    esquemas, catalogos, valores = (InMemoryMetadataSchemaRepository(), InMemoryCatalogRepository(),
                                    InMemorySourceMetadataRepository())
    meta = MetadataService(esquemas, catalogos, valores, fuentes)
    ing = IngestionService(fuentes, TxtExtractor(), InMemoryExtractionRepository(),
                           InMemoryFragmentationPolicyRepository(), chunks, esquemas, valores)
    rag = RagService(chunks, FastEmbedEmbeddingProvider(cache_dir=a.modelos.resolve()), FakeVectorStore(),
                     InMemoryIndexInfoRepository(), source_repository=fuentes,
                     reranker=FastEmbedReranker(cache_dir=a.modelos.resolve()))
    sid = meta.create_schema(P).id
    cat = meta.create_catalog(P, "nivel")
    meta.add_catalog_entry(P, cat.id, "bachillerato", "Bachillerato")
    meta.add_field_definition(P, sid, "nivel_academico", "Nivel académico", "seleccion_unica",
                              inherited_by_chunks=True, catalog_id=cat.id)
    ing.set_fragmentation_policy(P, "programa_academico", strategy=FragmentationStrategy.POR_ENCABEZADO,
                                 target_tokens=500, overlap_tokens=0, min_tokens=1)
    for tipo in ("informacion_admisiones", "informacion_academica"):
        ing.set_fragmentation_policy(P, tipo, strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
    docs = {"bachillerato_torres_landa.md": ("programa_academico", PLAN.format(p="Torres Landa")),
            "bachillerato_hilario_medina.md": ("programa_academico", PLAN.format(p="Hilario Medina")),
            "requisitos_ingreso.md": ("informacion_admisiones", REQUISITOS.replace("{titulo}", a.titulo_requisitos)),
            **{k: ("informacion_academica", v) for k, v in COMPARTIDOS.items()}}
    tmp = Path(tempfile.mkdtemp())
    titulo_de = {}
    for nombre, (tipo, texto) in docs.items():
        (tmp / nombre).write_text(texto, encoding="utf-8")
        src = Source(project_id=P, title=nombre, source_type=SourceType.MARKDOWN, location=str(tmp / nombre),
                     document_type_code=tipo, validation_status="validado")
        fuentes.save(src)
        titulo_de[src.id] = nombre
        meta.set_source_metadata_value(P, sid, src.id, "nivel_academico", "bachillerato")
        ing.extract_source_text(P, src.id)
        ing.fragment_source(P, src.id, schema_id=sid, document_type_code=tipo)
        rag.index_source(P, src.id)

    intents, variables = InMemoryIntentRepository(), InMemoryConversationalVariableRepository()
    variables.save(ConversationalVariable(project_id=P, code="nivel_academico", label="Nivel",
                                          metadata_field_id="nivel_academico"))
    for nombre, ejemplos in (
        ("consultar_requisitos_bachillerato", ["¿Cuáles son los requisitos para entrar al bachillerato?",
                                               "¿Qué necesito para ingresar al bachillerato?",
                                               "¿Qué documentos necesito para entrar al bachillerato?"]),
        ("consultar_areas_programa", ["¿Qué áreas se ofrecen en el bachillerato?"]),
        ("consultar_cualidades_aspirante", ["¿Qué cualidades debe tener un aspirante?"]),
        ("consultar_informacion_programa", ["Dame información del bachillerato"]),
    ):
        intents.save(Intent(project_id=P, name=nombre, positive_examples=ejemplos, priority=50,
                            required_variables=["nivel_academico"]))
    sim = SimulateConversation(intents, variables, InMemoryGuardrailRuleRepository(),
                               InMemoryChannelingSchemeRepository(), valores, rag, source_repository=fuentes,
                               schema_repository=esquemas, catalog_repository=catalogos)

    def fila(r):
        return f"{titulo_de[r.chunk.source_id]:32} «{_section_title(r.chunk)[:45]}»"

    def mostrar(titulo, resultados, k=8):
        print(f"\n{titulo}")
        for i, r in enumerate(resultados[:k], 1):
            print(f"  {i:2}. {fila(r)}")

    mostrar("1) Búsqueda RAG (Laboratorio): consulta original, híbrida, SIN reranking",
            rag.search_hybrid(P, CONSULTA, limit=10))
    mostrar("1b) Búsqueda RAG (Laboratorio): consulta original, híbrida, CON reranking",
            rag.search_hybrid(P, CONSULTA, limit=10, rerank=True))

    trace = sim.execute(P, CONSULTA, {"nivel_academico": "bachillerato"}, limit=5)
    print(f"\nIntención: {trace.matched_intent_name}  confianza {trace.confidence:.3f}  acción {trace.action.value}")
    print(f"Filtros: {trace.applied_metadata_filters}  descartadas: {trace.excluded_by_metadata_filter}")
    print(f"2) Texto de búsqueda del Simulador: {trace.retrieval_query!r}")
    texto = trace.retrieval_query or CONSULTA
    permitidas = set(fuentes_id for fuentes_id in titulo_de)
    pool_rr = rag.search_hybrid(P, texto, limit=20, only_usable_sources=True, rerank=rag.has_reranker,
                                source_ids=permitidas)
    pool_sin = rag.search_hybrid(P, texto, limit=20, only_usable_sources=True, source_ids=permitidas)
    mostrar(f"3a) Pool del Simulador (rerank={rag.has_reranker}, como en producción)", pool_rr, 10)
    mostrar("3b) Mismo pool SIN reranking", pool_sin, 10)
    intent = next(i for i in intents.list_for_project(P) if i.name == trace.matched_intent_name)
    afinidad = SectionAffinity(intent, intents.list_for_project(P), CONSULTA, sim._catalog_mention_masker(P))
    print("\n4) Afinidad título-intención de los candidatos del pool (3a):")
    for i, r in enumerate(pool_rr[:12], 1):
        print(f"  {i:2}. afinidad {afinidad.score(_section_title(r.chunk)):.2f}  {fila(r)}")
    mostrar("5) Resultado final del Simulador (top 5)", trace.search_results, 5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
