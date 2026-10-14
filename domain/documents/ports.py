"""Puertos del contexto Documentos. Implementados en infrastructure.

Los métodos reciben project_id explícito (mismo criterio que
ConfigurationRepository en Etapa 1): cada project.db es independiente
y portable, así que el repositorio necesita saber cuál abrir sin
inferirlo de otro campo.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .entities import Source
from .import_batch import ImportBatchRecord


class SourceRepository(ABC):
    @abstractmethod
    def save(self, source: Source) -> None: ...

    @abstractmethod
    def get(self, project_id: str, source_id: str) -> Optional[Source]: ...

    @abstractmethod
    def get_by_content_hash(self, project_id: str, content_hash: str) -> Optional[Source]: ...

    @abstractmethod
    def list_for_project(self, project_id: str) -> list[Source]: ...


class SourceFileStore(ABC):
    """Copia el archivo original de una fuente al almacenamiento propio
    del proyecto (`sources/original/`, ver
    infrastructure.filesystem.paths), para que la extracción deje de
    depender de que la ruta externa original (`Source.location`) siga
    existiendo (ver README, "Limitaciones conocidas"). Capacidad
    opcional (igual criterio que embedding_provider_factory en
    RagService/ocr_engine en PdfTextExtractor): quien llama a
    RegisterSource/UpdateSourceDetails sin pasar esta dependencia
    conserva el comportamiento de siempre (se sigue leyendo de
    location directamente)."""

    @abstractmethod
    def store_original(self, project_id: str, source_id: str, external_path: str) -> str:
        """Copia `external_path` dentro del proyecto y devuelve la
        ruta absoluta final donde quedó guardada la copia. Si
        `external_path` no es un archivo legible en este momento (no
        existe, es un directorio, sin permisos), debe propagar la
        excepción tal cual -- decidir qué hacer ante un fallo de copia
        (omitir en silencio, seguir usando location) es responsabilidad
        de quien llama en application, no de este puerto."""
        ...


class ImportBatchLedger(ABC):
    """Registro append-only de los lotes de RAG CONTENT importados en un
    proyecto (Ronda 92, ver domain.documents.import_batch). Viaja con el
    proyecto (.agentproj) y con cada instantánea publicada."""

    @abstractmethod
    def list_batches(self, project_id: str) -> list[ImportBatchRecord]: ...

    @abstractmethod
    def append(self, project_id: str, record: ImportBatchRecord) -> None: ...
