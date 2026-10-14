"""Pista C.2b del ADR-003 (docs proyecto/
RAG_STUDIO_Propuesta_C2_Procedencia_Temporalidad.docx): linaje completo
de versiones de una fuente, caminando `Source.supersedes_source_id` en
ambos sentidos -- hacia atrás (a qué fuente sustituye) y hacia
adelante (qué fuente la sustituyó a ella, si alguna). Antes de esta
pista, `ui/sources/panel.py` solo mostraba un salto hacia atrás; este
módulo reconstruye la cadena completa."""
from __future__ import annotations

from domain.documents.entities import Source
from domain.documents.exceptions import SourceNotFoundError
from domain.documents.ports import SourceRepository


class GetSourceLineage:
    def __init__(self, repository: SourceRepository):
        self._repository = repository

    def execute(self, project_id: str, source_id: str) -> list[Source]:
        """Devuelve la cadena completa de versiones, de la más antigua
        a la más nueva -- incluye la fuente pedida. Con
        `SourceRepository.list_for_project` (ya existente, sin método
        nuevo en el repositorio, ver sección 6 del documento de
        diseño): aceptable para el tamaño típico de un proyecto de
        RAG STUDIO; si el volumen de fuentes lo justificara, se puede
        agregar una consulta indexada más adelante sin cambiar la
        forma de este resultado."""
        target = self._repository.get(project_id, source_id)
        if target is None:
            raise SourceNotFoundError(source_id)

        all_sources = self._repository.list_for_project(project_id)
        by_id = {source.id: source for source in all_sources}
        seen = {target.id}

        # Hacia atrás: a qué fuente sustituye esta, y a qué sustituye
        # esa a su vez -- protegido contra un ciclo (no debería
        # ocurrir nunca en datos reales, pero un ciclo silencioso
        # produciría un bucle infinito sin esta comprobación).
        backward: list[Source] = []
        current = target
        while current.supersedes_source_id is not None and current.supersedes_source_id in by_id:
            previous = by_id[current.supersedes_source_id]
            if previous.id in seen:
                break
            backward.append(previous)
            seen.add(previous.id)
            current = previous
        backward.reverse()

        # Hacia adelante: qué fuente sustituyó a esta, y a esa otra,
        # etc.
        forward: list[Source] = []
        current = target
        while True:
            successor = next(
                (s for s in all_sources if s.supersedes_source_id == current.id and s.id not in seen),
                None,
            )
            if successor is None:
                break
            forward.append(successor)
            seen.add(successor.id)
            current = successor

        return [*backward, target, *forward]
