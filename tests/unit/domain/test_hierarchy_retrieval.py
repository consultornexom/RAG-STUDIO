"""Ronda 100: funciones puras del contexto jerárquico en la búsqueda
(domain.rag.hierarchy) y ruta de encabezados al fragmentar."""
import pytest

from domain.rag.hierarchy import (
    content_terms,
    ordinal_conflicts,
    contextualized_text,
    hierarchy_match,
    hierarchy_rank,
    lexical_document,
    lexical_query,
    ordinal_terms,
)


@pytest.mark.parametrize("texto", [
    "5.º semestre", "5º semestre", "5° semestre", "5to semestre", "5to. semestre", "quinto semestre",
    "Quinto Semestre", "semestre 5", "5.o semestre", "5a. semestre",
])
def test_equivalencias_de_quinto_semestre(texto):
    assert ordinal_terms(texto) == ["semestre_5"]


@pytest.mark.parametrize("texto", [
    "artículo 5", "apartado 5", "inciso 5", "fracción 5", "dura 6 semestres", "5 semestres", "el semestre 2026",
    "Cap. 5 o semestre", "semestre 10%", "5. Semestre",
])
def test_sin_falsos_positivos(texto):
    assert ordinal_terms(texto) == []


def test_unidades_distintas_no_se_confunden():
    assert ordinal_terms("5.º grado") == ["grado_5"]
    assert ordinal_terms("tercer cuatrimestre y 1er. Semestre") == ["cuatrimestre_3", "semestre_1"]
    assert ordinal_terms("primer año") == ["ano_1"]


def test_documento_lexico_sin_ruta_ni_ordinales_es_el_texto_original():
    assert lexical_document("Requisitos de ingreso: acta y CURP.", []) == "Requisitos de ingreso: acta y CURP."
    assert lexical_query("requisitos de ingreso") == "requisitos de ingreso"


def _ruta(*titulos):
    return [{"level": i + 1, "title": t} for i, t in enumerate(titulos)]


RUTA_EA5 = _ruta("Bachillerato — Plantel Torres Landa", "Plan de estudios",
                 "Área Económico-Administrativa y Humanidades", "5.º semestre")
RUTA_FM5 = _ruta("Bachillerato — Plantel Torres Landa", "Plan de estudios",
                 "Área Físico-Matemática y Químico-Biológicas", "5.º semestre")
RUTA_EA6 = _ruta("Bachillerato — Plantel Torres Landa", "Plan de estudios",
                 "Área Económico-Administrativa y Humanidades", "6.º semestre")


def test_documento_lexico_agrega_encabezados_superiores_y_ordinal():
    doc = lexical_document("#### 5.º semestre\n* Economía I", RUTA_EA5)
    assert doc.startswith("#### 5.º semestre\n* Economía I\n")
    assert "Área Económico-Administrativa y Humanidades" in doc and doc.endswith("semestre_5")
    assert doc.count("5.º semestre") == 1  # el título propio no se repite


def test_coincidencia_usa_superiores_y_ordinales_no_el_titulo_propio():
    q = "¿Qué materias se cursan en quinto semestre del área Económico-Administrativa en el plantel Torres Landa?"
    assert hierarchy_match(q, RUTA_EA5) == ["administrativa", "economico", "landa", "semestre_5", "torres"]
    assert hierarchy_match("requisitos de ingreso", _ruta("Plan", "Requisitos de ingreso")) == []
    assert hierarchy_match(q, []) == []


def test_ranking_jerarquico_distingue_area_y_semestre_e_ignora_terminos_comunes():
    q = "materias de quinto semestre del área Económico-Administrativa en Torres Landa"
    otros = [(f"x{i}", _ruta("Bachillerato — Plantel Hilario Medina", "Plan de estudios")) for i in range(4)]
    orden = hierarchy_rank(q, [("fm5", RUTA_FM5), ("ea6", RUTA_EA6), ("ea5", RUTA_EA5), *otros])
    ids = [i for i, _ in orden]
    assert ids[0] == "ea5" and set(ids[1:3]) == {"ea6", "fm5"}  # área y semestre correctos, primero
    # "bachillerato" está en la ruta de todos los candidatos: no distingue y no cuenta.
    assert all("bachillerato" not in t for _, t in orden)
    assert "bachillerato" in content_terms("Bachillerato")


def test_texto_para_el_reranker():
    assert contextualized_text("texto", []) == "texto"
    assert contextualized_text("* Economía I", RUTA_EA5).splitlines()[0].endswith("> 5.º semestre")


# ---------- ruta al fragmentar (por_encabezado), estructuras irregulares ----------

def _fragmentar(texto, estrategia="por_encabezado", **kw):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "application"))
    from fakes_documents import InMemorySourceRepository
    from fakes_ingestion import (
        FakeTextExtractor, InMemoryChunkRepository, InMemoryExtractionRepository,
        InMemoryFragmentationPolicyRepository,
    )
    from fakes_metadata import InMemoryMetadataSchemaRepository, InMemorySourceMetadataRepository

    from application.ingestion.service import IngestionService
    from domain.documents.entities import Source, SourceType

    fuentes = InMemorySourceRepository()
    src = Source(project_id="p", title="doc", source_type=SourceType.MARKDOWN, location="doc.md")
    fuentes.save(src)
    ing = IngestionService(fuentes, FakeTextExtractor(canned={"doc.md": (texto, "fake", [], [])}),
                           InMemoryExtractionRepository(), InMemoryFragmentationPolicyRepository(),
                           InMemoryChunkRepository(), InMemoryMetadataSchemaRepository(),
                           InMemorySourceMetadataRepository())
    ing.set_fragmentation_policy("p", "default", strategy=estrategia, **kw)
    ing.extract_source_text("p", src.id)
    return ing.fragment_source("p", src.id)


def _rutas(chunks):
    return [[(h.level, h.title) for h in c.section_path] for c in chunks if c.chunk_type.value != "padre"]


def test_ruta_con_niveles_omitidos_titulos_repetidos_y_preambulo():
    texto = ("Preámbulo sin encabezado.\n\n# Reglamento\nTexto.\n\n### Capítulo I\nTexto del capítulo.\n\n"
             "## Sección A\n### Disposiciones\nUno.\n\n## Sección B\n### Disposiciones\nDos.\n")
    rutas = _rutas(_fragmentar(texto, min_tokens=1, overlap_tokens=0))
    assert rutas == [
        [],
        [(1, "Reglamento")],
        [(1, "Reglamento"), (3, "Capítulo I")],
        [(1, "Reglamento"), (2, "Sección A")],
        [(1, "Reglamento"), (2, "Sección A"), (3, "Disposiciones")],
        [(1, "Reglamento"), (2, "Sección B")],
        [(1, "Reglamento"), (2, "Sección B"), (3, "Disposiciones")],
    ]


def test_hijos_subdivididos_y_su_padre_comparten_la_ruta():
    cuerpo = " ".join(f"palabra{i}" for i in range(60))
    chunks = _fragmentar(f"# Manual\n## Instalación\n{cuerpo}\n", target_tokens=15, overlap_tokens=0, min_tokens=1)
    hijos = [c for c in chunks if c.parent_chunk_id]
    padre = next(c for c in chunks if c.chunk_type.value == "padre")
    assert len(hijos) > 1
    assert all([h.title for h in c.section_path] == ["Manual", "Instalación"] for c in [*hijos, padre])


@pytest.mark.parametrize("estrategia", ["por_tamanio", "documento_completo"])
def test_otras_estrategias_no_guardan_ruta(estrategia):
    assert all(c.section_path == [] for c in _fragmentar("# Título\nTexto con varias palabras.\n", estrategia))



# ---------- Ronda 101: conflicto de ordinal explícito ----------

RUTA_FM6 = _ruta("Bachillerato — Plantel Torres Landa", "Plan de estudios",
                 "Área Físico-Matemática y Químico-Biológicas", "6.º semestre")


def test_conflicto_solo_con_ordinal_explicito_de_la_misma_unidad():
    q = "¿Qué materias se cursan en quinto semestre del área Físico-Matemática y Químico-Biológicas?"
    assert ordinal_conflicts(q, RUTA_FM6) == ["semestre_6"]
    assert ordinal_conflicts(q, RUTA_FM5) == []
    assert ordinal_conflicts("materias del área Físico-Matemática", RUTA_FM6) == []  # sin semestre pedido
    assert ordinal_conflicts("materias de quinto y sexto semestre", RUTA_FM6) == []  # ambos pedidos
    assert ordinal_conflicts(q, []) == []  # sin ruta (otras estrategias o documentos compartidos)
    assert ordinal_conflicts("5.º grado", RUTA_FM6) == []  # otra unidad
    assert ordinal_conflicts("artículo 5 del reglamento", RUTA_FM6) == []  # no es ordinal de periodo
