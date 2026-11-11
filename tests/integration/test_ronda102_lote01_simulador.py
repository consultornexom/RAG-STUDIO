"""Ronda 102 -- regresión con los CINCO archivos reales de
LOTE01_Bachillerato (tests/fixtures/lote01_bachillerato, entregados por
NEXOM; se cargan tal cual, con su encabezado YAML) y los modelos reales
del proyecto (embeddings multilingües y cross-encoder, desde data/models,
sin red).

Hallazgo real: «¿Cuáles son los requisitos para ingresar al Bachillerato de
la Universidad de León?» -- Búsqueda RAG ponía requisitos_ingreso.md entre
los primeros, el Simulador lo sacaba del top 5. Causas (diagnóstico
Ronda 102): la afinidad título-intención era la clave principal del orden
(C1) y los documentos completos con encabezado YAML tenían "---" como
título (C2).

Se comprueba con y sin reranking, sin perder información general, planes
de estudio, ordinales ni documentos compartidos. Supuestos del proyecto
(no se tiene el .agentproj de NEXOM): ver docs proyecto/
Ronda102_Diagnostico_Simulador/evaluacion_simulador.py."""
from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
DOCS = RAIZ / "tests" / "fixtures" / "lote01_bachillerato"
MODELOS = RAIZ / "data" / "models"

if not (MODELOS / "models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q").exists() and not any(
    MODELOS.glob("*paraphrase-multilingual*")
):
    pytest.skip("Modelos locales no disponibles en data/models", allow_module_level=True)

sys.path.insert(0, str(RAIZ / "tests" / "unit" / "application"))

from fakes_conversational import (  # noqa: E402
    InMemoryChannelingSchemeRepository, InMemoryConversationalVariableRepository,
    InMemoryGuardrailRuleRepository, InMemoryIntentRepository,
)
from fakes_documents import InMemorySourceRepository  # noqa: E402
from fakes_ingestion import (  # noqa: E402
    InMemoryChunkRepository, InMemoryExtractionRepository, InMemoryFragmentationPolicyRepository,
)
from fakes_metadata import (  # noqa: E402
    InMemoryCatalogRepository, InMemoryMetadataSchemaRepository, InMemorySourceMetadataRepository,
)
from fakes_rag import FakeVectorStore, InMemoryIndexInfoRepository  # noqa: E402

from application.conversational.queries.simulate_conversation import SimulateConversation  # noqa: E402
from application.ingestion.service import IngestionService  # noqa: E402
from application.metadata.service import MetadataService  # noqa: E402
from application.rag.service import RagService  # noqa: E402
from domain.conversational.entities import ConversationalVariable, Intent, RuleActionType  # noqa: E402
from domain.documents.entities import Source, SourceType  # noqa: E402
from domain.ingestion.entities import FragmentationStrategy  # noqa: E402
from infrastructure.embeddings.fastembed_provider import FastEmbedEmbeddingProvider  # noqa: E402
from infrastructure.extraction.text_extractors import TxtExtractor  # noqa: E402
from infrastructure.rerankers.fastembed_cross_encoder import FastEmbedReranker  # noqa: E402

P = "lote01"
ARCHIVOS = {
    "bachillerato_hilario_medina.md": ("programa_academico", ["hilario_medina"]),
    "bachillerato_torres_landa.md": ("programa_academico", ["torres_landa"]),
    "requisitos_ingreso.md": ("informacion_admisiones", ["hilario_medina", "torres_landa"]),
    "areas_formacion.md": ("informacion_academica", ["hilario_medina", "torres_landa"]),
    "cualidades_aspirante.md": ("informacion_academica", ["hilario_medina", "torres_landa"]),
}
INTENCIONES = [
    ("consultar_requisitos_bachillerato",
     "Consultar los requisitos de ingreso al programa de bachillerato de la Universidad de León, diferenciando "
     "esta consulta de requisitos correspondientes a licenciaturas, maestrías, posgrados u otros niveles educativos.",
     ["¿Cuáles son los requisitos para entrar al bachillerato?", "¿Qué necesito para ingresar al bachillerato?",
      "¿Qué documentos necesito para entrar al bachillerato?"],
     ["¿Cuáles son los requisitos para entrar a una maestría?", "¿Qué necesito para ingresar a una licenciatura?"]),
    ("consultar_areas_programa", "",
     ["¿Qué áreas se ofrecen en el bachillerato?", "¿Qué áreas tiene el bachillerato?", "¿Qué ofrece el programa?"],
     ["¿Cuáles son los requisitos de ingreso?", "¿Qué cualidades debe tener un aspirante?"]),
    ("consultar_cualidades_aspirante",
     "Consultar las cualidades o características esperadas del aspirante al bachillerato.",
     ["¿Qué cualidades debe tener un aspirante?", "¿Cuál es el perfil del aspirante?"],
     ["¿Cuáles son los requisitos de ingreso?", "¿Qué áreas se ofrecen?"]),
    ("consultar_informacion_programa", "Consultar información general del programa de bachillerato.",
     ["Dame información del bachillerato", "¿Cómo es el programa de bachillerato?"],
     ["¿Cuáles son los requisitos de ingreso?", "¿Qué cualidades debe tener un aspirante?"]),
    ("consultar_plan_estudios", "Consultar las materias del plan de estudios del bachillerato por semestre y área.",
     ["¿Qué materias tiene el bachillerato?", "¿Qué materias se cursan en quinto semestre?"],
     ["¿Cuáles son los requisitos de ingreso?"]),
]
CONSULTA_NEXOM = "¿Cuáles son los requisitos para ingresar al Bachillerato de la Universidad de León?"


def test_los_documentos_reales_estan_intactos():
    """Condición 6 de NEXOM: no se modifica la estructura de los
    documentos. Los fixtures coinciden con el hash del manifiesto."""
    with (DOCS / "manifiesto_original.csv").open(encoding="utf-8") as archivo:
        esperados = {fila["titulo"]: fila["hash_contenido"] for fila in csv.DictReader(archivo)}
    assert set(esperados) == set(ARCHIVOS)
    for nombre, digest in esperados.items():
        assert hashlib.sha256((DOCS / nombre).read_bytes()).hexdigest() == digest


@pytest.fixture(scope="module")
def corpus():
    fuentes, chunks = InMemorySourceRepository(), InMemoryChunkRepository()
    esquemas, catalogos, valores = (InMemoryMetadataSchemaRepository(), InMemoryCatalogRepository(),
                                    InMemorySourceMetadataRepository())
    meta = MetadataService(esquemas, catalogos, valores, fuentes)
    ing = IngestionService(fuentes, TxtExtractor(), InMemoryExtractionRepository(),
                           InMemoryFragmentationPolicyRepository(), chunks, esquemas, valores)
    embeddings = FastEmbedEmbeddingProvider(cache_dir=MODELOS)
    vectores, info = FakeVectorStore(), InMemoryIndexInfoRepository()
    rag_con = RagService(chunks, embeddings, vectores, info, source_repository=fuentes,
                         reranker=FastEmbedReranker(cache_dir=MODELOS))
    rag_sin = RagService(chunks, embeddings, vectores, info, source_repository=fuentes)

    sid = meta.create_schema(P).id
    nivel = meta.create_catalog(P, "nivel")
    meta.add_catalog_entry(P, nivel.id, "bachillerato", "Bachillerato")
    meta.add_field_definition(P, sid, "nivel_academico", "Nivel académico", "seleccion_unica",
                              inherited_by_chunks=True, catalog_id=nivel.id)
    plantel = meta.create_catalog(P, "plantel")
    meta.add_catalog_entry(P, plantel.id, "hilario_medina", "Hilario Medina")
    meta.add_catalog_entry(P, plantel.id, "torres_landa", "Torres Landa")
    meta.add_field_definition(P, sid, "plantel", "Plantel", "seleccion_multiple", inherited_by_chunks=True,
                              catalog_id=plantel.id, multiple=True)
    ing.set_fragmentation_policy(P, "programa_academico", strategy=FragmentationStrategy.POR_ENCABEZADO,
                                 target_tokens=500, overlap_tokens=60, min_tokens=80)
    for tipo in ("informacion_admisiones", "informacion_academica"):
        ing.set_fragmentation_policy(P, tipo, strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
    titulo_de: dict[str, str] = {}
    for nombre, (tipo, planteles) in ARCHIVOS.items():
        src = Source(project_id=P, title=nombre, source_type=SourceType.MARKDOWN, location=str(DOCS / nombre),
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
    variables.save(ConversationalVariable(project_id=P, code="plantel", label="Plantel", metadata_field_id="plantel"))
    for nombre, descripcion, positivos, negativos in INTENCIONES:
        intents.save(Intent(project_id=P, name=nombre, description=descripcion, positive_examples=positivos,
                            negative_examples=negativos, required_variables=["nivel_academico"],
                            optional_variables=["plantel"]))

    def simulador(rag):
        return SimulateConversation(intents, variables, InMemoryGuardrailRuleRepository(),
                                    InMemoryChannelingSchemeRepository(), valores, rag, source_repository=fuentes,
                                    schema_repository=esquemas, catalog_repository=catalogos)

    return {"con": simulador(rag_con), "sin": simulador(rag_sin)}, titulo_de


def _posicion(trace, titulo_de, fuente, texto):
    for i, r in enumerate(trace.search_results, 1):
        if titulo_de[r.chunk.source_id] == fuente and texto in r.chunk.text:
            return i
    return None


@pytest.mark.parametrize("variante", ["con", "sin"])
def test_consulta_de_nexom_requisitos_primero(corpus, variante):
    simuladores, titulo_de = corpus
    trace = simuladores[variante].execute(P, CONSULTA_NEXOM, {}, limit=5)
    assert trace.matched_intent_name == "consultar_requisitos_bachillerato"
    assert trace.applied_metadata_filters == {"nivel_academico": "bachillerato"}
    assert trace.action == RuleActionType.RESPONDER
    assert _posicion(trace, titulo_de, "requisitos_ingreso.md", "Acta de nacimiento con vigencia") == 1
    assert trace.result_ordering[0].affinity_title == "Requisitos de ingreso — Bachillerato UDL"
    assert trace.reranking_applied is (variante == "con")


CASOS = [
    # (consulta, fuente, texto verificable, peor posición admitida)
    ("¿Qué documentos necesito para entrar al bachillerato?", "requisitos_ingreso.md", "CURP: original", 3),
    ("Requisitos de ingreso al bachillerato en el plantel Torres Landa", "requisitos_ingreso.md", "CURP: original", 1),
    ("¿Qué áreas se ofrecen en el bachillerato?", "areas_formacion.md", "se indican las siguientes áreas", 1),
    ("¿Qué cualidades debe tener un aspirante al bachillerato?", "cualidades_aspirante.md", "Gusto por el estudio", 1),
    ("Dame información del bachillerato del plantel Torres Landa", "bachillerato_torres_landa.md",
     "Plantel: Torres Landa.", 1),
    ("¿Qué materias se cursan en quinto semestre del área Económico-Administrativa del bachillerato en el plantel "
     "Torres Landa?", "bachillerato_torres_landa.md", "Contabilidad I", 1),
    ("¿Qué materias se cursan en sexto semestre del área Físico-Matemática y Químico-Biológicas del bachillerato en "
     "el plantel Hilario Medina?", "bachillerato_hilario_medina.md", "Cálculo Integral", 1),
    ("materias del 5.º semestre del área Económico-Administrativa del bachillerato en Hilario Medina",
     "bachillerato_hilario_medina.md", "Economía I", 1),
]


@pytest.mark.parametrize("variante", ["con", "sin"])
def test_sin_perder_informacion_general_planes_ordinales_ni_compartidos(corpus, variante):
    simuladores, titulo_de = corpus
    fallos = []
    for consulta, fuente, texto, peor in CASOS:
        trace = simuladores[variante].execute(P, consulta, {}, limit=5)
        posicion = _posicion(trace, titulo_de, fuente, texto)
        if posicion is None or posicion > peor:
            fallos.append((consulta, posicion, peor))
    assert not fallos, fallos
