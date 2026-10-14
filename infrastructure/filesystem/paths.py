"""Layout de directorios en disco (ADR-001, sección 7 / RAG STUDIO.odt, sección 4).

agent_studio/
├── application.db
├── settings/ models/ plugins/ logs/
└── projects/
    └── <project_id>/
        ├── project.db
        ├── manifest.json
        ├── sources/{original, extracted, normalized}/
        ├── chunks/  indexes/  pipelines/  rules/
        ├── tests/  runs/  evidence/  reports/
"""
from __future__ import annotations

from pathlib import Path

_PROJECT_SUBDIRS = [
    "sources/original",
    "sources/extracted",
    "sources/normalized",
    "chunks",
    "indexes",
    "pipelines",
    "rules",
    "tests",
    "runs",
    "evidence",
    "reports",
]


class InstallationPaths:
    """Resuelve rutas para una instalación de RAG STUDIO en esta laptop."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)

    def application_db_path(self) -> Path:
        return self.base_dir / "application.db"

    def settings_dir(self) -> Path:
        return self.base_dir / "settings"

    def models_dir(self) -> Path:
        return self.base_dir / "models"

    def plugins_dir(self) -> Path:
        return self.base_dir / "plugins"

    def logs_dir(self) -> Path:
        return self.base_dir / "logs"

    def projects_dir(self) -> Path:
        return self.base_dir / "projects"

    def project_dir(self, project_id: str) -> Path:
        return self.projects_dir() / project_id

    def project_db_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "project.db"

    def manifest_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "manifest.json"

    def qdrant_index_dir(self, project_id: str) -> Path:
        """Directorio del indice vectorial local (Etapa 4): un
        QdrantClient(path=...) por proyecto, dentro del subdirectorio
        "indexes" ya reservado en el layout (ver docstring del
        modulo). Igual que project.db, viaja dentro de .agentproj sin
        cambios en el empaquetador (FilesystemProjectPackager
        recorre project_dir/** recursivamente)."""
        return self.project_dir(project_id) / "indexes" / "qdrant"

    def snapshots_dir(self, project_id: str) -> Path:
        """Raíz de las instantáneas publicadas de un proyecto
        (ADR-002, Fase 1) -- deliberadamente fuera de
        projects/<project_id>, para que nunca quede incluida si algo
        llegara a copiar ese directorio recursivamente (como ya hace
        FilesystemProjectPackager) y para que un futuro runtime nunca
        necesite distinguir "mis propios archivos" de los que la app
        de escritorio edita en vivo."""
        return self.base_dir / "snapshots" / project_id

    def snapshot_version_dir(self, project_id: str, version: int) -> Path:
        return self.snapshots_dir(project_id) / f"v{version}"

    def runtime_db_path(self) -> Path:
        """El SQLite propio del proceso `interfaces/api/` (ADR-002,
        Fase 2: bitácora de conversaciones; Fase 4: tokens de widget)
        -- vive en la misma instalación que `application.db`, un nivel
        por encima de `projects/`, porque una fila puede pertenecer a
        cualquier proyecto atendido (no es "un archivo por proyecto").
        Antes de la Fase 5 este literal solo existía, repetido, en
        `interfaces/api/app.py` (`installation_dir / "runtime.db"`);
        aquí queda como único punto de verdad para que la app de
        escritorio (Fase 5, pestaña de Monitoreo) pueda leer el mismo
        archivo sin duplicar la ruta. Puede no existir todavía -- si el
        runtime nunca corrió contra esta instalación, no hay nada que
        monitorear (ver RuntimeMonitoringService)."""
        return self.base_dir / "runtime.db"

    def ensure_installation_layout(self) -> None:
        for d in (self.settings_dir(), self.models_dir(), self.plugins_dir(),
                  self.logs_dir(), self.projects_dir()):
            d.mkdir(parents=True, exist_ok=True)

    def ensure_project_layout(self, project_id: str) -> Path:
        project_dir = self.project_dir(project_id)
        for sub in _PROJECT_SUBDIRS:
            (project_dir / sub).mkdir(parents=True, exist_ok=True)
        return project_dir


class SnapshotInstallationPaths(InstallationPaths):
    """Adaptador de InstallationPaths para interfaces/api/ (ADR-002,
    Fase 2): redirige `project_dir(project_id)` a una instantánea
    publicada específica (`snapshots/<project_id>/v<n>/`, ver
    ProjectSnapshot) en vez de `projects/<project_id>`, que la app de
    escritorio sigue editando en vivo.

    `project_db_path`/`manifest_path`/`qdrant_index_dir` ya se definen
    en `InstallationPaths` en términos de `self.project_dir(...)` --
    heredarlos funciona sin duplicar ninguna lógica de rutas, y
    permite reutilizar sin cambios todos los repositorios SQLAlchemy y
    QdrantLocalVectorStore ya existentes, apuntándolos a la
    instantánea en vez del proyecto en edición.

    `models_dir()`/`settings_dir()`/etc. siguen resolviendo contra
    `runtime_dir` (no contra la instantánea, que es de solo lectura y
    no debería recibir escrituras nuevas como la caché de modelos de
    embeddings) -- ver ADR-002, sección 5, sobre por qué la
    instantánea debe permanecer intacta."""

    def __init__(self, project_id: str, snapshot_dir: str | Path, runtime_dir: str | Path):
        super().__init__(base_dir=runtime_dir)
        self._project_id = project_id
        self._snapshot_dir = Path(snapshot_dir)

    def project_dir(self, project_id: str) -> Path:
        if project_id != self._project_id:
            raise ValueError(
                f"Esta instantánea solo sirve al proyecto {self._project_id!r}, no {project_id!r}."
            )
        return self._snapshot_dir
