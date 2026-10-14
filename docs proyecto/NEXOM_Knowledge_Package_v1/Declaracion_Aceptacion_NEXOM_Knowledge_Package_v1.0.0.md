# Declaración de aceptación del contrato — NEXOM Knowledge Package v1.0.0

**Documento:** Declaración formal de estado del contrato de interoperabilidad RAG Studio → NEXOM Agent Runtime
**Estado de este documento:** VERSIÓN FINAL PARA FIRMA, revisión 4.1 (solo documental). Incorpora las decisiones de NEXOM del 23-09-2026 y las correcciones de sus revisiones de las revisiones 2, 3 y 4. Respecto de la revisión 4, su contenido no cambia; solo se actualiza la referencia al alcance anexo. No surte efecto hasta la firma (sección 10).
**Fecha:** 23 de septiembre de 2026
**Base:** Informe de validación de interoperabilidad RAG Studio → NEXOM Agent Runtime, v1.0, septiembre 2026 (en adelante, "el Informe"), emitido sobre el candidato `v1.0-rc3.2`.
**Alcance:** este documento declara el estado del contrato y fija los artefactos que lo componen. No modifica código de RAG Studio ni del Runtime, no genera una `rc3.3` y no altera el paquete auditado.

---

## 1. Declaración

Sujeto a la firma de las partes, se declara:

```
Resultado de la prueba AR-INC-00       = ACCEPTED WITH OBSERVATIONS
Decisión de NEXOM sobre el contrato    = ACCEPTED
schema_version del contrato            = 1.0.0
Candidato validado                     = NEXOM Knowledge Package v1.0-rc3.2
Observaciones contractuales bloqueantes = ninguna
```

Los dos estados no se contradicen. El primero es el resultado literal de la prueba y se conserva sin cambios como antecedente. El segundo es la decisión de NEXOM sobre el contrato, y se apoya en que ninguna observación del Informe acredita una incompatibilidad contractual (sección 3).

El contrato **v1.0.0** queda definido por los artefactos normativos de la sección 4.1, que son byte a byte los del candidato `v1.0-rc3.2`. Las observaciones del Informe se registran en la sección 7 con su responsable y disposición. Ninguna de ellas modifica los schemas, el esquema de identificadores ni el validador de referencia.

## 2. Identificación del artefacto validado

Los identificadores del Informe se verificaron contra la copia del paquete en `docs proyecto/NEXOM_Knowledge_Package_v1/`. NEXOM los verificó además por separado. Coinciden todos:

| Identificador | Valor |
|---|---|
| Paquete | NEXOM Knowledge Package `v1.0-rc3.2` |
| `package_id` | `urn:nexom:package:2aa43944e3b1a44d6bd4b660df460238` |
| `manifest.schema_version` | `1.0.0-rc3.2` |
| `content_digest` | `1690c9d06a7887ed53f3e836f4118dddcb32900031f05c5f06c58e8fb73f1b5b` |
| SHA-256 del ZIP exterior | `78db21b10c8a12906784e111747bebe304f230abebcecc834eb030e6f3ff81cc` |
| Contenido | 4 sources, 6 chunks, 4 evidences, 1 media, 3 acceptance cases |

**Resultados que se apoyan en la firma del Informe.** Las afirmaciones sobre la ejecución en el Runtime no son reproducibles desde RAG Studio y quedan respaldadas por la firma de quien emitió el Informe. Son estas: importación y persistencia, reembedding a 768 dimensiones, índice `READY` y activación, PASS de AC-001/AC-002/AC-003 con `min_score = 0.5926…`, idempotencia, y 826 pruebas aprobadas con el candidato y 0 fallidas. Lo verificado de forma independiente son los hashes de esta sección y de la sección 4.

## 3. Análisis del Informe

La sección 17 del Informe pide separar los hallazgos, indicar si alguna incompatibilidad contractual obliga a modificar `v1.0-rc3.2` y no implementar nada antes de la revisión de NEXOM.

### 3.1 ¿Existe alguna incompatibilidad contractual que obligue a modificar v1.0-rc3.2?

**No.** Ningún hallazgo indica que un schema, una fórmula de identificador o una regla del validador sea incorrecta o insuficiente para el consumidor. Las brechas de integración del Informe (importador, checksums, intents/guardrails, persistencia, fixture) fueron del Runtime y se corrigieron ahí sin cambiar el paquete (Informe, secciones 7 y 14).

### 3.2 Clasificación de hallazgos

**Acciones requeridas en RAG Studio (ninguna es contractual):**

| Id | Acción | Hallazgo que la origina |
|---|---|---|
| A-1 | Corregir la errata de `LEEME.md`, línea 26 ("20 casos negativos" → "19 casos negativos + 1 caso base") en la documentación de `v1.0.0`. | Dictamen final de NEXOM sobre rc3.2 |
| A-2 | Incorporar al ADR de `v1.0.0` las aclaraciones normativas de la sección 6, sin cambiar schemas. | Informe §10 y precedencia pendiente desde el dictamen sobre rc3.1 |
| A-3 | En el nuevo paquete de ejemplo `1.0.0`, expresar AC-003 como `contains` + `must_not_retrieve` (sección 5). | Informe §10: AC-003 dependió de un umbral del consumidor |
| A-4 | Implementar el exportador real (RAG-INC-01) conforme al documento de alcance anexo. | Informe §15; roadmap acordado |

**Mejoras recomendadas para futuras versiones del contrato (no bloquean v1.0.0):**

| Id | Mejora | Hallazgo |
|---|---|---|
| M-1 | Recomendar en la guía del contrato que los casos de denegación usen `contains` + `must_not_retrieve` y no `exact` con listas esperadas vacías. `exact` vacío significa "ningún resultado", y su PASS depende de un umbral de relevancia que el contrato no transporta. | Informe §10: margen de solo 0.0153 entre ruido y señal |
| M-2 | Declarar `normalization` en `embedding_spaces.json` con un valor verificado en lugar de `unknown_not_verified`, cuando RAG-INC-01 lea el proveedor real. | Informe §5; recomendación 6 del §15 |

**Observaciones que corresponden exclusivamente al Runtime:**

| Id | Observación | Referencia |
|---|---|---|
| R-1 | `min_score_ar_inc00 = 0.5926…` es configuración de auditoría del Runtime. No se incorpora al paquete ni como default de RAG Studio. | Informe §10 |
| R-2 | La incompatibilidad `384 (MiniLM) vs 768 (nomic-embed-text)` es la decisión correcta del consumidor. RAG Studio no cambia su modelo por esto. | Informe §5 |
| R-3 | Las brechas de importador, checksums, intents/guardrails, persistencia y fixture fueron del Runtime y ya se corrigieron. | Informe §14 |
| R-4 | El Informe muestra los niveles como `public/internal/confidential/restricted` y el paquete declara `publico/interno/confidencial/restringido`. **Condición de firma** (sección 10): el firmante del Runtime confirma que interpreta el orden y la regla de `access_hierarchy.json` del paquete y que no depende de una tabla fija inglés/español. | Informe §9 |

**Asuntos diferidos a una especificación conjunta RAG Studio + Runtime:**

| Id | Asunto | Referencia |
|---|---|---|
| F-1 | Esquema de confianza y firma para producción (almacén de claves, emisión, rotación y revocación de `key_id`). Hoy `signer_trusted_for_production = False` con clave DEMO. Mientras F-1 no esté resuelto, los paquetes tienen integridad técnica (checksums y `content_digest`) pero no autenticidad del productor, porque cualquiera que modifique un paquete puede recalcular esos valores. **La aceptación automática de paquetes en producción queda condicionada a F-1.** | Informe §11; recomendación 9 del §15 |
| F-2 | Perfiles `AUDIT` y `PREINDEXED`, y recuperación por imagen. | ADR v1.0-rc3.2; Informe §3 |
| F-3 | Si los casos de aceptación deben transportar un criterio de relevancia portable. Se recomienda no hacerlo mientras no se hayan evaluado varios modelos de embeddings: un umbral absoluto no se transfiere de un espacio vectorial a otro. | Informe §10 |

## 4. Artefactos del contrato v1.0.0

### 4.1 Artefactos normativos

El contrato `v1.0.0` son exactamente estos 16 archivos, con estos SHA-256. Cualquier cambio en alguno de ellos produce una versión nueva del contrato (sección 8).

| Artefacto | SHA-256 |
|---|---|
| `schemas/acceptance_case.schema.json` | `7cb0cf09e1b153c895bf3e5130713a7ca1588afa475d0f6d499eab4110a27581` |
| `schemas/access_hierarchy.schema.json` | `92e2c6ac9eb3b33527e4728447ad1c0bc9b882913d0b26c96ec63f62fd4a4b25` |
| `schemas/checksums.schema.json` | `bef9d65d5c210f72a5fe04daa8a5af0d7ec378551e22f9d5d698be7b7d282c46` |
| `schemas/chunk.schema.json` | `169d8f6d05dad78624ec8f0aa06276022b6aa83588c76922a775ce7ccd788999` |
| `schemas/conversational_bundle.schema.json` | `d72f8ff680d4895d5628bf4b9a58980ef222b521196f284ebfdc00561f0e5ef5` |
| `schemas/embedding_spaces.schema.json` | `b9468913bb640f28a284d99eb17a36e1c704aecb304679fa9e44186f2f04a753` |
| `schemas/evidence.schema.json` | `043ec0dd5448bd1dd3229dfcb72002cb01704d31f890ca2651ee70bda9569b00` |
| `schemas/indexes.schema.json` | `d981e3e622d641965c15997e2e0f78165a1ae099b065d7849c3e419235b43ac0` |
| `schemas/manifest.schema.json` | `46dee8ed56f809f9e5acda005a259a53a9d2af74561996c3c74691683913c463` |
| `schemas/media.schema.json` | `c3ed9324203bbc2147ad342f78886c17d6af4f5991f7d8aec7caa9a6b57ec9fc` |
| `schemas/metadata_schema.schema.json` | `c443b7bcc26356a4a7daf58769cb71049fe284f77b80fe0af38e7c442266f7e1` |
| `schemas/signature.schema.json` | `bb583efda303eb2b81d43ebc0c83710bcf6bba9485c1a7cb6acc1dd3bc8a55f1` |
| `schemas/source.schema.json` | `8a61ecce31d1fc2207a342e7a9c8dabfb3970f324f2c5ebb51891b2ec087cd90` |
| `schemas/source_metadata.schema.json` | `4b9bcbf3242d7e701595e377cd41f05a3a67657445acf2cf5e7988276832fde3` |
| `common/id_scheme.py` | `559847df560b8033b20a4e797ca32448320eef8d84f81cb654bcad6c1a942ba8` |
| `validator/validate_knowledge_package.py` | `96f18a4fa5105e94dae9d894cd6f6b63ad1a035d747cfff2568af227af9eef74` |

### 4.2 Artefactos de reproducibilidad y QA (no normativos)

No forman parte del contrato: cambiarlos no genera una versión nueva. Se versionan y se registran con hash para que cualquiera pueda reproducir la validación en las mismas condiciones.

| Artefacto | SHA-256 (estado rc3.2) |
|---|---|
| `requirements.lock.txt` | `c9f8bb792efb25272fa6f6eeef41b426830b84704f3a9237fc087bbb3ac7594d` |
| `validator/test_negative_cases.py` | `b0eeec1e217fc402bb30f2fb816364a88d18d4861eff90736a832a701c54380a` |

`requirements.lock.txt` fija las dependencias del validador: `jsonschema==4.26.0`, `rfc3339-validator==0.1.4`, `rfc8785==0.1.4` y `cryptography==50.0.1`. `validator/test_negative_cases.py` es la suite negativa automatizada (19 casos negativos + caso base).

`generate_example.py` y el paquete de ejemplo tampoco son normativos. El generador cambia al producir el ejemplo `1.0.0` (sección 5), por lo que su hash no se fija aquí.

### 4.3 Evidencia de aceptación

El paquete `v1.0-rc3.2` (ZIP con SHA-256 `78db21b1…81cc`, `content_digest` `1690c9d0…1b5b`) se archiva como **evidencia de aceptación inmutable**. No se regenera, no se reetiqueta y no se corrige, ni siquiera su AC-003.

## 5. Publicación de v1.0.0

`manifest.schema.json` no restringe el valor de `schema_version` y el validador no lo compara contra una lista. Por eso publicar `v1.0.0` no requiere tocar ningún artefacto normativo. El procedimiento es:

1. Publicar los 16 artefactos de la sección 4.1 sin modificación como contrato `v1.0.0`.
2. Archivar `rc3.2` según la sección 4.3.
3. Actualizar solo la documentación: ADR `v1.0.0` (estado `ACCEPTED` y aclaraciones de la sección 6) y `LEEME.md` (errata A-1).
4. Generar un nuevo paquete de ejemplo `1.0.0` que difiere del auditado en tres cosas:
   - la etiqueta de versión (`schema_version = "1.0.0"`, `exporter_version`, nombres de sidecars, `key_id` y `signer` alineados);
   - AC-003 en su forma correcta:
     ```json
     {
       "case_id": "AC-003-denegacion-por-acceso",
       "match_policy": "contains",
       "expected_source_ids": [],
       "expected_chunk_ids": [],
       "expected_evidence_ids": [],
       "must_not_retrieve": ["<source_confidencial>", "<chunk_confidencial>"]
     }
     ```
     Así se prueba exactamente la propiedad que importa, no recuperar contenido prohibido, sin depender de que un umbral elimine resultados públicos poco relevantes;
   - en consecuencia, nuevos `checksums.json`, firma DEMO y `content_digest`.
5. Verificar el ejemplo `1.0.0` con: validador de referencia con 0 errores (directorio y ZIP), suite negativa 20/20 e importación de humo en el Runtime.
6. No se repite AR-INC-00: el contrato normativo es idéntico al validado y el ejemplo no es normativo.

Ninguno de estos pasos se ejecuta antes de la firma.

## 6. Aclaraciones normativas incorporadas a v1.0.0

Fijan la interpretación de campos existentes. No añaden campos ni cambian schemas, así que no alteran la sección 4.1.

**Alcance.** Estas reglas describen cómo un consumidor **evalúa** un caso de aceptación al ejecutarlo. El validador de referencia comprueba la estructura y la coherencia del paquete, pero no ejecuta recuperación ni calcula recall, y por tanto no comprueba estas reglas. Por ejemplo, no rechaza un caso `exact` con `minimum_recall` menor que 1.0. Esto es una división de responsabilidades intencional, no una omisión. Si en el futuro se quiere que el validador detecte casos semánticamente mal formados, es un cambio `1.1.0`.

**6.1 Evaluación de un caso de aceptación.** El consumidor recupera `top_k` resultados para `query`, aplica el filtro de acceso de `access_hierarchy.json` para `user_access_level` y, sobre ese resultado:

- `must_not_retrieve` tiene precedencia absoluta: si aparece cualquiera de sus ids, el caso falla, sin importar la política ni el recall.
- `minimum_recall` se aplica solo a `expected_chunk_ids`: el caso exige que la fracción recuperada sea al menos `minimum_recall`. Con `expected_chunk_ids` vacío no se evalúa.
- `expected_source_ids` y `expected_evidence_ids` deben aparecer completos en `contains` y `ranked`.
- `contains` permite resultados adicionales. Con esto se resuelve la precedencia pendiente desde el dictamen sobre rc3.1: `minimum_recall` gobierna la cobertura de chunks y `contains` solo indica que los extras no hacen fallar el caso.
- `exact` exige que el conjunto de resultados sea igual al esperado. `exact` con `minimum_recall` menor que 1.0 es semánticamente mal formado, y el consumidor debe reportarlo así, no como PASS ni como FAIL.
- `ranked` exige que los elementos esperados que aparezcan respeten el orden declarado dentro de `top_k`.

**6.2 Casos con todas las listas esperadas vacías.** Con `exact` significan "ningún resultado tras el filtro de acceso". Siguen siendo válidos en `v1.0.0`, pero su resultado depende del umbral de relevancia del consumidor. Para pruebas de denegación se usa `contains` + `must_not_retrieve`, como en el ejemplo `1.0.0` (sección 5).

**6.3 Umbrales de relevancia.** `min_score`, `semantic_threshold` y equivalentes pertenecen al consumidor. El informe de aceptación debe registrarlos; el paquete no los transporta.

**6.4 Reutilización de embeddings.** `embedding_spaces.json` describe el espacio del productor. Decidir si se reutilizan los vectores o se reindexa corresponde al consumidor. En `CORE` no viajan vectores.

**6.5 Chunks no indexables.** Un chunk cuyo `chunk_type` no figura en ningún `covers_chunk_types` se conserva e importa, pero no se indexa textualmente (Informe §3).

## 7. Registro de observaciones

| Id | Observación | Responsable | Disposición |
|---|---|---|---|
| O-1 | Errata en `LEEME.md`, línea 26 | RAG Studio | Se corrige en la documentación `v1.0.0` (A-1) |
| O-2 | Precedencia `contains` / `minimum_recall` | RAG Studio | Resuelta por la aclaración 6.1 (A-2) |
| O-3 | AC-003 dependió de un umbral del consumidor | RAG Studio | Se corrige en el ejemplo `1.0.0` (A-3); `rc3.2` queda intacto |
| O-4 | `min_score` de auditoría | Runtime | Fuera del contrato (R-1, aclaración 6.3) |
| O-5 | Espacios de embeddings incompatibles | Runtime | Comportamiento esperado (R-2, aclaración 6.4) |
| O-6 | Clave de firma DEMO | Conjunto | Diferido a especificación conjunta (F-1) |
| O-7 | Etiquetas de acceso en inglés en el Runtime | Runtime | Condición de firma: confirmación del Runtime (R-4, sección 10) |
| O-8 | Chunk de imagen no indexado | Conjunto | Conforme (aclaración 6.5); recuperación visual diferida (F-2) |

## 8. Política de cambios a partir de v1.0.0

- **1.0.x**: documentación, erratas y aclaraciones interpretativas que no cambian qué paquetes son válidos. Los artefactos de la sección 4.1 no cambian.
- **1.x.0**: cambios compatibles hacia atrás, como campos opcionales nuevos o valores de enumeración nuevos que un consumidor `1.0` pueda ignorar. Todo paquete `1.0.0` válido sigue siendo válido.
- **2.0.0**: cualquier cambio que invalide paquetes `1.0.0` o cambie la semántica de un campo o de una fórmula de identificador.
- Todo cambio en un artefacto de la sección 4.1 exige versión nueva, actualizar sus hashes y ejecutar la suite negativa. Un cambio `2.0.0` exige además una nueva prueba de interoperabilidad con el Runtime.
- RAG-INC-01 y siguientes deben producir paquetes que el validador `v1.0.0` acepte con 0 errores. Una necesidad que el contrato no cubra se documenta como propuesta de cambio. No se resuelve en el exportador por fuera del contrato.

## 9. Decisiones adoptadas

Recomendadas por NEXOM el 23-09-2026. Entran en vigor con la firma.

| Id | Decisión | Resolución |
|---|---|---|
| CON-D1 | Estado del contrato | `ACCEPTED`. Se conserva literalmente el resultado `ACCEPTED WITH OBSERVATIONS` de AR-INC-00 como antecedente (sección 1) |
| CON-D2 | Publicación de `v1.0.0` | Procedimiento de la sección 5, con `rc3.2` inmutable y AC-003 corregido solo en el ejemplo `1.0.0` |
| CON-D3 | Aclaraciones normativas | Aprobadas (sección 6) |
| CON-D4 | Autorizar RAG-INC-01 | Aprobado con el alcance del documento anexo, revisión 4.1 |

## 10. Firmas y secuencia posterior

| Rol | Nombre | Firma | Fecha |
|---|---|---|---|
| NEXOM — responsable del contrato | | | |
| NEXOM Agent Runtime — responsable de AR-INC-00 | | | |
| RAG Studio — responsable técnico | | | |

**Condiciones de firma:**

- **Jerarquía de acceso (R-4).** Con su firma, el responsable del Runtime confirma que el importador interpreta el orden y la regla de `access_hierarchy.json` declarados por cada paquete, y que no depende de una tabla fija de traducción inglés/español. Sin esta confirmación, el Runtime no firma.
- **Estado productivo (F-1).** Firmar declara aceptado el contrato y habilita la interoperabilidad técnica. No convierte los paquetes en entregas autenticadas para producción: esa condición queda sujeta a F-1.

Con la firma conjunta de esta declaración y del Alcance de RAG-INC-01:

1. se publican los 16 artefactos de la sección 4.1 como contrato `v1.0.0`;
2. se archiva `rc3.2` como evidencia de aceptación;
3. se genera el ejemplo `1.0.0` con AC-003 corregido;
4. se ejecutan el validador, la suite 20/20 y la importación de humo;
5. se inicia RAG-INC-01 por el hito 01a (migración `0021`), solo sobre copias y respaldos;
6. el hito 01b no comienza hasta que NEXOM apruebe formalmente 01a (migración, detección de colisiones, `preserve` y `fork`);
7. los intercambios productivos autenticados quedan condicionados a F-1, cuya especificación conjunta se inicia en paralelo a RAG-INC-01 para que no se convierta después en el siguiente bloqueo.
