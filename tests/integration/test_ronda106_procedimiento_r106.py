"""Ronda 106 (autorizada por NEXOM): procedimiento r106 (V + Y + R) contra
r105b con los CINCO archivos reales de LOTE01_Bachillerato y los modelos
reales (data/models, sin red), con el motor real (SimulateConversation),
no con el prototipo.

Configuración real de AGENTE UDL (confirmada por NEXOM): planes
por_encabezado 500/60/80 y compartidos documento_completo; intención
`consultar_requisitos_bachillerato` con su descripción y sus 8 + 8 ejemplos
reales, sin datos obligatorios, opcionales plantel y nivel_academico,
prioridad 50. Las demás intenciones son las supuestas de las Rondas 102-105.

Pruebas obligatorias de la autorización (sección 4):
1. Los 14 casos de LOTE01 con las políticas reales: UDL-BACH-003 (R1) y la
   consulta de documentos (R2) con requisitos_ingreso.md en 1.º, requisitos
   por delante de los fragmentos puente y ninguna consulta peor que r105b.
2. Las otras estrategias de fragmentación de los experimentos (compartidos
   por_encabezado y todo por_tamanio): ninguna consulta peor que r105b.
3. El corpus sintético de la Ronda 102: requisitos_ingreso.md por delante
   de las secciones que solo remiten a él.
Además: intención, confianza, acción y filtros idénticos en r105b y r106.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
DOCS = RAIZ / "tests" / "fixtures" / "lote01_bachillerato"
SINTETICO = RAIZ / "docs proyecto" / "Ronda105c_Diagnostico_Post_P1" / "corpus_sintetico_r102"
MODELOS = RAIZ / "data" / "models"

if not any(MODELOS.glob("*paraphrase-multilingual*")):
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
from domain.conversational.entities import ConversationalVariable, Intent  # noqa: E402
from domain.documents.entities import Source, SourceType  # noqa: E402
from domain.ingestion.entities import FragmentationStrategy  # noqa: E402
from infrastructure.embeddings.fastembed_provider import FastEmbedEmbeddingProvider  # noqa: E402
from infrastructure.extraction.text_extractors import TxtExtractor  # noqa: E402

P = "lote01"
ARCHIVOS = {
    "bachillerato_hilario_medina.md": ("programa_academico", ["hilario_medina"]),
    "bachillerato_torres_landa.md": ("programa_academico", ["torres_landa"]),
    "requisitos_ingreso.md": ("informacion_admisiones", ["hilario_medina", "torres_landa"]),
    "areas_formacion.md": ("informacion_academica", ["hilario_medina", "torres_landa"]),
    "cualidades_aspirante.md": ("informacion_academica", ["hilario_medina", "torres_landa"]),
}
# (nombre, descripción, positivos, negativos, obligatorias, opcionales, prioridad)
INTENCIONES = [
    ("consultar_requisitos_bachillerato",
     "Informar sobre los requisitos generales y documentos necesarios para ingresar al Bachillerato de la "
     "Universidad de León, utilizando exclusivamente información institucional autorizada.",
     ["¿Cuáles son los requisitos para ingresar al bachillerato?", "¿Qué documentos necesito para inscribirme?",
      "¿Qué necesito para entrar a la preparatoria?", "¿Piden certificado de secundaria?",
      "¿Qué papeles debo entregar para ingresar?", "¿Cuáles son los requisitos de admisión?",
      "¿Qué documentos solicitan para nuevo ingreso?", "¿Los requisitos son iguales en ambos planteles?"],
     ["¿Qué materias llevan en quinto semestre?", "¿Cuál es el plan de estudios?",
      "¿Cuánto cuesta la inscripción?", "¿Dónde se encuentra el plantel Hilario Medina?",
      "¿Qué áreas de formación ofrece el bachillerato?", "¿Cuáles son las cualidades de un aspirante?",
      "¿Cuándo comienzan las clases?", "Quiero hablar con un asesor."],
     [], ["plantel", "nivel_academico"], 50),
    ("consultar_areas_programa", "",
     ["¿Qué áreas se ofrecen en el bachillerato?", "¿Qué áreas tiene el bachillerato?", "¿Qué ofrece el programa?"],
     ["¿Cuáles son los requisitos de ingreso?", "¿Qué cualidades debe tener un aspirante?"],
     ["nivel_academico"], ["plantel"], None),
    ("consultar_cualidades_aspirante",
     "Consultar las cualidades o características esperadas del aspirante al bachillerato.",
     ["¿Qué cualidades debe tener un aspirante?", "¿Cuál es el perfil del aspirante?"],
     ["¿Cuáles son los requisitos de ingreso?", "¿Qué áreas se ofrecen?"],
     ["nivel_academico"], ["plantel"], None),
    ("consultar_informacion_programa", "Consultar información general del programa de bachillerato.",
     ["Dame información del bachillerato", "¿Cómo es el programa de bachillerato?"],
     ["¿Cuáles son los requisitos de ingreso?", "¿Qué cualidades debe tener un aspirante?"],
     ["nivel_academico"], ["plantel"], None),
]
CASOS = [
    # (id, consulta, fuente esperada, texto verificable) -- docs proyecto/
    # Ronda102_Diagnostico_Simulador/evaluacion_simulador.py
    ("R1", "¿Cuáles son los requisitos para ingresar al Bachillerato de la Universidad de León?",
     "requisitos_ingreso.md", "Acta de nacimiento con vigencia"),
    ("R2", "¿Qué documentos necesito para entrar al bachillerato?", "requisitos_ingreso.md", "CURP: original"),
    ("R3", "Requisitos de ingreso al bachillerato en el plantel Torres Landa", "requisitos_ingreso.md",
     "CURP: original"),
    ("S1", "¿Qué áreas se ofrecen en el bachillerato?", "areas_formacion.md", "se indican las siguientes áreas"),
    ("S2", "¿Qué cualidades debe tener un aspirante al bachillerato?", "cualidades_aspirante.md",
     "Gusto por el estudio"),
    ("G1", "Dame información del bachillerato del plantel Torres Landa", "bachillerato_torres_landa.md",
     "Plantel: Torres Landa."),
    ("G2", "¿Cómo es el programa de bachillerato en Hilario Medina?", "bachillerato_hilario_medina.md",
     "Plantel: Hilario Medina."),
    ("P1", "¿Qué materias se cursan en quinto semestre del área Económico-Administrativa del bachillerato en el "
     "plantel Torres Landa?", "bachillerato_torres_landa.md", "Contabilidad I"),
    ("P2", "¿Qué materias se cursan en quinto semestre del área Físico-Matemática y Químico-Biológicas del "
     "bachillerato en el plantel Torres Landa?", "bachillerato_torres_landa.md", "Dibujo I"),
    ("P3", "¿Qué materias se cursan en sexto semestre del área Físico-Matemática y Químico-Biológicas del "
     "bachillerato en el plantel Hilario Medina?", "bachillerato_hilario_medina.md", "Cálculo Integral"),
    ("P4", "¿Qué materias lleva el primer semestre del bachillerato en Torres Landa?", "bachillerato_torres_landa.md",
     "Metodología de la Investigación"),
    ("P5", "materias del 5.º semestre del área Económico-Administrativa del bachillerato en Hilario Medina",
     "bachillerato_hilario_medina.md", "Economía I"),
    ("P6", "materias de 6to semestre del área Económico-Administrativa del bachillerato en Torres Landa",
     "bachillerato_torres_landa.md", "Proyecto Emprendedor"),
    ("O1", "¿Cuál es el reconocimiento de validez oficial del bachillerato en el plantel Torres Landa?",
     "bachillerato_torres_landa.md", "04/0235"),
]


def construir(compartidos: str = "documento_completo", documentos: Path = DOCS, token_counter=None):
    """Corpus LOTE01 con el motor real. compartidos: "documento_completo"
    (configuración real de AGENTE UDL), "por_encabezado" o
    "por_tamanio_todos" (todas las fuentes por_tamanio 500/60/80).
    Devuelve ({"r105b": simulador, "r106": simulador}, titulo_de)."""
    fuentes, chunks = InMemorySourceRepository(), InMemoryChunkRepository()
    esquemas, catalogos, valores = (InMemoryMetadataSchemaRepository(), InMemoryCatalogRepository(),
                                    InMemorySourceMetadataRepository())
    meta = MetadataService(esquemas, catalogos, valores, fuentes)
    ing = IngestionService(fuentes, TxtExtractor(), InMemoryExtractionRepository(),
                           InMemoryFragmentationPolicyRepository(), chunks, esquemas, valores,
                           token_counter=token_counter)
    rag = RagService(chunks, FastEmbedEmbeddingProvider(cache_dir=MODELOS), FakeVectorStore(),
                     InMemoryIndexInfoRepository(), source_repository=fuentes)
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
    tamanio = dict(target_tokens=500, overlap_tokens=60, min_tokens=80)
    for tipo in ("programa_academico", "informacion_admisiones", "informacion_academica"):
        if compartidos == "por_tamanio_todos":
            politica = dict(strategy=FragmentationStrategy.POR_TAMANIO, **tamanio)
        elif tipo == "programa_academico" or compartidos == "por_encabezado":
            politica = dict(strategy=FragmentationStrategy.POR_ENCABEZADO, **tamanio)
        else:
            politica = dict(strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
        ing.set_fragmentation_policy(P, tipo, **politica)
    titulo_de: dict[str, str] = {}
    for nombre, (tipo, planteles) in ARCHIVOS.items():
        src = Source(project_id=P, title=nombre, source_type=SourceType.MARKDOWN, location=str(documentos / nombre),
                     document_type_code=tipo, validation_status="validado")
        fuentes.save(src)
        titulo_de[src.id] = nombre
        meta.set_source_metadata_value(P, sid, src.id, "nivel_academico", "bachillerato")
        meta.set_source_metadata_value(P, sid, src.id, "plantel", planteles)
        ing.extract_source_text(P, src.id)
        ing.fragment_source(P, src.id, schema_id=sid, document_type_code=tipo)
        rag.index_source(P, src.id)

    intents, variables = InMemoryIntentRepository(), InMemoryConversationalVariableRepository()
    variables.save(ConversationalVariable(project_id=P, code="nivel_academico", label="Nivel académico",
                                          metadata_field_id="nivel_academico"))
    variables.save(ConversationalVariable(project_id=P, code="plantel", label="Plantel", metadata_field_id="plantel"))
    for nombre, descripcion, positivos, negativos, obligatorias, opcionales, prioridad in INTENCIONES:
        extra = {"priority": prioridad} if prioridad is not None else {}
        intents.save(Intent(project_id=P, name=nombre, description=descripcion, positive_examples=positivos,
                            negative_examples=negativos, required_variables=obligatorias,
                            optional_variables=opcionales, **extra))

    def simulador(procedimiento: str) -> SimulateConversation:
        return SimulateConversation(intents, variables, InMemoryGuardrailRuleRepository(),
                                    InMemoryChannelingSchemeRepository(), valores, rag, source_repository=fuentes,
                                    schema_repository=esquemas, catalog_repository=catalogos,
                                    retrieval_procedure=lambda _pid: procedimiento)

    return {"r105b": simulador("r105b"), "r106": simulador("r106")}, titulo_de


def posicion(trace, titulo_de, fuente, texto):
    for i, r in enumerate(trace.search_results, 1):
        if titulo_de[r.chunk.source_id] == fuente and texto in r.chunk.text:
            return i
    return None


def evaluar(simuladores, titulo_de, casos=CASOS) -> dict:
    """{procedimiento: {id: (posición, decisión, traza)}}"""
    salida: dict = {}
    for procedimiento, sim in simuladores.items():
        salida[procedimiento] = {}
        for cid, consulta, fuente, texto in casos:
            trace = sim.execute(P, consulta, {}, limit=5)
            decision = (trace.matched_intent_name, trace.action.value, trace.confidence,
                        dict(trace.applied_metadata_filters), list(trace.fired_rules), trace.retrieval_query)
            salida[procedimiento][cid] = (posicion(trace, titulo_de, fuente, texto), decision, trace)
    return salida


def mrr(resultado: dict) -> float:
    return sum(1 / p for p, _d, _t in resultado.values() if p) / len(resultado)


def _peor(a, b) -> bool:
    """True si la posición b es peor que a (None = fuera del top 5)."""
    return (b or 99) > (a or 99)


def _comprobar_sin_regresiones_ni_cambios_de_decision(res: dict) -> None:
    base, nuevo = res["r105b"], res["r106"]
    peores = {cid: (base[cid][0], nuevo[cid][0]) for cid in base if _peor(base[cid][0], nuevo[cid][0])}
    assert not peores, f"consultas peores que r105b: {peores}"
    cambios = {cid: (base[cid][1], nuevo[cid][1]) for cid in base if base[cid][1] != nuevo[cid][1]}
    assert not cambios, f"decisiones distintas: {cambios}"
    for cid in base:
        assert base[cid][2].retrieval_pipeline == "r105b" and nuevo[cid][2].retrieval_pipeline == "r106"


def test_configuracion_real_de_agente_udl():
    simuladores, titulo_de = construir("documento_completo")
    res = evaluar(simuladores, titulo_de)
    # r105b reproduce lo observado por NEXOM (UDL-BACH-003 en 2.º; documentos fuera del top 5).
    assert res["r105b"]["R1"][0] == 2 and res["r105b"]["R2"][0] is None
    # r106: requisitos en 1.º en UDL-BACH-003 y en la consulta de documentos.
    assert res["r106"]["R1"][0] == 1 and res["r106"]["R2"][0] == 1
    # Requisitos por delante de los fragmentos puente (planes que remiten a requisitos_ingreso.md).
    trace = res["r106"]["R2"][2]
    puentes = [i for i, r in enumerate(trace.search_results, 1)
               if titulo_de[r.chunk.source_id].startswith("bachillerato_") and "requisitos_ingreso.md" in r.chunk.text]
    assert all(res["r106"]["R2"][0] < p for p in puentes)
    assert mrr(res["r106"]) == pytest.approx(1.0) and mrr(res["r105b"]) == pytest.approx(0.857, abs=1e-3)
    _comprobar_sin_regresiones_ni_cambios_de_decision(res)


@pytest.mark.parametrize("compartidos", ["por_encabezado", "por_tamanio_todos"])
def test_otras_estrategias_sin_regresiones(compartidos):
    simuladores, titulo_de = construir(compartidos)
    res = evaluar(simuladores, titulo_de)
    _comprobar_sin_regresiones_ni_cambios_de_decision(res)
    assert mrr(res["r106"]) >= mrr(res["r105b"])


@pytest.mark.skipif(not SINTETICO.exists(), reason="corpus sintético de la Ronda 102 no disponible")
def test_corpus_sintetico_ronda102_requisitos_delante_de_las_secciones_que_remiten():
    simuladores, titulo_de = construir("documento_completo", documentos=SINTETICO)
    caso = [c for c in CASOS if c[0] == "R1"]
    res = evaluar(simuladores, titulo_de, caso)
    assert res["r105b"]["R1"][0] == 1
    assert res["r106"]["R1"][0] == 1
    trace = res["r106"]["R1"][2]
    fuentes = [titulo_de[r.chunk.source_id] for r in trace.search_results]
    primero_puente = next((i for i, f in enumerate(fuentes) if f.startswith("bachillerato_")), len(fuentes))
    assert fuentes.index("requisitos_ingreso.md") < primero_puente
    assert res["r105b"]["R1"][1] == res["r106"]["R1"][1]
