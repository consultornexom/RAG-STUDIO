"""Ronda 105c -- diagnóstico posterior a P1 (sin cambios en el motor).

Reproduce, con los cinco archivos reales de LOTE01 y los modelos reales, el
procedimiento r105b SIN reranking (lo que hoy hacen el Simulador y el
Runtime con «Automático») y mide, por separado y combinadas, las mejoras
pendientes, simuladas FUERA del motor:

  base  procedimiento actual r105b
  Y     P2a: fragmento solo-YAML sin afinidad de título
  R     P2b: resolución de referencias (puente detrás de su destino; 2 por fuente)
  T     P3:  buscar con la consulta original (sin quitar los valores filtrados;
             el filtro de metadatos se sigue aplicando a las fuentes)
  V     (Ronda 105e) combinación ponderada por el valor de la afinidad
  M     (Ronda 105d) enmascarar el valor de catálogo también dentro del nombre
        de la intención en snake_case
  P4    corpus indexado SIN el encabezado YAML (copias temporales de los
        archivos; los originales no se tocan)

Para las dos consultas del informe (BACH-003/R1 y la del incidente/R2)
imprime el detalle del top 8: fuente, título usado para la afinidad, tipo de
fragmento, puesto en la búsqueda híbrida, en la semántica y en la textual,
afinidad, puntaje combinado RRF y posición final. Para las 14 consultas,
la posición del fragmento correcto.

Supuestos (no se tiene el project.db de AGENTE UDL): intenciones, variables y
políticas de tests/integration/test_ronda102_lote01_simulador.py.

Uso: python3 experimento_post_p1.py --compartidos documento_completo|por_encabezado
        --variantes base,Y,T,YT,YR,YRT [--p4] [--detalle] [--salida r.json]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
for p in (RAIZ, RAIZ / "tests" / "integration", RAIZ / "tests" / "unit" / "application",
          RAIZ / "docs proyecto" / "Ronda102_Diagnostico_Simulador", RAIZ / "docs proyecto" / "Ronda104_Fragmentos_Puente"):
    sys.path.insert(0, str(p))

FOCO = {"R1": "UDL-BACH-003 / requisitos", "R2": "incidente 493c8033 / documentos",
        "R3": "requisitos con plantel"}


def _sin_yaml(texto: str) -> str:
    if texto.startswith("---"):
        fin = texto.find("\n---", 3)
        if fin >= 0:
            return texto[fin + 4:].lstrip("\n")
    return texto


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compartidos", choices=["documento_completo", "por_encabezado", "por_tamanio_todos"],
                    default="documento_completo",
                    help="por_tamanio_todos (Ronda 105d): TODAS las fuentes con por_tamanio 500/60/80, "
                         "configuración real de AGENTE UDL informada por NEXOM")
    ap.add_argument("--variantes", default="base,Y,T,YT,YR,YRT")
    ap.add_argument("--p4", action="store_true", help="indexar copias de los archivos sin YAML")
    ap.add_argument("--detalle", action="store_true")
    ap.add_argument("--documentos", type=Path, help="carpeta alternativa con los cinco archivos (p. ej. corpus "
                    "sintético de la Ronda 102); por defecto, los reales de LOTE01")
    ap.add_argument("--intenciones", choices=["r102", "historico", "historico+asesor", "hipotesis_info", "real"],
                    default="r102",
                    help="r102: 4 históricas + consultar_plan_estudios (supuesta); historico: solo las 4 activas "
                         "del proyecto histórico de Bachillerato; historico+asesor: + solicitar_asesor_admisiones "
                         "(supuesta, Ronda 103)")
    ap.add_argument("--listar", action="store_true", help="lista los fragmentos indexados")
    ap.add_argument("--contador", choices=["palabras", "subpalabras", "x3"], default="palabras",
                    help="conteo de tokens al fragmentar: palabras (1 por palabra); subpalabras (tokenizador "
                         "del modelo de embeddings); x3 (3 por palabra, aproxima tiktoken en español). La "
                         "app real usa tiktoken cl100k_base, no disponible sin red en este entorno")
    ap.add_argument("--salida", type=Path)
    a = ap.parse_args()

    import evaluacion_simulador as ev
    import prototipo_referencias as pr
    import test_ronda102_lote01_simulador as base
    from domain.conversational.section_affinity import (
        SectionAffinity, affinity_title, combine_with_retrieval, raices,
    )
    from domain.ingestion.entities import FragmentationStrategy

    # Ajuste de R propuesto en la Ronda 105: un título sin extensión ni forma
    # de identificador no cuenta como referencia.
    original_nombres = pr.nombres_de_fuente

    def nombres(titulo):
        return [n for n in original_nombres(titulo) if re.search(r"\.[a-z0-9]{1,5}$|[_\-]", n)]

    pr.nombres_de_fuente = nombres
    pr.MAX_POR_FUENTE, pr.MAX_DESTINOS = 2, 5

    tmp = None
    if a.p4:
        tmp = Path(tempfile.mkdtemp())
        for nombre in base.ARCHIVOS:
            (tmp / nombre).write_text(_sin_yaml((base.DOCS / nombre).read_text(encoding="utf-8")), encoding="utf-8")
        base.DOCS = tmp
    if a.compartidos == "por_tamanio_todos":
        original_pt = base.IngestionService.set_fragmentation_policy

        def politica_pt(self, project_id, tipo, **kw):
            kw = dict(strategy=FragmentationStrategy.POR_TAMANIO, target_tokens=500, overlap_tokens=60,
                      min_tokens=80)
            return original_pt(self, project_id, tipo, **kw)

        base.IngestionService.set_fragmentation_policy = politica_pt
    if a.compartidos == "por_encabezado":
        original = base.IngestionService.set_fragmentation_policy

        def politica(self, project_id, tipo, **kw):
            if tipo in ("informacion_admisiones", "informacion_academica"):
                kw = dict(strategy=FragmentationStrategy.POR_ENCABEZADO, target_tokens=500, overlap_tokens=60,
                          min_tokens=80)
            return original(self, project_id, tipo, **kw)

        base.IngestionService.set_fragmentation_policy = politica

    if a.contador != "palabras":
        from domain.ingestion.ports import TokenCounter

        class Contador(TokenCounter):
            def __init__(self, modo):
                self._modo = modo
                self._tok = None
                if modo == "subpalabras":
                    from tokenizers import Tokenizer
                    ruta = next((RAIZ / "data" / "models").glob(
                        "models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q/snapshots/*/tokenizer.json"))
                    self._tok = Tokenizer.from_file(str(ruta))
                    self._tok.no_truncation()  # el archivo trae truncado a 128 para el modelo

            def count_tokens(self, text: str) -> int:
                if self._modo == "x3":
                    return 3 * len(text.split())
                return len(self._tok.encode(text, add_special_tokens=False).ids)

        contador = Contador(a.contador)
        init_original = base.IngestionService.__init__

        def init(self, *args, **kw):
            kw.setdefault("token_counter", contador)
            init_original(self, *args, **kw)

        base.IngestionService.__init__ = init
    if a.documentos:
        base.DOCS = a.documentos.resolve()
    real_requisitos = None
    if a.intenciones == "real":
        # Ronda 105f: intención REAL de AGENTE UDL informada por NEXOM (texto
        # exacto); las demás intenciones siguen siendo las supuestas.
        real_requisitos = (
            "consultar_requisitos_bachillerato",
            "Informar sobre los requisitos generales y documentos necesarios para ingresar al Bachillerato de la "
            "Universidad de León, utilizando exclusivamente información institucional autorizada.",
            ["¿Cuáles son los requisitos para ingresar al bachillerato?", "¿Qué documentos necesito para inscribirme?",
             "¿Qué necesito para entrar a la preparatoria?", "¿Piden certificado de secundaria?",
             "¿Qué papeles debo entregar para ingresar?", "¿Cuáles son los requisitos de admisión?",
             "¿Qué documentos solicitan para nuevo ingreso?", "¿Los requisitos son iguales en ambos planteles?"],
            ["¿Qué materias llevan en quinto semestre?", "¿Cuál es el plan de estudios?",
             "¿Cuánto cuesta la inscripción?", "¿Dónde se encuentra el plantel Hilario Medina?",
             "¿Qué áreas de formación ofrece el bachillerato?", "¿Cuáles son las cualidades de un aspirante?",
             "¿Cuándo comienzan las clases?", "Quiero hablar con un asesor."],
        )
        base.INTENCIONES[:] = [real_requisitos if n == real_requisitos[0] else (n, d, pos, neg)
                               for n, d, pos, neg in base.INTENCIONES]
    if a.intenciones == "hipotesis_info":
        # HIPÓTESIS (Ronda 105e) para reproducir la observación real: la
        # intención de requisitos incluye la palabra «información».
        base.INTENCIONES[:] = [
            (n, ("Consultar información general de los requisitos de ingreso al bachillerato." if n ==
                 "consultar_requisitos_bachillerato" else d), pos, neg)
            for n, d, pos, neg in base.INTENCIONES]
    elif a.intenciones != "r102":
        base.INTENCIONES[:] = [i for i in base.INTENCIONES if i[0] != "consultar_plan_estudios"]
        if a.intenciones == "historico+asesor":
            base.INTENCIONES.append((
                "solicitar_asesor_admisiones", "Solicitar hablar con un asesor de admisiones de la Universidad de León.",
                ["Quiero hablar con un asesor de admisiones", "¿Me pueden comunicar con un asesor?",
                 "Necesito que me atienda una persona de admisiones"],
                ["¿Cuáles son los requisitos de ingreso?"]))
    simuladores, titulo_de = getattr(base.corpus, "__wrapped__", base.corpus)()
    if real_requisitos is not None:
        # Datos opcionales reales (campus, nivel_academico), sin obligatorios. En esta
        # reproducción la variable de plantel se llama "plantel".
        repo_int = simuladores["sin"]._intents
        for it in repo_int.list_for_project(base.P):
            if it.name == real_requisitos[0]:
                repo_int.save(it.model_copy(update={"required_variables": [],
                                                    "optional_variables": ["plantel", "nivel_academico"],
                                                    "priority": 50}))
    if a.listar:
        repo = simuladores["sin"]._rag._hybrid_search._text._chunks
        todos = repo.list_for_project(base.P)
        print(f"fragmentos indexados: {len(todos)} "
              f"(tipos: {sorted({c.chunk_type.value for c in todos})})")
        for c in sorted(todos, key=lambda c: (titulo_de[c.source_id], c.chunk_index)):
            primera = (c.text or "").strip().split("\n", 1)[0][:50]
            print(f"   {titulo_de[c.source_id][:28]:28} #{c.chunk_index:<2} {c.chunk_type.value:6} "
                  f"tokens {c.token_count:4} título={c.section_title!s:12.12} «{primera}»")
    sim = simuladores["sin"]  # r105b con «Automático»: sin reranking, igual en Simulador y Runtime
    rag, P = sim._rag, base.P
    hibrida = rag._hybrid_search
    fuentes = sim._sources.list_for_project(P)
    variables = sim._variables.list_for_project(P)
    intents = sim._intents.list_for_project(P)

    def tipo(chunk) -> str:
        if pr.solo_yaml(chunk.text):
            return "solo-YAML"
        if pr.palabras_de_contenido(chunk.text) < pr.MIN_PALABRAS_CONTENIDO:
            return "solo-encabezado"
        refs, _ = pr.detectar_referencias(chunk.text, chunk.source_id, pr.indice_de_nombres(titulo_de))
        if refs and pr.palabras_sin_yaml(chunk.text) <= pr.MAX_PALABRAS_PUENTE:
            return "puente"
        return "contenido"

    def titulo(chunk, con_y):
        if con_y and not chunk.section_title and pr.solo_yaml(chunk.text):
            return ""
        return affinity_title(chunk.section_title, chunk.text, titulo_de[chunk.source_id])

    def ejecutar(consulta, variante):
        trace = sim.execute(P, consulta, {}, limit=5)
        if trace.action.value != "responder":
            return [], {}, trace, {}
        if not trace.applied_metadata_filters:
            # Sin filtros, r105b no reordena por afinidad: se entrega la búsqueda tal cual
            # (y las variantes, que actúan en ese reordenamiento, tampoco cambian nada).
            return list(trace.search_results), {}, trace, {"texto": trace.search_text}
        permitidas = {s.id: s.title for s in fuentes if sim._source_matches_filters(
            P, s.id, variables, trace.applied_metadata_filters)}
        texto = consulta if "T" in variante else (trace.retrieval_query or consulta)
        pool = rag.search_hybrid(P, texto, limit=20, only_usable_sources=True, source_ids=set(permitidas))
        rango_busqueda = {r.chunk.id: i for i, r in enumerate(pool, 1)}
        sem = {r.chunk.id: i for i, r in enumerate(hibrida._semantic.execute(
            P, texto, limit=40, only_usable_sources=True, source_ids=set(permitidas)), 1)}
        lex = {r.chunk.id: i for i, r in enumerate(hibrida._text.execute(
            P, texto, limit=40, only_usable_sources=True, source_ids=set(permitidas)), 1)}
        enlaces: dict = {}
        if "R" in variante:
            res = pr.resolver_referencias(pool, permitidas)
            pool, enlaces = res.candidatos, res.enlaces
        perfiles = intents
        if "M" in variante:
            # M (Ronda 105d): el enmascarado de valores de catálogo también
            # reconoce el valor dentro de nombres de intención en snake_case
            # ("consultar_requisitos_bachillerato"); hoy no lo hace.
            perfiles = [i.model_copy(update={"name": i.name.replace("_", " ")}) for i in intents]
        intent = next(p_ for p_, i in zip(perfiles, intents, strict=True) if i.name == trace.matched_intent_name)
        afinidad = SectionAffinity(intent, perfiles, consulta, sim._catalog_mention_masker(P))
        titulos = [titulo(r.chunk, "Y" in variante) for r in pool]
        puntajes = [afinidad.score(t) for t in titulos]
        if "V" in variante:
            # V (Ronda 105e): la afinidad suma en proporción a su VALOR
            # (afinidad/61) y no por su puesto; 0 no suma.
            orden_idx = sorted(range(len(puntajes)), key=lambda i: (-(1 / (61 + i) + puntajes[i] / 61), i))
        else:
            orden_idx = combine_with_retrieval(puntajes)
        valores = sorted({round(x, 3) for x in puntajes if x > 0}, reverse=True)
        puesto_af = {v: n + 1 for n, v in enumerate(valores)}
        orden = [pool[i].chunk.id for i in orden_idx]
        if enlaces:
            orden = pr.aplicar_restriccion(orden, enlaces)
        idx = {r.chunk.id: i for i, r in enumerate(pool)}
        detalle = {}
        for pos, cid in enumerate(orden[:8], 1):
            i = idx[cid]
            r = pool[i]
            pa = puesto_af.get(round(puntajes[i], 3))
            detalle[pos] = {
                "fuente": titulo_de[r.chunk.source_id], "titulo_afinidad": titulos[i][:48], "tipo": tipo(r.chunk),
                "puesto_lista": i + 1, "puesto_busqueda": rango_busqueda.get(cid), "semantica": sem.get(cid),
                "textual": lex.get(cid), "afinidad": round(puntajes[i], 2), "puesto_afinidad": pa,
                "rrf": round(1 / (60 + i + 1) + (1 / (60 + pa) if pa else 0), 5),
            }
        por_id = {r.chunk.id: r for r in pool}
        return [por_id[c] for c in orden[:5]], detalle, trace, {"texto": texto, "raices": sorted(raices(texto))}

    resultados: dict = {}
    for variante in a.variantes.split(","):
        posiciones = {}
        decisiones = {}
        for cid, _g, consulta, fuente, verif in ev.CASOS:
            final, detalle, trace, info = ejecutar(consulta, variante)
            pos = next((i for i, r in enumerate(final, 1)
                        if titulo_de[r.chunk.source_id] == fuente and verif in r.chunk.text), None)
            posiciones[cid] = pos
            decisiones[cid] = (trace.matched_intent_name, trace.action.value, round(trace.confidence, 4),
                               dict(trace.applied_metadata_filters))
            if a.detalle and cid in FOCO:
                print(f"\n[{a.compartidos}{' P4' if a.p4 else ''} | {variante}] {cid} {FOCO[cid]}: "
                      f"texto de búsqueda {info.get('texto')!r} → correcto en {pos}")
                for p_, d in detalle.items():
                    print(f"  {p_}. {d['fuente'][:28]:28} {d['tipo']:15} lista#{d['puesto_lista']:<2} "
                          f"búsq#{d['puesto_busqueda']!s:4} sem#{d['semantica']!s:4} tex#{d['textual']!s:4} "
                          f"afin {d['afinidad']:.2f} (#{d['puesto_afinidad']!s:4}) rrf {d['rrf']:.5f} "
                          f"«{d['titulo_afinidad']}»")
        n = len(posiciones)
        mrr = sum(1 / p for p in posiciones.values() if p) / n
        r1 = sum(1 for p in posiciones.values() if p == 1) / n
        clave = (f"{a.compartidos}{'+P4' if a.p4 else ''}{'' if a.contador == 'palabras' else '+' + a.contador}"
                 f"{'' if a.intenciones == 'r102' else '+' + a.intenciones}|{variante}")
        resultados[clave] = {"R@1": round(r1, 3), "MRR": round(mrr, 3), "posiciones": posiciones,
                             "decisiones": decisiones}
        print(f"{clave:32} R@1 {r1:.2f} MRR {mrr:.3f}  " + " ".join(f"{c}={p}" for c, p in posiciones.items()))
    if a.salida:
        previo = json.loads(a.salida.read_text()) if a.salida.exists() else {}
        previo.update(resultados)
        a.salida.write_text(json.dumps(previo, ensure_ascii=False, indent=1))
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
