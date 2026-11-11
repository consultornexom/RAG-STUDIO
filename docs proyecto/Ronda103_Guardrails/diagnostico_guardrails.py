"""Ronda 103 -- DIAGNÓSTICO (sin cambios de código) de la canalización de
«¿Cuál es la mejor pizza de León?» en AGENTE UDL - LOTE01_Bachillerato v1.

Reproduce el motor real (SimulateConversation, el mismo que usa
POST /messages) con:
- los guardrails reportados por NEXOM (texto exacto de condiciones,
  acciones y prioridades);
- las cuatro intenciones activas del proyecto histórico de Bachillerato
  (textos reales), consultar_plan_estudios (supuesta) y
  solicitar_asesor_admisiones (SUPUESTA: no se tiene su texto real);
- los cinco documentos reales de LOTE01 (tests/fixtures/lote01_bachillerato)
  y el modelo de embeddings real (data/models, sin red).

Muestra, por consulta, las tres mejores intenciones (margen, positivo,
negativo), la confianza, las reglas que disparan y la decisión, con la
configuración actual y con la alternativa de configuración propuesta
(agregar "confianza >= 0.45" a canalizar_solicitud_asesor).

Uso (raíz del repositorio):
    python3 "docs proyecto/Ronda103_Guardrails/diagnostico_guardrails.py"
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests" / "integration"))
sys.path.insert(0, str(RAIZ / "tests" / "unit" / "application"))

ASESOR = (
    "solicitar_asesor_admisiones",
    "Solicitar hablar con un asesor de admisiones de la Universidad de León.",
    ["Quiero hablar con un asesor de admisiones", "¿Me pueden comunicar con un asesor?",
     "Necesito que me atienda una persona de admisiones", "¿Puedo hablar con alguien de admisiones?"],
    ["¿Cuáles son los requisitos de ingreso?", "¿Qué materias tiene el bachillerato?"],
)

GUARDRAILS = [
    ("aclarar_baja_confianza", ["confianza < 0.45"], "aclarar", 80),
    ("abstenerse_confianza_insuficiente", ["confianza < 0.20"], "abstenerse", 90),
    ("canalizar_solicitud_asesor", ["intencion = solicitar_asesor_admisiones"], "canalizar", 69),
]
ALTERNATIVA = {"canalizar_solicitud_asesor": ["intencion = solicitar_asesor_admisiones", "confianza >= 0.45"]}

CONSULTAS = [
    ("fuera de alcance", "¿Cuál es la mejor pizza de León?"),
    ("fuera de alcance", "¿Qué clima hará mañana en León?"),
    ("fuera de alcance", "¿Quién ganó el partido del León ayer?"),
    ("fuera de alcance", "Recomiéndame una película"),
    ("asesor explícito", "Quiero hablar con un asesor de admisiones"),
    ("asesor explícito", "¿Me pueden comunicar con alguien de admisiones del bachillerato?"),
    ("asesor explícito", "Necesito hablar con una persona, no con un bot"),
    ("documental", "¿Cuáles son los requisitos para ingresar al Bachillerato de la Universidad de León?"),
    ("documental", "¿Qué áreas se ofrecen en el bachillerato?"),
    ("documental", "¿Qué cualidades debe tener un aspirante al bachillerato?"),
    ("documental", "Dame información del bachillerato del plantel Torres Landa"),
]


def main() -> int:
    import test_ronda102_lote01_simulador as base
    from fakes_conversational import InMemoryChannelingSchemeRepository, InMemoryGuardrailRuleRepository

    from application.conversational.queries.simulate_conversation import SimulateConversation
    from domain.conversational.entities import (
        ChannelingScheme, GuardrailRule, Intent, RuleActionType, RuleCondition, RuleType,
    )

    base.INTENCIONES.append(ASESOR)
    simuladores, _ = base.corpus.__wrapped__() if hasattr(base.corpus, "__wrapped__") else base.corpus()
    sim = simuladores["sin"]
    intents, variables, valores = sim._intents, sim._variables, sim._source_metadata
    # La intención de asesor no exige nivel_academico.
    for it in intents.list_for_project(base.P):
        if it.name == ASESOR[0]:
            intents.save(it.model_copy(update={"required_variables": [], "optional_variables": [],
                                               "fallback_channeling_code": "canalizar_asesor_admisiones"}))
    canal = InMemoryChannelingSchemeRepository()
    canal.save(ChannelingScheme(project_id=base.P, code="canalizar_asesor_admisiones", name="Asesor de admisiones"))

    def construir(reglas: dict[str, list[str]]):
        repo = InMemoryGuardrailRuleRepository()
        for nombre, condiciones, accion, prioridad in GUARDRAILS:
            conds = []
            for texto in reglas.get(nombre, condiciones):
                campo, op, valor = texto.split(" ", 2)
                conds.append(RuleCondition(field=campo, operator=op, value=valor))
            repo.save(GuardrailRule(project_id=base.P, name=nombre, rule_type=RuleType.CANALIZACION,
                                    conditions=conds, action=RuleActionType(accion), priority=prioridad))
        return SimulateConversation(intents, variables, repo, canal, valores, sim._rag,
                                    source_repository=sim._sources, schema_repository=sim._schemas,
                                    catalog_repository=sim._catalogs)

    # 1) Precedencia pura (sin modelos): el contexto exacto del caso de
    #    NEXOM (intención de asesor con confianza 0.206) y uno con
    #    confianza por debajo del umbral de abstención.
    from domain.conversational.rule_evaluation import select_firing_action

    print("Precedencia (domain.conversational.rule_evaluation.select_firing_action):")
    for etiqueta, reglas in (("ACTUAL", {}), ("ALTERNATIVA", ALTERNATIVA)):
        repo = construir(reglas)._guardrails.list_for_project(base.P)
        for confianza in ("0.206", "0.15", "0.60"):
            contexto = {"intencion": ASESOR[0], "confianza": confianza, "nivel_riesgo": "bajo",
                        "variables_faltantes": "0"}
            accion, disparadas = select_firing_action(repo, contexto)
            print(f"  {etiqueta:11} asesor con confianza {confianza}: {[r.name for r in disparadas]} -> {accion.value}")

    actual, alternativa = construir({}), construir(ALTERNATIVA)
    for grupo, consulta in CONSULTAS:
        t = actual.execute(base.P, consulta, {}, limit=5)
        t2 = alternativa.execute(base.P, consulta, {}, limit=5)
        print(f"\n[{grupo}] {consulta}")
        for s in t.intent_scores[:3]:
            print(f"    {s.intent_name:36} margen {s.margin:.3f} (+{s.positive:.3f} −{s.negative:.3f})")
        print(f"  intención {t.matched_intent_name}  confianza {t.confidence:.3f}")
        print(f"  ACTUAL      reglas {t.fired_rules} -> {t.action.value}")
        print(f"  ALTERNATIVA reglas {t2.fired_rules} -> {t2.action.value}")
    _ = Intent
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
