"""Caso de uso: extraer el texto plano de una Source (Módulo 4 mínimo).

No hace OCR ni revisión manual todavía; simplemente delega en el
TextExtractor disponible para el source_type y guarda el resultado
(upsert: una extracción por fuente en esta iteración, sin historial).
"""
from __future__ import annotations

from typing import Callable, Optional

from domain.documents.entities import SourceType
from domain.documents.exceptions import SourceNotFoundError
from domain.documents.ports import SourceRepository
from domain.ingestion.entities import ExtractionRecord
from domain.ingestion.exceptions import EmptyExtractionError, SourceLocationUnreadableError
from domain.ingestion.normalization import normalize_text
from domain.ingestion.ports import ExtractionRepository, TextExtractor


class ExtractSourceText:
    def __init__(
        self,
        source_repository: SourceRepository,
        extractor: TextExtractor,
        extraction_repository: ExtractionRepository,
    ):
        self._source_repository = source_repository
        self._extractor = extractor
        self._extraction_repository = extraction_repository

    def execute(
        self, project_id: str, source_id: str,
        is_cancelled: Callable[[], bool] = lambda: False,
    ) -> Optional[ExtractionRecord]:
        """Extrae y guarda el texto de una fuente.

        `is_cancelled` es cancelación cooperativa (ver
        workers.jobs.JobHandle.is_cancelled): se revisa antes de llamar
        al extractor y otra vez después, antes de guardar. La llamada
        al extractor en sí (pypdf/python-docx) sigue siendo una sola
        operación atómica -- no expone puntos de control intermedios
        para interrumpirla a la mitad de un documento -- así que esto
        es "lo mejor posible" (best effort), no interrupción real
        dentro del parseo. Aun así aporta algo real: si se cancela
        antes de empezar, o mientras la extracción ya terminó pero
        antes de persistir, no se guarda nada -- antes de este cambio
        se guardaba siempre, sin importar la cancelación.

        Devuelve `None` (en vez de lanzar) cuando el trabajo se
        cancela, para que quien llama en segundo plano (ver
        ui/ingestion/panel.py) no lo trate como un error; los
        llamadores directos (scripts, pruebas) nunca pasan un
        `is_cancelled` real, así que para ellos esto nunca cambia de
        comportamiento.
        """
        if is_cancelled():
            return None

        source = self._source_repository.get(project_id, source_id)
        if source is None:
            raise SourceNotFoundError(source_id)

        # Preferir la copia local en sources/original/ (si existe,
        # ver domain.documents.ports.SourceFileStore/RegisterSource)
        # sobre la ruta externa original: así la extracción -- incluso
        # una re-extracción posterior -- no depende de que el archivo
        # externo original siga existiendo en el mismo lugar (ver
        # README, "Limitaciones conocidas"). Sin copia (proyecto
        # antiguo, tipo de fuente sin archivo real, o la copia falló al
        # registrar), se sigue leyendo de location directamente, igual
        # que siempre.
        read_path = source.original_copy_path or source.location
        try:
            text, method, page_breaks, warnings = self._extractor.extract(read_path, source.source_type)
        except OSError as exc:
            # read_path apunta a algo no legible como archivo (no
            # existe, es un directorio, sin permisos...) -- se envuelve
            # en un error de dominio claro en vez de dejar pasar el
            # OSError crudo del sistema de archivos tal cual hasta la
            # UI (hallazgo real de validación visual: una fuente
            # registrada con la carpeta contenedora en "Ubicación" en
            # vez de la ruta completa del archivo).
            raise SourceLocationUnreadableError(source_id, read_path, str(exc)) from exc

        # Pista B.2 del ADR-003: bloques estructurados (hoy, hojas XLSX
        # o el CSV completo) ADEMÁS del texto ya extraído arriba -- ver
        # `domain.ingestion.ports.TextExtractor.extract_structured_blocks`.
        # Diccionario vacío para cualquier fuente que no sea XLSX/CSV
        # (comportamiento por defecto del puerto, sin cambio alguno).
        structured_blocks = self._extractor.extract_structured_blocks(read_path, source.source_type)

        # Normalización (RAG STUDIO.odt: paso propio antes de fragmentar
        # -- ver domain.ingestion.normalization). Solo se aplica cuando
        # la extracción NO produjo saltos de página (TXT/DOCX/XLSX/CSV/
        # imagen): normalizar cambiaría la longitud del texto y
        # invalidaría los desplazamientos de `page_breaks` ya calculados
        # por PdfTextExtractor (trazabilidad de página, A2) -- PDF ya
        # aplica su propia normalización específica (reparación de
        # letra-espaciado) antes de fijar esos desplazamientos.
        if not page_breaks:
            text = normalize_text(text)

        # SourceType.IMAGEN_NATIVA (Fase 2 de multimodalidad, RAG 3) es
        # la única excepción deliberada: ImageNativeExtractor siempre
        # devuelve texto vacío porque no hay nada que transcribir -- el
        # contenido real es el archivo de imagen, no texto. Para
        # cualquier otro tipo de fuente, texto vacío sigue siendo un
        # fallo real de extracción (documento en blanco, PDF escaneado
        # sin OCR, etc.).
        if not text.strip() and source.source_type != SourceType.IMAGEN_NATIVA:
            raise EmptyExtractionError(source_id)

        if is_cancelled():
            return None

        record = ExtractionRecord(
            project_id=project_id, source_id=source_id, text=text,
            page_breaks=page_breaks, extraction_method=method, warnings=warnings,
            structured_blocks=structured_blocks,
        )
        self._extraction_repository.save(record)
        return record
