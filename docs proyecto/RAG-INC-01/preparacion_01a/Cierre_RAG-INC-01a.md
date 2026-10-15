# RAG-INC-01a — Cierre formal

Fecha: 2026-10-14 · Rama `rag-inc-01/01a` · Registro autorizado por NEXOM.

## Estado: **RAG-INC-01a = CERRADO**

| Componente | Estado | Commit |
|---|---|---|
| 0021 — identidades persistentes (`knowledge_base_id`, `lineage_id`) | Completado | `a208d8be53d58e45d027c8864308143f3a177bd7` |
| Política de importación `preserve` / `fork` | Completado | `3d508efbc1c1edbabc4fcec53e6596a449c8e284` |
| Detección de colisión de identidad | Completado | `3d508ef…` |
| Bloqueo entre procesos (`<instalación>/.importacion.lock`) | Completado | `3d508ef…` |
| Adaptación mínima de la UI de importación (D-1) | Completado | `3d508ef…` |
| Medición INC01-R1 | Completada | — |

Detalle: `Resultados_0021.md` y `Resultados_Politica_Identidad_01a.md` (riesgos aceptados incluidos).

## INC01-R1 — resuelto en cuanto a decisión

Fuentes heredadas sin `content_hash` (medición final):

| Corpus | Sin `content_hash` |
|---|---|
| A | 1 / 1 |
| B | 5 / 5 |
| C | 25 / 25 |
| D | 0 / 35 |
| **Total** | **31** |

- **Decisión NEXOM:** opción B. Se rellena `content_hash` de las fuentes heredadas antes de emitir cualquier NEXOM Knowledge Package.
- **Mecanismo:** comando/servicio explícito. La migración Alembic 0022 queda descartada.
- **Descartadas:** A (ids dependientes de `updated_at`), C (hash solo al exportar) y D1 (cambiar la fórmula del contrato).
- La fórmula del contrato v1.0.0 no cambia.
- R1 pasa como **precondición técnica de 01b**. Ver `../preparacion_01b/Precondicion_content_hash_01b.md`.
