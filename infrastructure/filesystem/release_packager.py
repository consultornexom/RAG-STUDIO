"""Implementación filesystem de ReleasePackager (domain.release.ports)
-- ítem 6 de la evaluación de madurez post-8-etapas: paquete
exportable real (un .zip con archivos legibles), no solo el JSON en
línea de ReleaseRecord.deliverables_report.

Formato (deliberadamente simple, sin manifiesto de integridad tipo
.agentproj -- este paquete es un entregable de lectura para humanos y
auditoría externa, no algo que se vuelva a importar como proyecto):

    release-<id>.zip
    ├── manifest.json           (identificación de la liberación + evidencia)
    ├── dictamen.txt            (resumen humano, texto plano)
    ├── checklist.json          (las compuertas evaluadas, con motivo)
    └── entregables/
        ├── especificacion_metadatos.json
        ├── diseno_fragmentacion.json
        ├── pipeline_reproducible.json
        ├── indice_y_recuperacion.json
        ├── catalogo_reglas.json
        ├── esquema_canalizacion.json
        ├── banco_de_pruebas.json
        └── matriz_resultados_esperados.json
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from domain.release.entities import ReleaseRecord
from domain.release.ports import ReleasePackager


class FilesystemReleasePackager(ReleasePackager):
    def export(self, record: ReleaseRecord, destination_path: str) -> str:
        destination = Path(destination_path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        manifest = {
            "release_id": record.id,
            "project_id": record.project_id,
            "status": record.status.value,
            "created_at": record.created_at.isoformat(),
            "dictamen": record.dictamen,
            "evidence": record.evidence,
            "compuertas_cumplidas": record.checklist.all_passed,
        }
        checklist = {
            "compuertas": [
                {"nombre": gate.name, "cumplida": gate.passed, "motivo": gate.reason}
                for gate in record.checklist.gates
            ],
        }

        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            zf.writestr("dictamen.txt", record.dictamen)
            zf.writestr("checklist.json", json.dumps(checklist, indent=2, ensure_ascii=False))
            for key, payload in record.deliverables_report.items():
                zf.writestr(f"entregables/{key}.json", json.dumps(payload, indent=2, ensure_ascii=False))

        return str(destination)
