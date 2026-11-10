"""Ronda 100 (hallazgo real de NEXOM, AGENTE UDL - LOTE01_Bachillerato):
contexto jerárquico persistido (Chunk.section_path, migración 0023) y usado
en la búsqueda textual/híbrida, sobre un AppContext real (SQLite real,
Qdrant local real; embeddings determinísticos para no depender de red).
Corpus SINTÉTICO: la validación con los documentos reales queda pendiente."""
from __future__ import annotations

import sqlite3

import pytest

from application.pipeline.commands import run_pipeline as rp
from application.pipeline.commands.run_pipeline import RunPipeline
from application.rag.service import RagService
from domain.documents.entities import SourceType
from domain.ingestion.entities import ChunkType, FragmentationStrategy
from domain.pipeline.entities import PipelineItemStatus
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.ingestion_repositories import SqlAlchemyChunkRepository
from infrastructure.database.pipeline_repositories import SqlAlchemyPipelineRunRepository
from infrastructure.database.rag_repositories import SqlAlchemyIndexInfoRepository
from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore

from ..unit.application.fakes_rag import WordOverlapFakeEmbeddingProvider

PLAN = """# Bachillerato — Plantel {p}

## Plan de estudios

### 1er. semestre
* Matemáticas I
* Taller de Lectura y Redacción I

### Área Económico-Administrativa y Humanidades

#### 5.º semestre
* Geografía
* Economía I
* Derecho I
* Clave {s}-EA-5

#### 6.º semestre
* Filosofía
* Economía II
* Clave {s}-EA-6

### Área Físico-Matemática y Químico-Biológicas

#### 5.º semestre
* Geografía
* Cálculo diferencial
* Clave {s}-FM-5

#### 6.º semestre
* Filosofía
* Cálculo Integral
* Clave {s}-FM-6
"""


class Proyecto:
    def __init__(self, ctx, tmp):
        self.ctx, self.tmp = ctx, tmp
        p = ctx.paths
        self.rag = RagService(SqlAlchemyChunkRepository(p), WordOverlapFakeEmbeddingProvider(), QdrantLocalVectorStore(p),
                              SqlAlchemyIndexInfoRepository(p), source_repository=SqlAlchemySourceRepository(p))
        self.runs = SqlAlchemyPipelineRunRepository(p)
        self.pipeline = RunPipeline(SqlAlchemySourceRepository(p), ctx.ingestion_service, self.rag, self.runs)
        self.pid = ctx.project_service.create_project("LOTE01 sintético").id
        meta = ctx.metadata_service
        self.sid = meta.create_schema(self.pid).id
        cat = meta.create_catalog(self.pid, "campus_udl")
        for code, label in (("hilario_medina", "Hilario Medina"), ("torres_landa", "Torres Landa")):
            meta.add_catalog_entry(self.pid, cat.id, code, label)
        meta.add_field_definition(self.pid, self.sid, "campus", "Campus", "seleccion_multiple", multiple=True,
                                  inherited_by_chunks=True, catalog_id=cat.id)
        ing = ctx.ingestion_service
        ing.set_fragmentation_policy(self.pid, "programa_academico", strategy=FragmentationStrategy.POR_ENCABEZADO,
                                     target_tokens=500, overlap_tokens=0, min_tokens=1)
        ing.set_fragmentation_policy(self.pid, "informacion_admisiones",
                                     strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
        self.ids = {}
        self.fuente("tl", "programa_academico", PLAN.format(p="Torres Landa", s="TL"), ["torres_landa"])
        self.fuente("hm", "programa_academico", PLAN.format(p="Hilario Medina", s="HM"), ["hilario_medina"])
        self.fuente("requisitos", "informacion_admisiones",
                    "# Requisitos de ingreso\nCertificado de secundaria, acta de nacimiento y CURP.\n",
                    ["hilario_medina", "torres_landa"])

    def fuente(self, nombre, tipo, texto, campus):
        ruta = self.tmp / f"{nombre}.md"
        ruta.write_text(texto, encoding="utf-8")
        sid = self.ctx.document_service.register_source(self.pid, f"{nombre}.md", SourceType.MARKDOWN,
                                                        location=str(ruta), document_type_code=tipo).id
        for estado in ("en_revision", "validado"):
            self.ctx.document_service.update_validation_status(self.pid, sid, estado)
        self.ctx.metadata_service.set_source_metadata_value(self.pid, self.sid, sid, "campus", campus)
        self.ids[nombre] = sid

    def chunks(self, nombre):
        return self.ctx.ingestion_service.list_chunks(self.pid, self.ids[nombre])

    def marca(self, results, k=1):
        return [next((ln for ln in r.chunk.text.splitlines() if "Clave" in ln), r.chunk.text.splitlines()[0])
                for r in results[:k]]


@pytest.fixture
def proyecto(app_context, tmp_path):
    p = Proyecto(app_context, tmp_path)
    run = p.pipeline.execute(p.pid, schema_id=p.sid)
    assert all(i.status == PipelineItemStatus.EXITOSO for i in run.items)
    return p


def test_ruta_persistida_con_niveles_y_texto_intacto(proyecto):
    ea5 = next(c for c in proyecto.chunks("tl") if "TL-EA-5" in c.text)
    assert [(h.level, h.title) for h in ea5.section_path] == [
        (1, "Bachillerato — Plantel Torres Landa"), (2, "Plan de estudios"),
        (3, "Área Económico-Administrativa y Humanidades"), (4, "5.º semestre")]
    assert ea5.text.startswith("#### 5.º semestre\n* Geografía")  # el texto no se toca
    con = sqlite3.connect(proyecto.ctx.paths.project_db_path(proyecto.pid))
    crudo = con.execute("SELECT section_path FROM chunk WHERE id = ?", (ea5.id,)).fetchone()[0]
    assert '"level": 4' in crudo and "5.º semestre" in crudo
    # Estrategia sin secciones: sin ruta.
    assert all(c.section_path == [] for c in proyecto.chunks("requisitos"))


# Nota: con el proveedor de embeddings DETERMINÍSTICO de las pruebas (solapamiento
# de palabras, no un modelo real), la parte semántica de la híbrida no es
# representativa. El orden exacto se verifica en la búsqueda TEXTUAL (BM25 +
# ruta + ordinales, determinista) y en la híbrida se verifica que la señal
# jerárquica identifica al fragmento correcto y lo deja en el top 2. La medición
# con el modelo real está en docs proyecto/Ronda100_Contexto_Jerarquico/.

def _primero(proyecto, consulta, fuentes):
    return proyecto.marca([r for r in proyecto.rag.search_text(proyecto.pid, consulta, limit=20)
                           if r.chunk.source_id in fuentes])


def test_casos_a_b_c_con_filtro_de_campus(proyecto):
    tl = {proyecto.ids["tl"], proyecto.ids["requisitos"]}
    hm = {proyecto.ids["hm"], proyecto.ids["requisitos"]}
    qa = "materias de quinto semestre del área Económico-Administrativa en el plantel Torres Landa"
    qb = "materias de quinto semestre del área Físico-Matemática en el plantel Torres Landa"
    qc = "materias de quinto semestre del área Físico-Matemática en el plantel Hilario Medina"
    assert _primero(proyecto, qa, tl) == ["* Clave TL-EA-5"]
    assert _primero(proyecto, qb, tl) == ["* Clave TL-FM-5"]
    assert _primero(proyecto, qc, hm) == ["* Clave HM-FM-5"]
    for consulta, fuentes, esperado in ((qa, tl, "TL-EA-5"), (qb, tl, "TL-FM-5"), (qc, hm, "HM-FM-5")):
        r = proyecto.rag.search_hybrid(proyecto.pid, consulta, limit=5, source_ids=fuentes)
        assert any(esperado in m for m in proyecto.marca(r, 2)), (consulta, proyecto.marca(r, 3))
        objetivo = next(x for x in r if esperado in x.chunk.text)
        assert "semestre_5" in objetivo.hierarchy_terms
        # Ningún fragmento de otro plantel: el filtro estructurado manda.
        assert all(x.chunk.source_id in fuentes for x in r)


def test_caso_d_ordinales_equivalentes(proyecto):
    tl = {proyecto.ids["tl"]}
    for q in ("materias del 5.º semestre del área Económico-Administrativa",
              "materias del quinto semestre del área Económico-Administrativa",
              "materias del semestre 5 del área Económico-Administrativa"):
        assert _primero(proyecto, q, tl) == ["* Clave TL-EA-5"], q
    assert _primero(proyecto, "materias del sexto semestre del área Económico-Administrativa", tl) == [
        "* Clave TL-EA-6"]


def test_caso_e_documento_compartido_sigue_primero(proyecto):
    r = proyecto.rag.search_hybrid(proyecto.pid, "requisitos de ingreso acta de nacimiento CURP", limit=5)
    assert r[0].chunk.source_id == proyecto.ids["requisitos"]


def test_la_busqueda_textual_ya_no_devuelve_fragmentos_solo_de_encabezado(proyecto):
    solo_titulo = [c for c in proyecto.chunks("tl") if c.text.strip().lstrip("#").strip() == c.section_title]
    assert solo_titulo, "el plan tiene encabezados de área sin cuerpo propio"
    r = proyecto.rag.search_text(proyecto.pid, "Área Económico-Administrativa y Humanidades", limit=50)
    assert not {c.id for c in solo_titulo} & {x.chunk.id for x in r}
    # Con use_hierarchy=False se conserva el comportamiento anterior (para comparar).
    r0 = proyecto.rag.search_text(proyecto.pid, "Área Económico-Administrativa y Humanidades", limit=50,
                                  use_hierarchy=False)
    assert {c.id for c in solo_titulo} & {x.chunk.id for x in r0}


def test_sin_ruta_guardada_la_senal_jerarquica_no_participa(proyecto):
    """Fragmentos anteriores a la Ronda 100 (section_path NULL): se leen como
    ruta vacía, la señal jerárquica no participa y BM25 puntúa solo su texto."""
    con = sqlite3.connect(proyecto.ctx.paths.project_db_path(proyecto.pid))
    con.execute("UPDATE chunk SET section_path = NULL")
    con.commit()
    con.close()
    assert all(c.section_path == [] for c in proyecto.chunks("tl"))
    q = "materias de quinto semestre del área Económico-Administrativa en el plantel Torres Landa"
    assert all(not r.hierarchy_terms for r in proyecto.rag.search_hybrid(proyecto.pid, q, limit=8))
    from domain.rag.hierarchy import lexical_document
    ea5 = next(c for c in proyecto.chunks("tl") if "TL-EA-5" in c.text)
    assert lexical_document(ea5.text, ea5.section_path) == ea5.text + "\nsemestre_5"


def test_pipeline_reprocesa_solo_las_fuentes_por_encabezado_al_cambiar_la_version(proyecto, monkeypatch):
    # Simula la corrida previa a la Ronda 100 (sin versión de fragmentador) y
    # luego la versión actual: solo las fuentes por_encabezado se reprocesan.
    monkeypatch.setattr(rp, "FRAGMENTER_VERSIONS", {})
    proyecto.pipeline.execute(proyecto.pid, schema_id=proyecto.sid)
    monkeypatch.undo()
    run = proyecto.pipeline.execute(proyecto.pid, schema_id=proyecto.sid)
    estado = {i.source_id: i for i in run.items}
    for nombre in ("tl", "hm"):
        assert estado[proyecto.ids[nombre]].status == PipelineItemStatus.EXITOSO
        assert "Nueva versión del fragmentador por_encabezado" in estado[proyecto.ids[nombre]].reason
    assert estado[proyecto.ids["requisitos"]].status == PipelineItemStatus.OMITIDO
    assert proyecto.pipeline.execute(proyecto.pid, schema_id=proyecto.sid).items[0].status == PipelineItemStatus.OMITIDO


def test_detalle_muestra_ruta_almacenada_y_uso_en_busqueda(proyecto):
    ea5 = next(c for c in proyecto.chunks("tl") if "TL-EA-5" in c.text)
    d = proyecto.ctx.ingestion_service.get_chunk_detail(proyecto.pid, proyecto.ids["tl"], ea5.id)
    assert d.stored_section_path == d.heading_path and d.stored_matches_derived is True
    assert d.retrieval_hierarchy_active
    assert d.retrieval_extra_terms[-1] == "Área Económico-Administrativa y Humanidades"
    assert d.retrieval_ordinal_terms == ["semestre_5"]
    assert d.retrieval_lexical_document.endswith("semestre_5")
    padre = [c for c in proyecto.chunks("tl") if c.chunk_type == ChunkType.PADRE]
    assert all(c.section_path for c in padre)


# ---------- Ronda 101: caso real de validación (LOTE01_Bachillerato) ----------

class _RerankerQuePrefiereSexto:
    """Reproduce el resultado del cross-encoder real en la validación de NEXOM:
    puntúa por palabras en común con la consulta, pero da un plus al "6.º
    semestre", que así queda por encima del "5.º" pedido."""

    model_name = "reranker-de-prueba-6o"

    def score(self, query, passages):
        palabras = {w for w in query.lower().split() if len(w) > 3}
        return [len(palabras & set(p.lower().split())) + (3.0 if "6.º semestre" in p else 0.0) for p in passages]


def _rag_con_reranker(proyecto):
    p = proyecto.ctx.paths
    return RagService(SqlAlchemyChunkRepository(p), WordOverlapFakeEmbeddingProvider(), QdrantLocalVectorStore(p),
                      SqlAlchemyIndexInfoRepository(p), source_repository=SqlAlchemySourceRepository(p),
                      reranker=_RerankerQuePrefiereSexto())


CONSULTA_REAL = ("¿Qué materias se cursan en quinto semestre del área Físico-Matemática y Químico-Biológicas "
                 "en el plantel Torres Landa?")


def test_ronda101_caso_real_con_reranking_el_quinto_semestre_queda_primero(proyecto):
    rag = _rag_con_reranker(proyecto)
    tl = {proyecto.ids["tl"], proyecto.ids["requisitos"]}
    for filtro in (tl, None):
        r = rag.search_hybrid(proyecto.pid, CONSULTA_REAL, limit=12, rerank=True, source_ids=filtro)
        assert proyecto.marca(r, 1) == ["* Clave TL-FM-5"], (filtro is not None, proyecto.marca(r, 3))
        sexto = next(x for x in r if "TL-FM-6" in x.chunk.text)
        assert sexto.hierarchy_conflicts == ["semestre_6"]
        assert r[0].hierarchy_conflicts == []
    # Sin reranking sigue igual (posición 1).
    assert proyecto.marca(rag.search_hybrid(proyecto.pid, CONSULTA_REAL, limit=5, source_ids=tl)) == ["* Clave TL-FM-5"]


def test_ronda101_sin_semestre_en_la_consulta_se_respeta_el_reranker(proyecto):
    rag = _rag_con_reranker(proyecto)
    tl = {proyecto.ids["tl"]}
    r = rag.search_hybrid(proyecto.pid, "materias del área Físico-Matemática y Químico-Biológicas en Torres Landa",
                          limit=5, rerank=True, source_ids=tl)
    assert all(not x.hierarchy_conflicts for x in r)
    assert proyecto.marca(r, 1) == ["* Clave TL-FM-6"]  # sin ordinal pedido, decide el reranker


def test_ronda101_documento_compartido_no_se_afecta(proyecto):
    rag = _rag_con_reranker(proyecto)
    r = rag.search_hybrid(proyecto.pid, "requisitos de ingreso acta de nacimiento CURP", limit=5, rerank=True)
    assert r[0].chunk.source_id == proyecto.ids["requisitos"]
    assert all(not x.hierarchy_conflicts for x in r)
