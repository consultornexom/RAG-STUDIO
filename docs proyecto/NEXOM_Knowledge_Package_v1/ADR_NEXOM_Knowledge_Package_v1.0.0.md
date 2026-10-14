# ADR — NEXOM Knowledge Package v1.0.0

**Estado del contrato:** `ACCEPTED` — `schema_version = 1.0.0`
**Fecha efectiva:** 2026-09-24
**Base:** *Declaración de aceptación del contrato v1.0.0* (revisión 4.1, firmada) y *Ratificación* del 2026-09-24, en `firmados/`
**Resultado de la prueba de interoperabilidad AR-INC-00:** `ACCEPTED WITH OBSERVATIONS` (candidato `v1.0-rc3.2`)

## 1. Relación con el ADR de rc3.2

`ADR_NEXOM_Knowledge_Package_v1.md` (rc3.2) sigue siendo la fundamentación de diseño del contrato: identificadores, canonicalización, sidecars externos, perfiles, capacidades y omisiones, `FormatChecker`, igualdad de conjuntos de archivos, continuidad de `logical_id`, recomputo de `source.id`, validación de `acceptance_cases` y de evidencia. Quedan **sustituidos** su estado ("candidato, no cerrado") y su roadmap: este documento los reemplaza. El paquete `v1.0-rc3.2` se conserva como evidencia de aceptación inmutable (ZIP con SHA-256 `78db21b10c8a12906784e111747bebe304f230abebcecc834eb030e6f3ff81cc`).

## 2. Artefactos normativos

El contrato `v1.0.0` son los 16 artefactos normativos enumerados en `contrato_v1.0.0/SHA256SUMS`: 14 JSON Schemas, `common/id_scheme.py` y `validator/validate_knowledge_package.py`. El archivo `SHA256SUMS` es un inventario de control, no normativo. Todos son byte a byte iguales a los del candidato `v1.0-rc3.2` y se verifican con:

```
cd contrato_v1.0.0 && sha256sum -c SHA256SUMS
```

Los hashes individuales figuran en la sección 4.1 de la Declaración.

## 3. Aclaraciones normativas

Fijan la interpretación de campos existentes. No añaden campos ni cambian schemas, así que no alteran la sección 2 de este ADR.

**Alcance.** Estas reglas describen cómo un consumidor **evalúa** un caso de aceptación al ejecutarlo. El validador de referencia comprueba la estructura y la coherencia del paquete, pero no ejecuta recuperación ni calcula recall, y por tanto no comprueba estas reglas. Por ejemplo, no rechaza un caso `exact` con `minimum_recall` menor que 1.0. Esto es una división de responsabilidades intencional, no una omisión. Si en el futuro se quiere que el validador detecte casos semánticamente mal formados, es un cambio `1.1.0`.

**3.1 Evaluación de un caso de aceptación.** El consumidor recupera `top_k` resultados para `query`, aplica el filtro de acceso de `access_hierarchy.json` para `user_access_level` y, sobre ese resultado:

- `must_not_retrieve` tiene precedencia absoluta: si aparece cualquiera de sus ids, el caso falla, sin importar la política ni el recall.
- `minimum_recall` se aplica solo a `expected_chunk_ids`: el caso exige que la fracción recuperada sea al menos `minimum_recall`. Con `expected_chunk_ids` vacío no se evalúa.
- `expected_source_ids` y `expected_evidence_ids` deben aparecer completos en `contains` y `ranked`.
- `contains` permite resultados adicionales. Con esto se resuelve la precedencia pendiente desde el dictamen sobre rc3.1: `minimum_recall` gobierna la cobertura de chunks y `contains` solo indica que los extras no hacen fallar el caso.
- `exact` exige que el conjunto de resultados sea igual al esperado. `exact` con `minimum_recall` menor que 1.0 es semánticamente mal formado, y el consumidor debe reportarlo así, no como PASS ni como FAIL.
- `ranked` exige que los elementos esperados que aparezcan respeten el orden declarado dentro de `top_k`.

**3.2 Casos con todas las listas esperadas vacías.** Con `exact` significan "ningún resultado tras el filtro de acceso". Siguen siendo válidos en `v1.0.0`, pero su resultado depende del umbral de relevancia del consumidor. Para pruebas de denegación se usa `contains` + `must_not_retrieve`, como en el ejemplo `1.0.0`.

**3.3 Umbrales de relevancia.** `min_score`, `semantic_threshold` y equivalentes pertenecen al consumidor. El informe de aceptación debe registrarlos; el paquete no los transporta.

**3.4 Reutilización de embeddings.** `embedding_spaces.json` describe el espacio del productor. Decidir si se reutilizan los vectores o se reindexa corresponde al consumidor. En `CORE` no viajan vectores.

**3.5 Chunks no indexables.** Un chunk cuyo `chunk_type` no figura en ningún `covers_chunk_types` se conserva e importa, pero no se indexa textualmente (Informe §3).


## 4. Política de cambios a partir de v1.0.0

- **1.0.x**: documentación, erratas y aclaraciones interpretativas que no cambian qué paquetes son válidos. Los artefactos de la sección 2 de este ADR no cambian.
- **1.x.0**: cambios compatibles hacia atrás en este sentido: un consumidor `1.x` sigue aceptando todo paquete `1.0.0` válido. No se promete la compatibilidad inversa. Como los schemas son estrictos (`additionalProperties: false`, enumeraciones cerradas), un consumidor `1.0` puede rechazar un paquete `1.x` que use campos o valores nuevos. Por eso un productor solo debe emitir paquetes `1.x` a consumidores que declaren soportar esa versión. *(Precisión documental 1.0.x del 2026-09-24. El texto firmado de la sección 8 de la Declaración no se modifica; esta es su interpretación vigente.)*
- **2.0.0**: cualquier cambio que invalide paquetes `1.0.0` o cambie la semántica de un campo o de una fórmula de identificador.
- Todo cambio en un artefacto de la sección 2 de este ADR exige versión nueva, actualizar sus hashes y ejecutar la suite negativa. Un cambio `2.0.0` exige además una nueva prueba de interoperabilidad con el Runtime.
- RAG-INC-01 y siguientes deben producir paquetes que el validador `v1.0.0` acepte con 0 errores. Una necesidad que el contrato no cubra se documenta como propuesta de cambio. No se resuelve en el exportador por fuera del contrato.


## 5. Observaciones vigentes

Las observaciones del Informe se registran en la sección 7 de la Declaración. Las que siguen abiertas son:

- **F-1.** Esquema de confianza y firma productivos. Mientras no se resuelva, los paquetes tienen integridad técnica pero no autenticidad del productor, y no deben presentarse como entregas productivas autenticadas.
- **F-2.** Perfiles `AUDIT` y `PREINDEXED`, y recuperación por imagen.
- **F-3.** Criterio de relevancia portable en los casos de aceptación.
- **M-1 y M-2.** Mejoras recomendadas para una versión futura.
