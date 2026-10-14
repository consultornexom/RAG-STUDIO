"""Entidades del contexto Ingesta (ADR-001, sección 5 ampliada en la
Etapa 3; RAG STUDIO INVESTIGACION.odt, actividades A2/A3).

Tres conceptos:

- ExtractionRecord: resultado de extraer texto plano de una Source
  (Módulo 4 mínimo: sin OCR, sin revisión manual todavía).
- FragmentationPolicy: parámetros de fragmentación configurables por
  "document_type_code" (un código libre, no un enum fijo: el tipo
  documental real —reglamento, manual, FAQ...— vive como metadato
  configurable en el metamodelo de la Etapa 2, no como columna rígida
  aquí; ver RAG STUDIO.odt, sección 21).
- Chunk: un fragmento resultante, con los campos de trazabilidad que
  INVESTIGACION.odt exige (documento/sección/página) y una copia de
  los metadatos de la fuente marcados inherited_by_chunks=True.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChunkType(str, Enum):
    """Valores tomados literalmente de la tabla de metadatos de
    fragmento de INVESTIGACION.odt. REQUISITO y EXCEPCION quedan
    reservados para enriquecimiento manual o automático futuro; los
    divisores de esta iteración solo producen TEXTO.

    ENCABEZADO y PADRE: agregados en la Pista B.1 del ADR-003 (ver
    `docs proyecto/RAG_STUDIO_Diseno_B1_Modelo_Canonico_Chunk.docx`,
    sección 3.1) -- decisión explícita de reutilizar este Enum en vez
    de agregar un campo `element_type` paralelo, confirmada por el
    consultor. ENCABEZADO distingue el título de una sección del
    cuerpo de texto que hoy comparte TEXTO; PADRE marca el fragmento
    de contexto más amplio que agrupa a varios chunks hijo
    (`parent_chunk_id`, ver más abajo) -- un chunk PADRE nunca se
    indexa para búsqueda (ver `application/rag`), solo se recupera
    por id al expandir el contexto de un resultado."""

    TEXTO = "texto"
    TABLA = "tabla"
    PREGUNTA_RESPUESTA = "pregunta_respuesta"
    REQUISITO = "requisito"
    EXCEPCION = "excepcion"
    ENCABEZADO = "encabezado"
    PADRE = "padre"
    ESTRUCTURADO = "estructurado"
    """Pista B.2 del ADR-003 (ver `docs proyecto/
    RAG_STUDIO_Diseno_B2_Datos_Estructurados.docx`, sección 3.2): marca
    un chunk cuyo `structured_content` viene de un bloque estructurado
    real de la extracción (una hoja XLSX o un CSV completos, con
    columnas y filas nativas), no de una tabla Markdown detectada a
    posteriori como TABLA. A diferencia de PADRE, un chunk ESTRUCTURADO
    SÍ se indexa para búsqueda -- su `text` sigue siendo contenido
    narrativo legítimo (la misma tabla Markdown de siempre), no un
    duplicado a evitar."""

    IMAGEN = "imagen"
    """Fase 2 de multimodalidad nativa (RAG 3, ver docs proyecto/
    RAG_STUDIO_Diseno_Ejecutable_RAG3_Multimodalidad.docx, sección 3.1)
    -- mismo criterio de reutilizar este Enum ya aplicado a ENCABEZADO/
    PADRE/ESTRUCTURADO, en vez de agregar un campo `element_type`
    paralelo. Marca un chunk cuyo contenido real es un archivo de imagen
    (`image_relative_path`, ver más abajo), no texto narrativo -- por
    eso es el único ChunkType que puede tener `text` vacío (ver
    `Chunk._text_required_unless_image`). No se indexa en la colección
    de texto (`chunks`); la Fase 3 lo indexa en una colección aparte
    (`chunks_imagenes`) vía `ImageEmbeddingProvider`."""


class FragmentationStrategy(str, Enum):
    """Etapa 3 (tres estrategias genéricas) + Módulo 5 (tres
    estrategias por tipo documental, tabla "Reglas recomendadas por
    tipo documental" de INVESTIGACION.odt: reglamento, preguntas
    frecuentes y tabla; el resto de filas de esa tabla -- convocatoria,
    procedimiento, ficha de programa, formato, página web -- se cubren
    razonablemente bien con POR_ENCABEZADO/POR_TAMANIO existentes y
    quedan como trabajo futuro solo si un caso real lo justifica, ver
    README)."""

    POR_TAMANIO = "por_tamanio"
    """Ventana deslizante por conteo de palabras, con solapamiento.
    Estrategia genérica y de respaldo para cualquier tipo de texto."""

    POR_ENCABEZADO = "por_encabezado"
    """Divide por líneas de encabezado estilo Markdown ('#', '##', ...).
    Los extractores normalizan encabezados detectados (p.ej. estilos
    'Heading' de DOCX) a este formato para que la estrategia funcione
    igual sin importar el formato de origen."""

    DOCUMENTO_COMPLETO = "documento_completo"
    """Todo el texto extraído se convierte en un único fragmento.
    Apropiado para avisos, comunicados y documentos cortos que no
    deben partirse (INVESTIGACION.odt, A2)."""

    POR_ARTICULO = "por_articulo"
    """Reglamentos: un fragmento por artículo o inciso completo,
    detectado por líneas que empiezan con "Artículo N" / "Art. N",
    sin sub-dividir aunque exceda el tamaño estándar -- el supuesto y
    su consecuencia nunca deben quedar en fragmentos distintos
    (INVESTIGACION.odt, A2: "Reglamentos: artículo completo, incluso
    si excede el tamaño estándar")."""

    PREGUNTA_RESPUESTA = "pregunta_respuesta"
    """Preguntas frecuentes: un fragmento por pregunta completa
    (pregunta + respuesta), detectado por líneas que empiezan con
    "P:"/"Pregunta:"/"Q:", sin solapamiento (INVESTIGACION.odt, A2:
    "Preguntas frecuentes: sin solapamiento"). Los fragmentos
    resultantes se marcan como ChunkType.PREGUNTA_RESPUESTA."""

    POR_TABLA = "por_tabla"
    """Detecta tablas en formato Markdown (fila de encabezado + fila
    separadora + filas de datos) y arma fragmentos que siempre repiten
    encabezado y separador (INVESTIGACION.odt, A2: "Tabla completa o
    grupo lógico de filas... Repetir encabezados en cada fragmento").
    El texto que no es tabla se fragmenta como POR_TAMANIO. Los
    fragmentos de tabla se marcan como ChunkType.TABLA."""

    POR_HOJA_ESTRUCTURADA = "por_hoja_estructurada"
    """Pista B.2 del ADR-003 (ver `docs proyecto/
    RAG_STUDIO_Diseno_B2_Datos_Estructurados.docx`, sección 3.2): un
    chunk por cada bloque estructurado que ya identificó la extracción
    (`ExtractionRecord.structured_blocks` -- hoy, una hoja XLSX o el
    CSV completo), marcado ChunkType.ESTRUCTURADO. No sub-divide un
    bloque grande en varios chunks (limitación conocida, documentada
    en el diseño) -- a diferencia de POR_TABLA, aquí la fuente de
    verdad de qué chunks existen es `structured_blocks`, no un patrón
    detectado en el texto: los encabezados Markdown de la extracción
    solo se usan, mejor esfuerzo, para ubicar la página de cada bloque.
    Sin bloques estructurados (fuente no XLSX/CSV, o extractor sin
    esta capacidad), se degrada a DOCUMENTO_COMPLETO."""


class FragmentationPolicy(BaseModel):
    """Un proyecto puede definir una política por document_type_code
    (p.ej. "reglamento", "manual", "faq") y una política "default"
    de respaldo. Si no hay ninguna, application usa una política
    interna con los parámetros iniciales sugeridos por A2."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    document_type_code: str
    strategy: FragmentationStrategy = FragmentationStrategy.POR_TAMANIO
    target_tokens: int = 500
    overlap_tokens: int = 60
    min_tokens: int = 80
    created_at: datetime = Field(default_factory=_utcnow)

    @field_validator("document_type_code")
    @classmethod
    def _code_no_vacio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("document_type_code no puede estar vacío")
        return v

    @model_validator(mode="after")
    def _parametros_coherentes(self) -> "FragmentationPolicy":
        if self.target_tokens <= 0:
            raise ValueError("target_tokens debe ser mayor que cero")
        if self.overlap_tokens < 0 or self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens debe ser >= 0 y menor que target_tokens")
        if self.min_tokens < 0 or self.min_tokens >= self.target_tokens:
            raise ValueError("min_tokens debe ser >= 0 y menor que target_tokens")
        return self


class ExtractionRecord(BaseModel):
    """Resultado de extraer texto de una Source. Se guarda uno por
    Source (upsert): volver a extraer sustituye el registro anterior,
    igual que la fuente puede volver a validarse.

    Corrección de docstring (Pista C.2c del ADR-003, docs proyecto/
    RAG_STUDIO_Propuesta_C2_Procedencia_Temporalidad.docx): esta clase
    decía "no se conserva historial de extracciones en esta
    iteración" -- eso describía un estado anterior a que se agregara
    `ExtractionRepository.list_history` (con su propia tabla de solo
    inserción, `extraction_record_history`, distinta de este registro
    vigente). El historial real SÍ existe desde entonces; solo el
    comentario había quedado desactualizado."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    source_id: str
    text: str
    page_breaks: list[int] = Field(default_factory=list)
    """Desplazamientos de carácter donde inicia cada página nueva
    (solo se rellena para PDF; vacío para TXT/Markdown/DOCX, que no
    tienen páginas fijas)."""
    extraction_method: str = ""
    warnings: list[str] = Field(default_factory=list)
    structured_blocks: dict[str, dict] = Field(default_factory=dict)
    """Pista B.2 del ADR-003: bloques de contenido estructurado que el
    extractor identificó ADEMÁS del texto (p. ej. una hoja XLSX
    completa, con columnas y filas nativas) -- clave = título del
    bloque (nombre de hoja; "datos" para CSV, que no tiene varias
    tablas nombradas), valor = {"columnas": [...], "filas": [...]}.
    Diccionario vacío para cualquier fuente que no sea XLSX/CSV, o
    para una fuente XLSX/CSV extraída antes de esta capacidad (sin
    backfill automático, mismo criterio que otros campos aditivos de
    este proyecto)."""
    extracted_at: datetime = Field(default_factory=_utcnow)

    @property
    def char_count(self) -> int:
        return len(self.text)


class Chunk(BaseModel):
    """Fragmento resultante de aplicar una FragmentationPolicy al
    texto extraído de una Source."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    source_id: str
    chunk_index: int
    text: str
    token_count: int
    section_title: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    chunk_type: ChunkType = ChunkType.TEXTO
    previous_chunk_id: Optional[str] = None
    next_chunk_id: Optional[str] = None
    parent_chunk_id: Optional[str] = None
    """Pista B.1 del ADR-003: id de un chunk chunk_type=PADRE que
    agrupa a este fragmento junto con sus hermanos (p. ej. la sección
    completa de la que este chunk es un extracto). None significa "sin
    padre" -- el mismo estado, implícito, que tenía todo chunk antes de
    esta ronda; ninguna estrategia de fragmentación estaba obligada a
    poblarlo. Solo POR_ENCABEZADO lo produce por ahora (ver
    `application/ingestion/commands/fragment_source.py`)."""
    structured_content: Optional[dict] = None
    """Pista B.1 del ADR-003: contenido estructurado del fragmento
    (p. ej. filas/columnas de una tabla) sin aplanar a texto Markdown.
    Ningún extractor ni divisor lo puebla todavía -- se agrega ahora,
    vacío, para que la Pista B.2 (datos estructurados como
    representación propia) no necesite otra migración de esquema."""
    image_relative_path: Optional[str] = None
    """Fase 2 de multimodalidad nativa (RAG 3): ruta relativa (dentro de
    sources/original/, ver domain.documents.ports.SourceFileStore) al
    archivo de imagen que este chunk representa -- solo se puebla para
    chunk_type=IMAGEN. None para cualquier otro tipo de chunk, mismo
    criterio aditivo/opcional que structured_content."""
    semantic_summary: Optional[str] = None
    inherited_metadata: dict[str, str] = Field(default_factory=dict)
    pipeline_version: str = "1.0"
    created_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _text_required_unless_image(self) -> "Chunk":
        """Todo chunk necesita texto no vacío -- salvo ChunkType.IMAGEN
        (Fase 2 de multimodalidad nativa, RAG 3): ahí el contenido real
        es el archivo de `image_relative_path`, no texto narrativo, así
        que exigir texto obligaría a un placeholder falso solo para
        satisfacer este validador. Antes de esta ronda era un
        `field_validator("text")` de un solo campo; se convirtió en un
        validador de modelo completo porque ahora depende también de
        `chunk_type`."""
        if self.chunk_type != ChunkType.IMAGEN and not self.text.strip():
            raise ValueError("Un fragmento no puede tener texto vacío")
        return self

    @field_validator("chunk_index", "token_count")
    @classmethod
    def _no_negativo(cls, v: int) -> int:
        if v < 0:
            raise ValueError("chunk_index y token_count no pueden ser negativos")
        return v
