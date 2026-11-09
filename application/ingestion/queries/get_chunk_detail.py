"""Consulta: detalle completo de un fragmento guardado (Ronda 99, hallazgo
real de NEXOM, AGENTE UDL - LOTE01_Bachillerato).

La pestaña Fragmentación solo mostraba número, tokens, sección, páginas y
tipo de cada fragmento; no había forma de leer su texto ni sus metadatos
sin scripts externos. Esta consulta reúne, SOLO LEYENDO los repositorios
ya existentes (sin escribir, sin re-fragmentar ni re-indexar):

1. el fragmento tal como está guardado (texto íntegro y propiedades);
2. sus metadatos estructurados heredados (`inherited_metadata`), con los
   valores múltiples separados para leerlos y su forma original;
3. un contexto jerárquico DERIVADO para diagnóstico: la ruta completa de
   encabezados Markdown que rige al fragmento en el texto extraído, y
   cuáles de esos encabezados NO aparecen en el texto que se indexa. Este
   contexto no se guarda ni se usa en la búsqueda; sirve para comprobar si
   el fragmento tiene lo necesario para responder.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from domain.documents.ports import SourceRepository
from domain.ingestion.entities import Chunk, ChunkType
from domain.ingestion.heading_context import heading_outline, heading_path_at, missing_from_text
from domain.ingestion.ports import ChunkRepository, ExtractionRepository
from domain.metadata.entities import split_stored_values
from domain.metadata.ports import MetadataSchemaRepository


class ChunkReference(BaseModel):
    id: str
    chunk_index: Optional[int] = None
    section_title: Optional[str] = None
    found: bool = True
    """False si el id guardado ya no corresponde a ningún fragmento de la fuente."""


class InheritedMetadataEntry(BaseModel):
    field_id: str
    display_name: Optional[str] = None
    raw_value: str
    values: list[str] = Field(default_factory=list)
    multiple: bool = False


class ChunkDetail(BaseModel):
    chunk: Chunk
    source_id: str
    source_title: str
    source_position: Optional[int] = None
    """Posición (1..n) de la fuente entre las fuentes del proyecto."""
    source_count: int = 0
    source_document_type_code: Optional[str] = None
    inherited_metadata: list[InheritedMetadataEntry] = Field(default_factory=list)
    parent: Optional[ChunkReference] = None
    previous: Optional[ChunkReference] = None
    next: Optional[ChunkReference] = None
    indexable: bool = True
    indexable_reason: str = ""
    heading_path: list[str] = Field(default_factory=list)
    heading_path_levels: list[int] = Field(default_factory=list)
    heading_context_status: str = "no_aplica"
    """"derivado" | "sin_encabezados" | "sin_extraccion" | "no_localizado" | "no_aplica"."""
    heading_context_missing: list[str] = Field(default_factory=list)
    """Títulos de la ruta que no aparecen en el texto indexado del fragmento."""


def _indexable(chunk: Chunk) -> tuple[bool, str]:
    # Misma regla que application.rag.commands.index_source (no se duplica:
    # se importa la función que decide de verdad qué se indexa).
    from application.rag.commands.index_source import _has_meaningful_content

    if chunk.chunk_type == ChunkType.PADRE:
        return False, "Fragmento PADRE: se guarda para ampliar contexto, pero nunca se indexa."
    if not _has_meaningful_content(chunk):
        return False, "Solo contiene su encabezado: no se indexa (su título ya está en la sección de sus hijos)."
    return True, "Se indexa con su texto tal como está guardado."


class GetChunkDetail:
    def __init__(
        self,
        source_repository: SourceRepository,
        chunk_repository: ChunkRepository,
        extraction_repository: ExtractionRepository,
        schema_repository: MetadataSchemaRepository,
    ):
        self._sources = source_repository
        self._chunks = chunk_repository
        self._extractions = extraction_repository
        self._schemas = schema_repository

    def execute(self, project_id: str, source_id: str, chunk_id: str) -> Optional[ChunkDetail]:
        chunks = sorted(self._chunks.list_for_source(project_id, source_id), key=lambda c: c.chunk_index)
        by_id = {c.id: c for c in chunks}
        chunk = by_id.get(chunk_id)
        if chunk is None:
            return None
        source = self._sources.get(project_id, source_id)
        fuentes = self._sources.list_for_project(project_id)
        posicion = next((i for i, s in enumerate(fuentes, start=1) if s.id == source_id), None)

        def ref(target: Optional[str]) -> Optional[ChunkReference]:
            if not target:
                return None
            destino = by_id.get(target)
            if destino is None:
                return ChunkReference(id=target, found=False)
            return ChunkReference(id=target, chunk_index=destino.chunk_index, section_title=destino.section_title)

        indexable, motivo = _indexable(chunk)
        detail = ChunkDetail(
            chunk=chunk.model_copy(deep=True), source_id=source_id,
            source_title=source.title if source else source_id, source_position=posicion,
            source_count=len(fuentes), source_document_type_code=source.document_type_code if source else None,
            inherited_metadata=self._metadata(project_id, chunk),
            parent=ref(chunk.parent_chunk_id), previous=ref(chunk.previous_chunk_id), next=ref(chunk.next_chunk_id),
            indexable=indexable, indexable_reason=motivo,
        )
        self._heading_context(project_id, source_id, chunk, chunks, detail)
        return detail

    def _metadata(self, project_id: str, chunk: Chunk) -> list[InheritedMetadataEntry]:
        campos = {}
        schema = self._schemas.get_active_schema(project_id)
        if schema is not None:
            campos = {f.field_id: f for f in self._schemas.list_fields(project_id, schema.id)}
        entradas = []
        for field_id, valor in sorted((chunk.inherited_metadata or {}).items()):
            campo = campos.get(field_id)
            multiple = bool(campo and campo.multiple)
            valores = split_stored_values(valor) if multiple else [valor]
            entradas.append(InheritedMetadataEntry(
                field_id=field_id, display_name=campo.display_name if campo else None,
                raw_value=valor, values=valores, multiple=multiple,
            ))
        return entradas

    def _heading_context(
        self, project_id: str, source_id: str, chunk: Chunk, chunks: list[Chunk], detail: ChunkDetail,
    ) -> None:
        if not chunk.section_title:
            detail.heading_context_status = "no_aplica"
            return
        record = self._extractions.get(project_id, source_id)
        if record is None:
            detail.heading_context_status = "sin_extraccion"
            return
        outline = heading_outline(record.text)
        if not outline:
            detail.heading_context_status = "sin_encabezados"
            return
        # Se ubica cada fragmento en orden, a partir del anterior: dos
        # fragmentos con el mismo texto (p. ej. "5.º semestre" en dos áreas)
        # quedan cada uno en su lugar, no ambos en la primera aparición.
        posicion: Optional[int] = None
        desde = 0
        for actual in chunks:
            if actual.chunk_type == ChunkType.PADRE:
                continue
            texto = actual.text.strip()
            encontrado = record.text.find(texto, desde) if texto else -1
            if encontrado >= 0:
                desde = encontrado + 1
            if actual.id == chunk.id:
                posicion = encontrado if encontrado >= 0 else None
                break
        if chunk.chunk_type == ChunkType.PADRE:
            encontrado = record.text.find(chunk.text.strip())
            posicion = encontrado if encontrado >= 0 else None
        if posicion is None:
            detail.heading_context_status = "no_localizado"
            return
        ruta = heading_path_at(outline, posicion)
        detail.heading_path = [e.title for e in ruta]
        detail.heading_path_levels = [e.level for e in ruta]
        detail.heading_context_missing = missing_from_text(ruta, chunk.text)
        detail.heading_context_status = "derivado"
