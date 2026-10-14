# -*- coding: utf-8 -*-
"""Actividad 4 (parcial): agrega resultados_benchmark.jsonl (producido
por run_benchmark.py) por categoría y sistema, y calcula un proxy
automático de cobertura de evidencia (¿las fuentes que gold_evidence
dice que hacen falta aparecen entre selected_sources?). Esto NO
reemplaza la lectura manual de las respuestas (criterio de aprobación
real, sección 10.4 del documento de decisión, es cualitativo) -- es un
primer resumen cuantitativo para no tener que leer los 188 renglones
(94 preguntas x 2 sistemas) a mano antes de empezar el análisis."""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path


def cargar_programas_a_titulo(programs_path: Path) -> dict[str, str]:
    programs = json.loads(programs_path.read_text(encoding="utf-8"))
    return {name: p["source_title_b"] for name, p in programs.items()}


def cargar_id_a_titulo(project_db_path: Path) -> dict[str, str]:
    """id de fuente (UUID) -> título corto (admemp, ingcom, ...) -- para
    poder comparar selected_sources (que RagService devuelve como IDs)
    contra gold_evidence (que usa nombres de programa, ver
    programas_verificados.json)."""
    conn = sqlite3.connect(project_db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, title FROM source")
        return {row[0]: row[1] for row in cur.fetchall()}
    finally:
        conn.close()


def evidencia_cubierta(
    gold_evidence: list, selected_sources: list[str],
    nombre_a_titulo: dict[str, str], id_a_titulo: dict[str, str],
) -> float | None:
    """Fracción de los programas en gold_evidence cuyo título de fuente
    aparece entre selected_sources -- None si gold_evidence no lista
    nombres de programa (algunas preguntas ambiguas/multi-hop tienen
    texto libre ahí en vez de una lista de nombres, ver
    generate_questions.py) o si no se pasó --snapshot-dir (id_a_titulo
    vacío)."""
    if not isinstance(gold_evidence, list) or not gold_evidence or not id_a_titulo:
        return None
    titulos_esperados = {nombre_a_titulo[n] for n in gold_evidence if n in nombre_a_titulo}
    if not titulos_esperados:
        return None
    titulos_obtenidos = {id_a_titulo.get(sid) for sid in selected_sources}
    return len(titulos_esperados & titulos_obtenidos) / len(titulos_esperados)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resultados", default="resultados_benchmark.jsonl")
    parser.add_argument("--programs", default="programas_verificados.json")
    parser.add_argument("--snapshot-dir", default=None, help="Si se pasa, calcula el proxy de cobertura de evidencia contra project.db de esa carpeta")
    args = parser.parse_args()

    nombre_a_titulo = cargar_programas_a_titulo(Path(args.programs))
    id_a_titulo = cargar_id_a_titulo(Path(args.snapshot_dir) / "project.db") if args.snapshot_dir else {}

    filas = [json.loads(line) for line in Path(args.resultados).read_text(encoding="utf-8").splitlines() if line.strip()]

    por_categoria_sistema = defaultdict(list)
    for fila in filas:
        por_categoria_sistema[(fila["category"], fila["system"])].append(fila)

    print(f"{'Categoría':<16} {'Sistema':<8} {'N':>4} {'Latencia p50 (ms)':>18} {'Retrievals prom.':>18} {'Cobertura prom.':>16} {'Errores':>8}")
    for (categoria, sistema), filas_grupo in sorted(por_categoria_sistema.items()):
        latencias = [f["latency_ms"] for f in filas_grupo]
        retrievals = [f["num_retrievals"] for f in filas_grupo]
        errores = sum(1 for f in filas_grupo if f.get("error"))
        coberturas = [
            c for f in filas_grupo
            if (c := evidencia_cubierta(f.get("gold_evidence"), f.get("selected_sources", []), nombre_a_titulo, id_a_titulo)) is not None
        ]
        p50 = statistics.median(latencias) if latencias else 0.0
        cobertura_txt = f"{statistics.mean(coberturas):.2f} (n={len(coberturas)})" if coberturas else "n/d"
        print(f"{categoria:<16} {sistema:<8} {len(filas_grupo):>4} {p50:>18.1f} {statistics.mean(retrievals):>18.2f} {cobertura_txt:>16} {errores:>8}")

    print(
        "\nNOTA: este resumen es solo de instrumentación (latencia, número de "
        "retrievals, tasa de error) -- NO decide el criterio de aprobación de "
        "la sección 10.4 (mejora significativa de evidencia correcta), que "
        "exige leer las respuestas reales y compararlas contra gold_answer en "
        "corpus_preguntas.json. Ver README.md, sección 'Cómo completar el "
        "análisis' para el resto de la Actividad 4."
    )


if __name__ == "__main__":
    main()
