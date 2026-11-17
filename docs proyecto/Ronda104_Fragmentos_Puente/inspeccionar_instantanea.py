"""Ronda 104b -- inspección de SOLO LECTURA de una instantánea publicada, un
paquete de entrega (.zip) o un .agentproj, para reproducir un trace del
Runtime: identidad, revisión de esquema (indica la versión mínima de RAG
Studio que escribió o abrió la base), políticas de fragmentación efectivas
por fuente, fragmentos por fuente y, opcionalmente, el detalle de los
fragmentos de un trace.

No ejecuta migraciones ni escribe nada: copia project.db a un directorio
temporal y lo abre con sqlite3 en modo solo lectura.

Uso:
  python3 inspeccionar_instantanea.py <carpeta_instantanea | paquete.zip | proyecto.agentproj> \
      [--chunks id1,id2,...] [--json salida.json]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

# Revisión de esquema del proyecto -> ronda que la introdujo (referencia).
REVISIONES = {
    "0020": "Ronda 69 (ruta de imagen)", "0021": "RAG-INC-01a (identidades NEXOM)",
    "0022": "Ronda 98 (traza de políticas en el pipeline)", "0023": "Ronda 100 (chunk.section_path)",
    "0024": "Ronda 102 (project.agent_reranking)",
}
_PALABRA = re.compile(r"\w+", re.UNICODE)


def _localizar(origen: Path, tmp: Path) -> tuple[Path, dict | None]:
    """Devuelve (copia de project.db, snapshot_identity.json si existe)."""
    if origen.is_dir():
        dbs = sorted(origen.rglob("project.db"))
        ids = sorted(origen.rglob("snapshot_identity.json"))
        if not dbs:
            raise SystemExit("No se encontró project.db")
        destino = tmp / "project.db"
        shutil.copy2(dbs[0], destino)
        return destino, (json.loads(ids[0].read_text(encoding="utf-8")) if ids else None)
    with zipfile.ZipFile(origen) as z:
        nombres = z.namelist()
        db = next((n for n in nombres if n.endswith("project.db")), None)
        if db is None:
            raise SystemExit("El archivo no contiene project.db")
        destino = tmp / "project.db"
        destino.write_bytes(z.read(db))
        ident = next((n for n in nombres if n.endswith("snapshot_identity.json")), None)
        return destino, (json.loads(z.read(ident)) if ident else None)


def _columnas(c, tabla):
    return [r[1] for r in c.execute(f"pragma table_info({tabla})")]


def _sin_yaml(texto: str) -> str:
    lineas = (texto or "").split("\n")
    if lineas and lineas[0].strip() == "---":
        for j in range(1, len(lineas)):
            if lineas[j].strip() in ("---", "..."):
                return "\n".join(lineas[j + 1:])
    return texto or ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("origen", type=Path)
    ap.add_argument("--chunks", default="")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    informe: dict = {}
    with tempfile.TemporaryDirectory() as t:
        db, identidad = _localizar(a.origen, Path(t))
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        informe["identidad"] = identidad
        revision = next(iter(c.execute("select version_num from alembic_version")), [None])[0]
        informe["revision_esquema"] = {"valor": revision, "introducida_en": REVISIONES.get(revision, "anterior")}
        cols_chunk = _columnas(c, "chunk")
        cols_project = _columnas(c, "project")
        informe["capacidades"] = {
            "chunk.section_path (Ronda 100)": "section_path" in cols_chunk,
            "project.agent_reranking (Ronda 102)": "agent_reranking" in cols_project,
        }
        proyecto = c.execute("select * from project").fetchone()
        informe["proyecto"] = dict(zip(cols_project, proyecto, strict=False)) if proyecto else None
        informe["politicas"] = [dict(zip(_columnas(c, "fragmentation_policy"), r, strict=False))
                                for r in c.execute("select * from fragmentation_policy")]
        info = c.execute("select * from index_info").fetchone()
        informe["indice"] = dict(zip(_columnas(c, "index_info"), info, strict=False)) if info else None
        cols_item = _columnas(c, "pipeline_run_item")
        fuentes = []
        for sid, titulo, tipo, estado, acceso in c.execute(
                "select id, title, document_type_code, validation_status, access_level from source order by title"):
            filas = c.execute("select text, section_title, chunk_type from chunk where source_id=?", (sid,)).fetchall()
            item = None
            if "policy_strategy" in cols_item:
                item = c.execute(
                    "select policy_strategy, policy_origin, policy_hash, finished_at from pipeline_run_item "
                    "where source_id=? and status='completado' order by finished_at desc limit 1", (sid,)).fetchone()
            fuentes.append({
                "source_id": sid, "titulo": titulo, "tipo_documento": tipo, "validacion": estado, "acceso": acceso,
                "fragmentos": len(filas),
                "solo_yaml": sum(1 for f in filas if not _PALABRA.findall(_sin_yaml(f[0]))),
                "sin_titulo_de_seccion": sum(1 for f in filas if not f[1]),
                "tipos": sorted({f[2] for f in filas}),
                "ultima_politica_aplicada": dict(zip(("estrategia", "origen", "hash", "fecha"), item, strict=False)) if item else None,
            })
        informe["fuentes"] = fuentes
        if a.chunks:
            detalle = []
            for cid in a.chunks.split(","):
                fila = c.execute("select c.source_id, s.title, c.section_title, c.chunk_type, c.text from chunk c "
                                 "join source s on s.id=c.source_id where c.id=?", (cid.strip(),)).fetchone()
                if fila is None:
                    detalle.append({"chunk_id": cid, "encontrado": False})
                    continue
                cuerpo = _sin_yaml(fila[4])
                detalle.append({
                    "chunk_id": cid, "source_id": fila[0], "fuente": fila[1], "titulo_seccion": fila[2],
                    "tipo": fila[3], "palabras_sin_yaml": len(_PALABRA.findall(cuerpo)),
                    "inicio": cuerpo.strip()[:160],
                })
            informe["fragmentos_del_trace"] = detalle
        c.close()
    texto = json.dumps(informe, indent=1, ensure_ascii=False, default=str)
    print(texto)
    if a.json:
        a.json.write_text(texto, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
