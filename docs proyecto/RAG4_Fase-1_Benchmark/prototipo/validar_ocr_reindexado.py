# -*- coding: utf-8 -*-
"""Ronda 75 (siguiente accion propuesta): valida cuantitativamente la
mejora de OCR de la Ronda 74 -- no solo "el texto se ve mejor", sino
"la recuperacion mejora de verdad". Reprocesa las 25 fuentes reales de
Prueba_B_Cobertura_OCR_25_programas.agentproj desde cero (extraccion +
OCR con preprocess=True, ya default + fragmentacion + indexado) en una
copia de trabajo nueva, y compara la misma metrica de cobertura de
evidencia (evidencia_cubierta, ya usada en analizar_resultados.py)
contra el mismo gold set de corpus_preguntas.json, usando exactamente
el mismo RagService.search_hybrid (Sistema A, sin LLM) que ya se uso en
la Ronda 73. Reconstruye AMBOS lados (antes: preprocess=False, despues:
preprocess=True) desde cero, aqui mismo, con el mismo idioma de OCR
(SANDBOX_OCR_LANG), para aislar unicamente la variable de
preprocesamiento -- no se compara contra el indice viejo de
trabajo/piloto_b porque ese se construyo en la maquina real del
consultor con "spa+eng", lo que mezclaria la variable de idioma con la
de preprocesamiento.

Nunca toca el proyecto real "AGENTE UDL" -- todo corre sobre una copia
de trabajo nueva de Prueba_B."""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path("/sessions/sweet-pensive-pasteur/mnt/RAG STUDIO")
PROTOTIPO_DIR = REPO_ROOT / "docs proyecto/RAG4_Fase-1_Benchmark/prototipo"
sys.path.insert(0, str(REPO_ROOT))

from application.rag.service import RagService  # noqa: E402
from application.ingestion.service import IngestionService  # noqa: E402
from infrastructure.database.document_repositories import SqlAlchemySourceRepository  # noqa: E402
from infrastructure.database.ingestion_repositories import (  # noqa: E402
    SqlAlchemyChunkRepository,
    SqlAlchemyExtractionRepository,
    SqlAlchemyFragmentationPolicyRepository,
)
from infrastructure.database.metadata_repositories import (  # noqa: E402
    SqlAlchemyMetadataSchemaRepository,
    SqlAlchemySourceMetadataRepository,
)
from infrastructure.database.rag_repositories import SqlAlchemyIndexInfoRepository  # noqa: E402
from infrastructure.embeddings.fastembed_provider import make_provider_for_profile  # noqa: E402
from infrastructure.extraction.ocr_engine import TesseractOcrEngine  # noqa: E402
from infrastructure.extraction.text_extractors import (  # noqa: E402
    CompositeTextExtractor,
    CsvExtractor,
    DocxExtractor,
    HtmlExtractor,
    ImageTextExtractor,
    JsonExtractor,
    PdfTextExtractor,
    TxtExtractor,
    XlsxExtractor,
    XmlExtractor,
)
from infrastructure.filesystem.paths import InstallationPaths  # noqa: E402
from infrastructure.tokenization.tiktoken_counter import TiktokenCounter  # noqa: E402
from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore  # noqa: E402

PROJECT_ID = "aa0c6d50-66a3-4a3d-bb96-fdb6f05dfac0"
MODELS_CACHE_DIR = REPO_ROOT / "data" / "models"  # cache ya poblado -- evita depender de huggingface.co


SANDBOX_OCR_LANG = "eng"  # este entorno de consultoria solo tiene el
# paquete de idioma ingles de Tesseract (sin "spa"), a diferencia de la
# maquina real del consultor -- ver test_ocr_engine.py. Usar "eng" para
# AMBOS lados (antes y despues) es deliberado: si se comparara contra
# el indice viejo ya existente (construido en la maquina real, con
# "spa+eng"), la diferencia medida mezclaria dos variables (idioma Y
# preprocesamiento) en vez de aislar solo el efecto del preprocesamiento
# -- por eso este script reconstruye AMBOS lados desde cero, aqui
# mismo, con el mismo idioma, cambiando unicamente `preprocess`.


def build_ingestion_service(paths, preprocess: bool) -> IngestionService:
    ocr_engine = TesseractOcrEngine(lang=SANDBOX_OCR_LANG, preprocess=preprocess)
    text_extractor = CompositeTextExtractor([
        TxtExtractor(), DocxExtractor(),
        PdfTextExtractor(ocr_engine=ocr_engine), ImageTextExtractor(ocr_engine=ocr_engine),
        XlsxExtractor(), CsvExtractor(), HtmlExtractor(), JsonExtractor(), XmlExtractor(),
    ])
    return IngestionService(
        SqlAlchemySourceRepository(paths), text_extractor, SqlAlchemyExtractionRepository(paths),
        SqlAlchemyFragmentationPolicyRepository(paths), SqlAlchemyChunkRepository(paths),
        SqlAlchemyMetadataSchemaRepository(paths), SqlAlchemySourceMetadataRepository(paths),
        token_counter=TiktokenCounter(),
    )


def build_rag_service(paths) -> RagService:
    embedding_provider = make_provider_for_profile(cache_dir=MODELS_CACHE_DIR)
    return RagService(
        SqlAlchemyChunkRepository(paths), embedding_provider, QdrantLocalVectorStore(paths),
        SqlAlchemyIndexInfoRepository(paths), source_repository=SqlAlchemySourceRepository(paths),
    )


def reindex_some_sources(base_dir: Path, preprocess: bool, start: int, end: int | None) -> None:
    """Reprocesa un RANGO de fuentes del proyecto (sources[start:end])
    desde cero: extraccion (con OCR, preprocess segun parametro) +
    fragmentacion + indexado. IndexSource/FragmentSource ya borran los
    chunks/vectores viejos antes de escribir los nuevos (confirmado por
    codigo) -- no hay duplicados.

    Se procesa por rangos, en llamadas separadas, a proposito: este
    entorno de consultoria ejecuta cada comando de shell dentro de su
    propio namespace de procesos (bwrap --unshare-pid) -- un proceso
    dejado en segundo plano (nohup/setsid/disown) SIEMPRE muere en el
    instante en que termina la llamada que lo lanzo, sin excepcion, sin
    importar la tecnica usada para "desprenderlo". Confirmado
    empiricamente en esta misma ronda (ver bitacora). La unica forma
    confiable de correr un trabajo largo aqui es en primer plano, dentro
    de una sola llamada, y si no cabe en una sola llamada, dividirlo en
    llamadas sucesivas y sincronicas como esta funcion permite."""
    paths = InstallationPaths(base_dir=base_dir)
    ingestion_service = build_ingestion_service(paths, preprocess=preprocess)
    rag_service = build_rag_service(paths)

    source_repository = SqlAlchemySourceRepository(paths)
    all_sources = source_repository.list_for_project(PROJECT_ID)
    sources = all_sources[start:end]
    print(
        f"Reprocesando fuentes [{start}:{end}] de {len(all_sources)} "
        f"totales (preprocess={preprocess}, lang={SANDBOX_OCR_LANG})...",
        flush=True,
    )
    errores = []
    for i, source in enumerate(sources, start=start + 1):
        print(f"  [{i}/{len(all_sources)}] {source.title}: empezando...", flush=True)
        t0 = time.monotonic()
        try:
            ingestion_service.extract_source_text(PROJECT_ID, source.id)
            ingestion_service.fragment_source(PROJECT_ID, source.id)
            rag_service.index_source(PROJECT_ID, source.id)
            print(f"  [{i}/{len(all_sources)}] {source.title} ({time.monotonic()-t0:.1f}s)", flush=True)
        except Exception as exc:  # noqa: BLE001 -- registrar y seguir con las demas fuentes
            print(f"  [{i}/{len(all_sources)}] {source.title}: ERROR {type(exc).__name__}: {exc}", flush=True)
            errores.append((source.title, str(exc)))
    if errores:
        print(f"AVISO: {len(errores)} fuente(s) con error: {[t for t, _ in errores]}")


def id_a_titulo(project_db_path: Path) -> dict[str, str]:
    conn = sqlite3.connect(project_db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, title FROM source")
        return {row[0]: row[1] for row in cur.fetchall()}
    finally:
        conn.close()


def evidencia_cubierta(gold_evidence, selected_sources, nombre_a_titulo, id_a_titulo_map):
    if not isinstance(gold_evidence, list) or not gold_evidence:
        return None
    esperados = {nombre_a_titulo[n] for n in gold_evidence if n in nombre_a_titulo}
    if not esperados:
        return None
    obtenidos = {id_a_titulo_map.get(sid) for sid in selected_sources}
    return len(esperados & obtenidos) / len(esperados)


def recall_at_3(gold_evidence, selected_sources, nombre_a_titulo, id_a_titulo_map):
    """Variante mas estricta que evidencia_cubierta: solo mira los
    primeros 3 resultados devueltos (top_k real de una respuesta
    tipica), no el limit=5 completo -- mismo espiritu de Recall@3 que
    ya usa QualityService en producto."""
    if not isinstance(gold_evidence, list) or not gold_evidence:
        return None
    esperados = {nombre_a_titulo[n] for n in gold_evidence if n in nombre_a_titulo}
    if not esperados:
        return None
    obtenidos = {id_a_titulo_map.get(sid) for sid in selected_sources[:3]}
    return len(esperados & obtenidos) / len(esperados)


def medir(rag_service, project_id: str, project_db_path: Path, corpus, programs) -> dict:
    nombre_a_titulo = {name: p["source_title_b"] for name, p in programs.items()}
    id_a_titulo_map = id_a_titulo(project_db_path)

    filas = []
    for pregunta in corpus:
        try:
            results = rag_service.search_hybrid(project_id, pregunta["query_text"], limit=5)
            selected_sources = sorted({r.chunk.source_id for r in results})
        except Exception as exc:  # noqa: BLE001
            print(f"  AVISO {pregunta['id']}: {type(exc).__name__}: {exc}")
            selected_sources = []
        filas.append({**pregunta, "selected_sources": selected_sources})

    por_categoria = {}
    for fila in filas:
        cat = fila["category"]
        por_categoria.setdefault(cat, []).append(fila)

    resumen = {}
    todas_cob, todas_r3 = [], []
    for cat, filas_cat in sorted(por_categoria.items()):
        cobs = [
            c for f in filas_cat
            if (c := evidencia_cubierta(f.get("gold_evidence"), f["selected_sources"], nombre_a_titulo, id_a_titulo_map)) is not None
        ]
        r3s = [
            c for f in filas_cat
            if (c := recall_at_3(f.get("gold_evidence"), f["selected_sources"], nombre_a_titulo, id_a_titulo_map)) is not None
        ]
        resumen[cat] = {
            "n": len(filas_cat),
            "cobertura": statistics.mean(cobs) if cobs else None,
            "recall_at_3": statistics.mean(r3s) if r3s else None,
        }
        todas_cob.extend(cobs)
        todas_r3.extend(r3s)
    resumen["TOTAL"] = {
        "n": len(filas),
        "cobertura": statistics.mean(todas_cob) if todas_cob else None,
        "recall_at_3": statistics.mean(todas_r3) if todas_r3 else None,
    }
    return resumen


ANTES_DIR = PROTOTIPO_DIR / "trabajo" / "validacion_ocr_antes"  # preprocess=False
DESPUES_DIR = PROTOTIPO_DIR / "trabajo" / "validacion_ocr_despues"  # preprocess=True


def unzip_fresh_copy(dest_base_dir: Path) -> None:
    import shutil
    import zipfile

    project_dir = dest_base_dir / "projects" / PROJECT_ID
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    zip_path = PROTOTIPO_DIR / ".." / ".." / ".." / "PRUEBAS_RAG_STUDIO_UDL_2026-08-20" / "Prueba_B_Cobertura_OCR_25_programas.agentproj"
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(project_dir)


def main() -> None:
    corpus = json.loads((PROTOTIPO_DIR / ".." / "corpus_preguntas.json").read_text(encoding="utf-8"))
    programs = json.loads((PROTOTIPO_DIR / ".." / "programas_verificados.json").read_text(encoding="utf-8"))

    accion = sys.argv[1] if len(sys.argv) > 1 else "medir"

    if accion == "preparar_antes":
        unzip_fresh_copy(ANTES_DIR)
        print("OK: copia limpia de trabajo en", ANTES_DIR)
        return
    if accion == "preparar_despues":
        unzip_fresh_copy(DESPUES_DIR)
        print("OK: copia limpia de trabajo en", DESPUES_DIR)
        return
    if accion == "reindexar_antes":
        start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        end = int(sys.argv[3]) if len(sys.argv) > 3 else None
        reindex_some_sources(ANTES_DIR, preprocess=False, start=start, end=end)
        return
    if accion == "reindexar_despues":
        start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        end = int(sys.argv[3]) if len(sys.argv) > 3 else None
        reindex_some_sources(DESPUES_DIR, preprocess=True, start=start, end=end)
        return

    # "medir_antes" / "medir_despues": partido en dos comandos separados
    # (en vez de un solo "medir" que hace ambos) por la misma razon que
    # reindexar_* se partio en rangos -- 94 preguntas x 2 indices, cada
    # una con su propia carga del modelo de embeddings, no cabe con
    # margen holgado en una sola llamada de shell de este entorno.
    if accion == "medir_antes":
        print("=== Midiendo indice ANTES (preprocess=False) ===", flush=True)
        old_paths = InstallationPaths(base_dir=ANTES_DIR)
        old_rag_service = build_rag_service(old_paths)
        resumen_viejo = medir(
            old_rag_service, PROJECT_ID, ANTES_DIR / "projects" / PROJECT_ID / "project.db", corpus, programs,
        )
        out_path = PROTOTIPO_DIR / "trabajo" / "validacion_ocr_resultados_antes.json"
        out_path.write_text(json.dumps(resumen_viejo, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Guardado en {out_path}")
        return

    if accion == "medir_despues":
        print("=== Midiendo indice DESPUES (preprocess=True) ===", flush=True)
        new_paths = InstallationPaths(base_dir=DESPUES_DIR)
        new_rag_service = build_rag_service(new_paths)
        resumen_nuevo = medir(
            new_rag_service, PROJECT_ID, DESPUES_DIR / "projects" / PROJECT_ID / "project.db", corpus, programs,
        )
        out_path = PROTOTIPO_DIR / "trabajo" / "validacion_ocr_resultados_despues.json"
        out_path.write_text(json.dumps(resumen_nuevo, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Guardado en {out_path}")
        return

    # accion == "comparar": solo lee los dos JSON ya escritos por
    # medir_antes/medir_despues y arma la tabla -- no vuelve a correr
    # ninguna busqueda.
    resumen_viejo = json.loads((PROTOTIPO_DIR / "trabajo" / "validacion_ocr_resultados_antes.json").read_text(encoding="utf-8"))
    resumen_nuevo = json.loads((PROTOTIPO_DIR / "trabajo" / "validacion_ocr_resultados_despues.json").read_text(encoding="utf-8"))

    print(f"\n{'Categoria':<16} {'N':>4} {'Cobertura ANTES':>16} {'Cobertura DESPUES':>18} {'Recall@3 ANTES':>15} {'Recall@3 DESPUES':>17}")
    for cat in resumen_viejo:
        v, n = resumen_viejo[cat], resumen_nuevo[cat]
        def fmt(x):
            return f"{x:.3f}" if x is not None else "n/d"
        print(f"{cat:<16} {v['n']:>4} {fmt(v['cobertura']):>16} {fmt(n['cobertura']):>18} {fmt(v['recall_at_3']):>15} {fmt(n['recall_at_3']):>17}")

    out_path = PROTOTIPO_DIR / "trabajo" / "validacion_ocr_resultados.json"
    out_path.write_text(json.dumps({"antes": resumen_viejo, "despues": resumen_nuevo}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGuardado en {out_path}")


if __name__ == "__main__":
    main()
