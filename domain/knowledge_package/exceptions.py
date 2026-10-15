"""Errores tipados de la exportación NEXOM Knowledge Package (RAG-INC-01b).

Toda compuerta previa lanza uno de estos errores ANTES de publicar nada en
`output_dir`: una exportación fallida nunca deja un paquete que parezca
válido."""
from __future__ import annotations


class KnowledgePackageExportError(Exception):
    """Base de los errores de exportación NKP."""


class MissingTenantError(KnowledgePackageExportError):
    def __init__(self) -> None:
        super().__init__(
            "Falta el tenant: es obligatorio para exportar un NEXOM Knowledge Package "
            "(no se infiere ni se usa un valor por defecto)."
        )


class SnapshotNotFoundError(KnowledgePackageExportError):
    def __init__(self, project_id: str, snapshot_id: str):
        super().__init__(
            f"No existe una instantánea publicada con id={snapshot_id!r} en el proyecto {project_id!r}."
        )
        self.project_id = project_id
        self.snapshot_id = snapshot_id


class SnapshotDirectoryMissingError(KnowledgePackageExportError):
    """La instantánea está registrada pero su carpeta (o su project.db) no
    existe físicamente (caso histórico de AGENTE UDL: v1 registrada, carpeta
    ausente)."""

    def __init__(self, snapshot_id: str, version: int, snapshot_dir: str, detalle: str = ""):
        super().__init__(
            f"La instantánea v{version} (id={snapshot_id!r}) está registrada, pero no existe físicamente "
            f"en {snapshot_dir!r}{(': ' + detalle) if detalle else ''}. Publique una instantánea nueva."
        )
        self.snapshot_id = snapshot_id
        self.snapshot_dir = snapshot_dir


class SnapshotInconsistentError(KnowledgePackageExportError):
    """El project.db de la instantánea no corresponde al registro, o su
    esquema es anterior a las identidades persistentes (migración 0021)."""


class MissingIdentityError(KnowledgePackageExportError):
    """`knowledge_base_id` o algún `lineage_id` ausente o inválido."""

    def __init__(self, detalle: str, entidades: list[str] | None = None):
        super().__init__(f"Identidad persistente ausente o inválida en la instantánea: {detalle}")
        self.entidades = list(entidades or [])


class MissingContentHashError(KnowledgePackageExportError):
    """Precondición INC01-R1: fuentes basadas en archivo sin huella."""

    def __init__(self, fuentes: list[tuple[str, str]]):
        listado = "; ".join(f"{titulo} ({sid})" for sid, titulo in fuentes[:20])
        mas = f" y {len(fuentes) - 20} más" if len(fuentes) > 20 else ""
        super().__init__(
            "La instantánea contiene fuentes sin huella de contenido. Complete las huellas "
            "(\"Completar huellas de contenido…\", pestaña Fuentes) y publique una instantánea nueva "
            f"antes de exportar. Fuentes: {listado}{mas}."
        )
        self.fuentes = list(fuentes)


class PortableIdentityCollisionError(KnowledgePackageExportError):
    """Dos entidades producirían el mismo id portable. No se resuelve
    automáticamente."""

    def __init__(self, tipo: str, colisiones: dict[str, list[str]]):
        detalle = "; ".join(f"{pid} <- {', '.join(origenes)}" for pid, origenes in list(colisiones.items())[:20])
        super().__init__(
            f"Colisión de identidad portable ({tipo}): varias entidades producen el mismo id. "
            f"No se exporta. {detalle}"
        )
        self.tipo = tipo
        self.colisiones = {k: list(v) for k, v in colisiones.items()}


class BrokenReferenceError(KnowledgePackageExportError):
    """Una referencia interna (supersesión, metadatos, catálogo, variable,
    canalización, chunk) no se puede resolver dentro de la instantánea."""


class ContractConstraintError(KnowledgePackageExportError):
    """Un dato de la instantánea no cumple una restricción del contrato v1.0.0
    (p. ej. chunk no imagen con texto vacío, instantánea sin índice)."""


class OutputExistsError(KnowledgePackageExportError):
    def __init__(self, ruta: str):
        super().__init__(f"Ya existe {ruta!r}: la exportación no sobrescribe archivos existentes.")
        self.ruta = ruta


class ContractConformanceError(KnowledgePackageExportError):
    """La compuerta de conformidad (RAG-INC-01c) rechazó el paquete generado:
    no se publica nada en output_dir."""

    def __init__(self, report):
        super().__init__(
            "El paquete generado no cumple el contrato NEXOM Knowledge Package y no se publicó.\n"
            + report.summary()
        )
        self.report = report
