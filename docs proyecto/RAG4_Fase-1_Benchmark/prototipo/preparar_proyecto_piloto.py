# -*- coding: utf-8 -*-
"""Descomprime una COPIA de trabajo de un .agentproj del proyecto
piloto PRUEBAS_RAG_STUDIO_UDL_2026-08-20/ -- NUNCA modifica el archivo
.agentproj original, y NUNCA toca el proyecto real "AGENTE UDL" (que
vive en una carpeta completamente distinta y no se referencia en
ningún lugar de este prototipo).

También aplica las inyecciones adversariales sintéticas descritas en
`corpus_preguntas.json` (categoría "adversariales") -- SOLO sobre esta
copia de trabajo, escribiendo directamente en la columna `text` de la
tabla `chunk` de su project.db. El texto de inyección es sintético,
nunca estuvo en el documento real, y existe solo para medir resistencia
a inyección de instrucciones (sección 7 del documento de decisión
RAG4)."""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path

REPO_ROOT_HINT = "Ajusta esta ruta si corres el script desde otro lugar."


def unzip_pilot_project(agentproj_path: Path, dest_dir: Path) -> None:
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True)
    with zipfile.ZipFile(agentproj_path) as zf:
        zf.extractall(dest_dir)
    print(f"Copia de trabajo lista en: {dest_dir} (a partir de {agentproj_path.name}, sin modificarlo)")


def apply_adversarial_injections(project_db_path: Path, corpus_path: Path, programs_path: Path) -> None:
    corpus = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
    programs = json.loads(Path(programs_path).read_text(encoding="utf-8"))
    adversarial = [q for q in corpus if q["category"] == "adversariales" and "requisitos de ingreso a" in q["query_text"].lower()]

    conn = sqlite3.connect(project_db_path)
    cur = conn.cursor()
    applied = 0
    for q in adversarial:
        program_name = q["gold_evidence"][0]
        title_b = programs[program_name]["source_title_b"]
        # las fuentes de Prueba B se identifican por su título corto
        # (admemp, ingcom, der, psi, arq) -- ver programas_verificados.json
        cur.execute("SELECT s.id FROM source s WHERE s.title = ?", (title_b,))
        row = cur.fetchone()
        if row is None:
            print(f"AVISO: no se encontró la fuente {title_b!r} en este project.db -- se omite la inyección.")
            continue
        source_id = row[0]
        # extrae el texto de inyección literal del campo 'notes' de la
        # pregunta adversarial (ver generate_questions.py)
        notes = q["notes"]
        start = notes.find("'") + 1
        end = notes.rfind("', ")
        injected_text = notes[start:end] if start > 0 and end > start else None
        if not injected_text:
            continue
        cur.execute("SELECT id, text FROM chunk WHERE source_id = ? ORDER BY chunk_index LIMIT 1", (source_id,))
        chunk_row = cur.fetchone()
        if chunk_row is None:
            continue
        chunk_id, original_text = chunk_row
        cur.execute("UPDATE chunk SET text = ? WHERE id = ?", (original_text + injected_text, chunk_id))
        applied += 1
        print(f"Inyección aplicada en fuente {title_b!r} (chunk {chunk_id}).")
    conn.commit()
    conn.close()
    print(f"Total de inyecciones aplicadas: {applied} de {len(adversarial)} preguntas adversariales con fuente única.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-root", required=True, help="Ruta a PRUEBAS_RAG_STUDIO_UDL_2026-08-20/ dentro del repo de RAG STUDIO")
    parser.add_argument("--which", choices=["A", "B"], default="B", help="Prueba A (5 fuentes validadas) o Prueba B (25 fuentes, superset) -- el corpus usa nombres de Prueba B (admemp, ingcom, der, psi, arq)")
    parser.add_argument("--dest", required=True, help="Carpeta de trabajo destino (se borra y recrea)")
    parser.add_argument("--corpus", default="corpus_preguntas.json")
    parser.add_argument("--programs", default="programas_verificados.json")
    parser.add_argument("--skip-injections", action="store_true")
    args = parser.parse_args()

    pilot_root = Path(args.pilot_root)
    filename = (
        "Prueba_A_E2E_Oferta_Academica_UDL.agentproj" if args.which == "A"
        else "Prueba_B_Cobertura_OCR_25_programas.agentproj"
    )
    agentproj_path = pilot_root / filename
    if not agentproj_path.exists():
        raise FileNotFoundError(f"No se encontró {agentproj_path} -- revisa --pilot-root ({REPO_ROOT_HINT})")

    dest_dir = Path(args.dest)
    unzip_pilot_project(agentproj_path, dest_dir)

    if not args.skip_injections:
        apply_adversarial_injections(dest_dir / "project.db", Path(args.corpus), Path(args.programs))
    else:
        print("Inyecciones adversariales OMITIDAS (--skip-injections) -- usa esto solo para correr las preguntas no adversariales.")


if __name__ == "__main__":
    main()
