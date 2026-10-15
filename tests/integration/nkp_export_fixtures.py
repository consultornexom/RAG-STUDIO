"""Construcción de proyectos sintéticos e instantáneas para las pruebas del
exportador NEXOM Knowledge Package (RAG-INC-01b). Solo datos de prueba."""
from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from domain.conversational.entities import RuleActionType, RuleCondition, RuleOperator, RuleType
from domain.documents.entities import AccessLevel, SourceType
from domain.ingestion.entities import Chunk, ChunkType
from domain.metadata.entities import FieldDataType
from domain.rag.entities import IndexInfo
from infrastructure.database.ingestion_repositories import SqlAlchemyChunkRepository
from infrastructure.database.rag_repositories import SqlAlchemyIndexInfoRepository

RAIZ = Path(__file__).resolve().parents[2]
CONTRATO = RAIZ / "contracts" / "nexom_knowledge_package" / "v1_0_0"  # vendorizado en 01c
VALIDADOR = CONTRATO / "validator" / "validate_knowledge_package.py"
MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@dataclass
class Proyecto:
    project_id: str
    fuentes: dict[str, str] = field(default_factory=dict)  # alias -> source_id
    chunks: dict[str, str] = field(default_factory=dict)  # alias -> chunk_id


def _archivo(tmp: Path, nombre: str, contenido: bytes) -> Path:
    ruta = tmp / "externos" / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    return ruta


def registrar(ctx, pid, tmp, alias, contenido: bytes | None, tipo=SourceType.PDF, ext=".pdf", **kw):
    location = str(_archivo(tmp, f"{alias}{ext}", contenido)) if contenido is not None else ""
    hash_ = hashlib.sha256(contenido).hexdigest() if contenido is not None else None
    return ctx.document_service.register_source(
        pid, f"Fuente {alias}", tipo, location=location, content_hash=hash_, **kw,
    )


def indice(ctx, pid, puntos: int) -> None:
    SqlAlchemyIndexInfoRepository(ctx.paths).save(IndexInfo(
        project_id=pid, embedding_provider="fastembed", embedding_model=MODELO, dimensions=384, points_count=puntos,
    ))


def proyecto_minimo(ctx, tmp: Path, nombre: str = "Minimo") -> Proyecto:
    pid = ctx.project_service.create_project(nombre).id
    f = registrar(ctx, pid, tmp, f"{nombre}-unica", b"contenido unico")
    c = Chunk(project_id=pid, source_id=f.id, chunk_index=0, text="Texto de la unica fuente.", token_count=5)
    SqlAlchemyChunkRepository(ctx.paths).save_many(pid, [c])
    indice(ctx, pid, 1)
    return Proyecto(pid, {"unica": f.id}, {"c0": c.id})


def proyecto_completo(ctx, tmp: Path, nombre: str = "Completo") -> Proyecto:
    pid = ctx.project_service.create_project(nombre).id
    meta, conv = ctx.metadata_service, ctx.conversational_service

    # Metadatos: catálogo jerárquico, campo único heredado, campo múltiple y texto.
    esquema = meta.create_schema(pid)
    campus = meta.create_catalog(pid, "campus")
    leon = meta.add_catalog_entry(pid, campus.id, "LEON", "León")
    meta.add_catalog_entry(pid, campus.id, "LEON_CENTRO", "León Centro", parent_entry_id=leon.id)
    meta.add_catalog_entry(pid, campus.id, "IRAPUATO", "Irapuato")
    programa = meta.create_catalog(pid, "programa")
    meta.add_catalog_entry(pid, programa.id, "DER", "Derecho")
    meta.add_catalog_entry(pid, programa.id, "ISC", "Ingeniería en Sistemas")
    meta.add_field_definition(pid, esquema.id, "campus", "Campus", FieldDataType.SELECCION_UNICA,
                              filterable=True, inherited_by_chunks=True, catalog_id=campus.id)
    meta.add_field_definition(pid, esquema.id, "programas", "Programas", FieldDataType.SELECCION_MULTIPLE,
                              multiple=True, catalog_id=programa.id)
    meta.add_field_definition(pid, esquema.id, "nota", "Nota", FieldDataType.TEXTO)

    # Fuentes: cadena de versiones, fuente confidencial, API sin archivo, imagen.
    r1 = registrar(ctx, pid, tmp, f"{nombre}-reglamento-2025", b"reglamento 2025")
    r2 = registrar(ctx, pid, tmp, f"{nombre}-reglamento-2026", b"reglamento 2026", supersedes_source_id=r1.id)
    conf = registrar(ctx, pid, tmp, f"{nombre}-notas", b"notas internas", tipo=SourceType.DOCX, ext=".docx",
                     access_level=AccessLevel.CONFIDENCIAL)
    api = registrar(ctx, pid, tmp, f"{nombre}-api", None, tipo=SourceType.API)
    img = registrar(ctx, pid, tmp, f"{nombre}-diagrama", b"\x89PNG imagen", tipo=SourceType.IMAGEN_NATIVA, ext=".png")
    meta.set_source_metadata_value(pid, esquema.id, r2.id, "campus", "LEON")
    meta.set_source_metadata_value(pid, esquema.id, r2.id, "programas", ["DER", "ISC"])
    meta.set_source_metadata_value(pid, esquema.id, r2.id, "nota", "vigente")

    # Chunks: encabezado + texto con padre, tabla estructurada, padre, imagen.
    padre = Chunk(project_id=pid, source_id=r2.id, chunk_index=0, text="Sección completa de requisitos.",
                  token_count=4, chunk_type=ChunkType.PADRE)
    enc = Chunk(project_id=pid, source_id=r2.id, chunk_index=1, text="Capítulo 3. Requisitos", token_count=3,
                chunk_type=ChunkType.ENCABEZADO, section_title="Capítulo 3", page_start=5, page_end=5)
    txt = Chunk(project_id=pid, source_id=r2.id, chunk_index=2, text="Entregar acta de nacimiento.", token_count=4,
                section_title="Capítulo 3", page_start=5, page_end=6, inherited_metadata={"campus": "LEON"})
    enc.next_chunk_id = txt.id
    txt.previous_chunk_id = enc.id
    txt.parent_chunk_id = padre.id
    tabla = Chunk(project_id=pid, source_id=r1.id, chunk_index=0, text="Tabla de programas.", token_count=3,
                  chunk_type=ChunkType.TABLA, structured_content={"columns": ["programa"], "rows": [["DER"]]})
    nota = Chunk(project_id=pid, source_id=conf.id, chunk_index=0, text="Acuerdo interno del comité.", token_count=4)
    api_c = Chunk(project_id=pid, source_id=api.id, chunk_index=0, text="Respuesta de la API.", token_count=4)
    imagen = Chunk(project_id=pid, source_id=img.id, chunk_index=0, text="", token_count=0,
                   chunk_type=ChunkType.IMAGEN, image_relative_path=Path(img.original_copy_path).name)
    SqlAlchemyChunkRepository(ctx.paths).save_many(pid, [padre, enc, txt, tabla, nota, api_c, imagen])
    indice(ctx, pid, 5)

    # Conversacional.
    conv.create_variable(pid, "folio_aspirante", "Folio de aspirante")
    conv.create_channeling_scheme(pid, "admisiones_humano", "Admisiones", summary_template="Atención humana.")
    conv.create_intent(pid, "requisitos_admision", description="Requisitos de ingreso",
                       positive_examples=["qué necesito"], required_variables=["folio_aspirante"],
                       clarifying_questions={"folio_aspirante": "¿Cuál es tu folio?"},
                       fallback_channeling_code="admisiones_humano")
    conv.create_guardrail_rule(pid, "baja_confianza", RuleType.SEGURIDAD,
                               conditions=[RuleCondition(field="confianza", operator=RuleOperator.MENOR, value="0.5")],
                               action=RuleActionType.ABSTENERSE, priority=3)
    return Proyecto(pid, {"r1": r1.id, "r2": r2.id, "conf": conf.id, "api": api.id, "img": img.id},
                    {"padre": padre.id, "enc": enc.id, "txt": txt.id, "tabla": tabla.id, "nota": nota.id,
                     "api": api_c.id, "imagen": imagen.id})


def sql(ctx, pid: str, consulta: str, *args) -> None:
    """Modifica el project.db VIVO (solo para preparar casos de prueba antes de publicar)."""
    con = sqlite3.connect(ctx.paths.project_db_path(pid))
    try:
        con.execute(consulta, args)
        con.commit()
    finally:
        con.close()


def validar(ruta: Path) -> tuple[int, str]:
    """Validador firmado v1.0.0 como prueba externa (no se modifica)."""
    r = subprocess.run([sys.executable, str(VALIDADOR), str(ruta)], capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


def validador_disponible() -> bool:
    try:
        import jsonschema  # noqa: F401
        import rfc3339_validator  # noqa: F401
        import rfc8785  # noqa: F401
    except ImportError:
        return False
    return VALIDADOR.is_file()
