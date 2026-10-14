"""Excepciones del contexto Proyectos. Puras, sin dependencias externas."""


class ProjectDomainError(Exception):
    """Base de todos los errores del dominio de proyectos."""


class ProjectNotFoundError(ProjectDomainError):
    def __init__(self, project_id: str):
        super().__init__(f"No existe un proyecto con id={project_id!r}")
        self.project_id = project_id


class DuplicateProjectError(ProjectDomainError):
    def __init__(self, name: str):
        # Ronda 88: mensaje en lenguaje de usuario y sin los espacios
        # sobrantes que el nombre pueda traer (Project.name los recorta).
        super().__init__(
            f"Ya existe un proyecto llamado {name.strip()!r} en esta instalación. Elija otro nombre."
        )
        self.name = name


class InvalidStatusTransitionError(ProjectDomainError):
    def __init__(self, current: str, target: str):
        super().__init__(f"Transición de estado no permitida: {current} -> {target}")
        self.current = current
        self.target = target


class IntegrityViolationError(ProjectDomainError):
    """Se lanza cuando un .agentproj no verifica su hash o manifiesto."""


class ProjectIdCollisionError(ProjectDomainError):
    """Auditoría Ronda 48 (pruebas reales con documentos de Licenciatura/):
    import_project() nunca comprobaba si el project_id de destino ya
    tenía datos reales en disco -- un paquete cuyo manifiesto declarara
    (a propósito o por accidente) el id de un proyecto ya existente
    mezclaba silenciosamente sus archivos con los del proyecto
    existente, sin ninguna advertencia. Se lanza en vez de escribir
    nada cuando ese id ya pertenece a un proyecto registrado.

    Ronda 88 (2026-10-02): el mensaje anterior pedía "indicar un id nuevo
    (new_project_id)", algo que la interfaz no permitía hacer. Ahora la
    interfaz ofrece importar como copia (id nuevo generado
    automáticamente) y el mensaje lo explica en esos términos."""

    def __init__(self, project_id: str, existing_name: str = ""):
        nombre = f" ({existing_name!r})" if existing_name else ""
        super().__init__(
            f"Este paquete corresponde a un proyecto que ya está en esta instalación{nombre}, "
            f"id={project_id!r}. Importarlo encima mezclaría sus archivos. Puede importarlo "
            "como copia: se le asigna un identificador nuevo y el proyecto existente no se toca."
        )
        self.project_id = project_id
        self.existing_name = existing_name


class ImportResidueError(ProjectDomainError):
    """Ronda 88 (2026-10-02, hallazgo real de usuario): una importación
    anterior falló DESPUÉS de copiar los archivos del paquete (por
    ejemplo por un nombre de proyecto repetido), y dejó en
    projects/<id>/ una carpeta que no está registrada como proyecto.
    Antes, cualquier reintento chocaba con ProjectIdCollisionError sin
    salida desde la interfaz. Ahora se informa qué pasó y se ofrece
    apartar esa carpeta (se mueve, no se borra) y continuar."""

    def __init__(self, project_id: str):
        super().__init__(
            f"Hay restos de una importación anterior incompleta de este paquete (carpeta del "
            f"proyecto id={project_id!r} sin registrar en la lista de proyectos). Puede apartarlos "
            "y continuar: se mueven a la carpeta 'residuos_importacion' de la instalación, no se borran."
        )
        self.project_id = project_id


class ImportNameCollisionError(ProjectDomainError):
    """Ronda 88 (2026-10-02, hallazgo real de usuario): el nombre del
    proyecto del paquete ya lo usa otro proyecto de esta instalación.
    Antes se descubría al final, como un IntegrityError crudo de SQLite
    ("UNIQUE constraint failed: project_index.name"), y dejaba los
    archivos copiados en disco (ver ImportResidueError). Ahora se detecta
    antes de copiar nada y la interfaz pide otro nombre."""

    def __init__(self, name: str, suggested_name: str):
        super().__init__(
            f"Ya existe un proyecto llamado {name!r} en esta instalación. Para importar el paquete, "
            f"elija otro nombre (por ejemplo {suggested_name!r}). El proyecto existente no se modifica."
        )
        self.name = name
        self.suggested_name = suggested_name


class ProjectInUseError(ProjectDomainError):
    """Ronda 3 (punto 13) / Ronda 4 de Validacion_observaciones_RAG_STUDIO.md:
    hoy la única forma de "quitar de en medio" un proyecto es Archivar,
    una transición permanente -- no hay eliminación real. Se agrega
    borrado real, pero solo para un proyecto vacío (sin fuentes
    registradas): mismo criterio ya usado para campos y catálogos
    (bloquear si ya hay datos de negocio dependientes, para no perder
    trabajo por accidente)."""

    def __init__(self, project_id: str, source_count: int):
        super().__init__(
            f"No se puede eliminar el proyecto {project_id!r}: ya tiene {source_count} fuente(s) "
            "registrada(s). Si de verdad quieres dejar de usarlo, archívalo en vez de eliminarlo."
        )
        self.project_id = project_id
        self.source_count = source_count
