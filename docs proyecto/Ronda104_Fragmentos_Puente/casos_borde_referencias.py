"""Ronda 104b -- casos borde del diseño R (prototipo_referencias.py), sin
modelos: referencias inexistentes, ambiguas, circulares, a fuentes no
permitidas, destinos solo-YAML o solo-encabezado, fragmentos largos que
citan otro documento, documentos con varios fragmentos y garantía de orden
final. Se ejecuta con: python3 casos_borde_referencias.py (sale con código 1
si algún caso falla). Al implementar, estos casos pasan a pruebas unitarias.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prototipo_referencias as pr  # noqa: E402


@dataclass
class C:
    id: str
    source_id: str
    text: str
    section_title: str | None = None
    section_path: list = field(default_factory=list)


@dataclass
class R:
    chunk: C


YAML = "---\nunidad_id: x\nnivel: bachillerato\n---\n"
PUENTE = "## Información compartida\n\nPara evitar duplicación, consultar requisitos_ingreso.md — requisitos de ingreso."
CONTENIDO = "## Contenido\n\n- Acta de nacimiento original.\n- Certificado de secundaria.\n- CURP."
FUENTES = {"plan": "plan_a.md", "req": "requisitos_ingreso.md", "areas": "areas_formacion.md"}

fallos: list[str] = []


def caso(nombre: str, condicion: bool) -> None:
    print(("OK   " if condicion else "FALLA") + " " + nombre)
    if not condicion:
        fallos.append(nombre)


def ids(lista):
    return [r.chunk.id for r in lista]


# 1. Caso base: el destino queda delante del puente.
cands = [R(C("p1", "plan", PUENTE)), R(C("x", "plan", "## Info\n\nTexto general del plan con varias palabras.")),
         R(C("r1", "req", CONTENIDO))]
res = pr.resolver_referencias(cands, FUENTES)
caso("destino insertado antes del puente", ids(res.candidatos)[:2] == ["r1", "p1"] and res.enlaces == {"r1": ["p1"]})
caso("restricción final: destino delante aunque la afinidad lo ponga detrás",
     pr.aplicar_restriccion(["p1", "x", "r1"], res.enlaces) == ["r1", "p1", "x"])
caso("restricción: si el puente no está en el resultado no se mueve nada",
     pr.aplicar_restriccion(["x", "r1"], res.enlaces) == ["x", "r1"])

# 2. Referencia inexistente.
cands = [R(C("p1", "plan", "Consultar no_existe.md para más detalles.")), R(C("r1", "req", CONTENIDO))]
res = pr.resolver_referencias(cands, FUENTES)
caso("referencia a un archivo que no es fuente: sin cambios", ids(res.candidatos) == ["p1", "r1"] and not res.enlaces)

# 3. Referencia ambigua (dos fuentes con el mismo título).
dobles = {**FUENTES, "req2": "requisitos_ingreso.md"}
cands = [R(C("p1", "plan", PUENTE)), R(C("r1", "req", CONTENIDO)), R(C("r2", "req2", CONTENIDO))]
res = pr.resolver_referencias(cands, dobles)
caso("referencia ambigua: no se resuelve y queda en la traza",
     not res.enlaces and res.ambiguas == ["requisitos_ingreso", "requisitos_ingreso.md"])

# 4. Referencias circulares: A remite a B y B remite a A, ambos solo puentes.
circ = {"a": "unidad_a.md", "b": "unidad_b.md"}
cands = [R(C("a1", "a", "Ver unidad_b.md.")), R(C("b1", "b", "Ver unidad_a.md."))]
res = pr.resolver_referencias(cands, circ)
caso("circular entre puentes: un puente nunca es destino, sin bucles",
     not res.enlaces and ids(res.candidatos) == ["a1", "b1"])
cands = [R(C("a1", "a", "Ver unidad_b.md.")), R(C("b1", "b", "Ver unidad_a.md.")),
         R(C("a2", "a", "## Contenido A\n\nTexto propio de la unidad A con suficientes palabras.")),
         R(C("b2", "b", "## Contenido B\n\nTexto propio de la unidad B con suficientes palabras."))]
res = pr.resolver_referencias(cands, circ)
caso("circular con contenido: cada puente trae el contenido del otro, un solo nivel",
     res.enlaces == {"b2": ["a1"], "a2": ["b1"]} and ids(res.candidatos) == ["b2", "a1", "a2", "b1"])

# 5. Fuente referida no permitida (filtros, acceso, vigencia): no está en
#    fuentes_permitidas ni en los candidatos -> no se resuelve.
cands = [R(C("p1", "plan", PUENTE)), R(C("x", "plan", "Otro texto del plan con palabras suficientes."))]
res = pr.resolver_referencias(cands, {"plan": "plan_a.md"})
caso("fuente referida fuera de los filtros: no se incorpora", not res.enlaces)
res = pr.resolver_referencias(cands, FUENTES, modo="busqueda", buscar_en_fuente=lambda sid: [])
caso("modo búsqueda sin resultados permitidos en la fuente referida: no se incorpora", not res.enlaces)

# 6. Destinos sin contenido.
cands = [R(C("p1", "plan", PUENTE)), R(C("ry", "req", YAML)), R(C("rh", "req", "# Requisitos de ingreso")),
         R(C("r1", "req", CONTENIDO))]
res = pr.resolver_referencias(cands, FUENTES)
caso("destino solo-YAML o solo-encabezado: se salta y se toma el siguiente con contenido",
     list(res.enlaces) == ["r1"] and ids(res.candidatos)[0] == "r1")

# 7. Fragmento largo que cita otro documento: no es puente.
largo = "## Plan\n\n" + " ".join(["palabra"] * 90) + " ver requisitos_ingreso.md"
cands = [R(C("l1", "plan", largo)), R(C("r1", "req", CONTENIDO))]
res = pr.resolver_referencias(cands, FUENTES)
caso("fragmento largo que cita otra fuente: no se trata como puente", not res.enlaces)

# 8. Documento con varios fragmentos: hasta MAX_POR_FUENTE destinos.
cands = [R(C("p1", "plan", PUENTE)), R(C("rp", "req", "## Procedencia\n\nDocumento derivado de los dos folletos.")),
         R(C("r1", "req", CONTENIDO))]
pr.MAX_POR_FUENTE = 1
res1 = pr.resolver_referencias(cands, FUENTES)
pr.MAX_POR_FUENTE = 2
res2 = pr.resolver_referencias(cands, FUENTES)
pr.MAX_POR_FUENTE = 1
caso("varios fragmentos, 1 por fuente: solo el mejor ubicado", list(res1.enlaces) == ["rp"])
caso("varios fragmentos, 2 por fuente: ambos delante del puente",
     set(res2.enlaces) == {"rp", "r1"} and ids(res2.candidatos)[:3] == ["rp", "r1", "p1"])

# 9. Mención de la fuente propia o del nombre dentro de otra palabra.
cands = [R(C("r0", "req", "Este archivo requisitos_ingreso.md resume.")),
         R(C("p1", "plan", "Ver mis_requisitos_ingreso.md2 no aplica."))]
res = pr.resolver_referencias(cands, FUENTES)
caso("mención de la propia fuente o dentro de otro nombre: no es referencia", not res.enlaces)

# 10. Tope de destinos por consulta.
muchos = {f"s{i}": f"unidad_{i}.md" for i in range(6)}
muchos["plan"] = "plan_a.md"
texto = "Ver " + ", ".join(f"unidad_{i}.md" for i in range(6))
cands = [R(C("p1", "plan", texto))] + [R(C(f"c{i}", f"s{i}", f"## U{i}\n\nContenido propio número {i} extenso."))
                                        for i in range(6)]
res = pr.resolver_referencias(cands, muchos)
caso(f"tope de {pr.MAX_DESTINOS} destinos por consulta", len(res.enlaces) == pr.MAX_DESTINOS)

print(f"\n{len(fallos)} falla(s)")
raise SystemExit(1 if fallos else 0)
