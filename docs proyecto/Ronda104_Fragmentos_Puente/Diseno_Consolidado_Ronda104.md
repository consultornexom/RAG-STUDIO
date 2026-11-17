# Ronda 104b: diseño consolidado (Y, R, reranking y trazabilidad)

**Estado**
- No se modificó el motor ni se publicó nada.
- El commit `b260e6d` contiene solo `docs proyecto/Ronda104_Fragmentos_Puente/` (seis archivos de diagnóstico y medición, verificado con `git show --stat`).
- Esta ronda agrega, en la misma carpeta, solo herramientas de medición y este documento.

**Separación de resultados (pedida por NEXOM)**

| Origen | Qué se sabe | Fuente |
|---|---|---|
| **Incidente real** (v2, trace `493c8033`) | consulta, acción, intención 0.887, ids de los dos fragmentos puente y del fragmento con los requisitos (fuera del top 5) | informe de NEXOM |
| **Reproducción con supuestos** | todo lo medido en este documento | los cinco archivos reales de LOTE01, los modelos reales y el motor real; intenciones, metadatos y políticas supuestas (Ronda 102); dos variantes de fragmentación de los documentos compartidos |

Ninguna cifra de este documento proviene del incidente real.

---

## 1. Reproducibilidad del incidente original

### 1.1 Qué no se puede saber hoy desde fuera

- **El Runtime no informa:**
  - la versión del código: `/health` devuelve solo estado, proyectos, modo, versión de instantánea y perfil de embeddings;
  - si aplicó reranking;
  - con qué texto buscó.
- **Lo que guarda `runtime.db` (`conversation_log`) por turno:** mensaje, intención, confianza, acción, `source_ids` (sin ids de fragmento ni orden), latencia y `trace_id`.
- **La instantánea** (`snapshot_identity.json`) identifica el contenido (`content_fingerprint`) y el modelo de embeddings, pero no el código que la sirve.

### 1.2 Qué recuperar del entorno de la v2

| # | Evidencia | Cómo obtenerla | Qué permite saber |
|---|---|---|---|
| E1 | Respuesta JSON completa de `/messages` tal como la recibió Testing Agent (`sources[]` con `chunk_id` y `score`, `trace_id`, `snapshot_version`) | registro de Testing Agent | orden exacto observado; **si hubo reranking**: los puntajes de la fusión RRF están entre 0 y ≈0.05; los del cross-encoder son logits (p. ej. −3.6, +4.1) |
| E2 | Fila del trace en `runtime.db` | `sqlite3 runtime.db "select * from conversation_log where trace_id='493c8033-…'"` (ruta: `RAGSTUDIO_RUNTIME_DB_PATH` o la predeterminada en `RAGSTUDIO_HOME`) | mensaje exacto, `conversation_id`, fecha, latencia, fuentes |
| E3 | Solicitud enviada: `variables` y credencial usada (token de widget o clave operativa) | registro de Testing Agent | variables explícitas; nivel de acceso del canal (cambia las fuentes permitidas) |
| E4 | Versión del código del Runtime | en la instalación del Runtime: `git rev-parse HEAD` y `git status --short`, o el nombre y SHA-256 del ZIP de código desplegado; `pip freeze` (fastembed, onnxruntime, qdrant-client) | commit que generó el trace; versiones de las bibliotecas de inferencia |
| E5 | Variables de entorno del proceso | `RAGSTUDIO_SNAPSHOT_DIR`, `RAGSTUDIO_SNAPSHOT_VERSION`, `RAGSTUDIO_HOME`, `RAGSTUDIO_EMBEDDING_PROFILE` | instantánea y perfil realmente servidos |
| E6 | La instantánea servida: carpeta o paquete de entrega `.zip`, **copia previa a que el Runtime la abra** | — | contenido exacto: `project.db` y el índice |
| E7 | Informe de `inspeccionar_instantanea.py <E6> --chunks 428a1151-…,59baa137-…,8fe5e2de-…` (solo lectura) | herramienta incluida | revisión de esquema (0023 = código anterior a la Ronda 102; 0024 = Ronda 102 o posterior), si existe `project.agent_reranking`, **estrategia de fragmentación efectiva por fuente** (políticas y última política aplicada por el pipeline), fragmentos por fuente, fragmentos solo-YAML y detalle de los tres fragmentos del trace |

**Advertencias:**
- El Runtime aplica migraciones al abrir `project.db`. La revisión de esquema de una copia ya servida refleja el código más nuevo que la abrió, no el que la publicó. Para saber con qué código se publicó, debe inspeccionarse el paquete original.
- **Estrategia de los tres documentos compartidos (punto 1 de NEXOM):** E7 la da sin ambigüedad. `documento_completo` deja un solo fragmento por fuente, sin título de sección; `por_encabezado` deja varios, con títulos «Ámbito de aplicación», «Contenido», «Procedencia».

### 1.3 Procedimiento de reproducción exacta (cuando se tengan E1–E6)

1. Copiar la instantánea (E6) a un directorio de trabajo; dos copias, una por versión candidata.
2. Para cada versión candidata del código, levantar el Runtime fijado a esa copia (`RAGSTUDIO_SNAPSHOT_DIR`) con las mismas versiones de bibliotecas (E4) y el mismo perfil (E5):
   - `af7c123`, Ronda 101, anterior a la Ronda 102;
   - `3621dd5`, Ronda 102;
   - el commit indicado en E4, si es otro.
3. Enviar la misma solicitud (E3) y comparar con E1 la lista ordenada de `chunk_id` y los puntajes.
4. **Criterio:** la versión cuyo orden y puntajes coincidan es la que generó el trace. Los puntajes pueden variar en el último decimal entre CPU distintas, así que se compara el orden y los puntajes redondeados a 3 decimales. Un empate exacto podría ordenarse distinto: se revisa a mano.
5. Registrar el resultado como «reproducción exacta»: separado de la reproducción con supuestos, con E1–E7 como anexos.

**Hipótesis por verificar** (de la reproducción con supuestos, no confirmada): el orden observado coincide con el código anterior a la Ronda 102 sin reranking y con los compartidos como `documento_completo`.

---

## 2. Corrección Y: fragmentos solo-metadatos

**Problema.** La corrección C2 de la Ronda 102 da a un fragmento sin título de sección el título de la fuente. El fragmento que solo contiene el encabezado YAML de un documento (`---` … `---`) no tiene contenido, pero hereda un título afín a la intención («requisitos_ingreso») y entra al top 5. En la reproducción `por_encabezado`, hasta 12 apariciones en los top 5 de las 14 consultas.

**Comportamiento esperado:**
- **Afinidad 0.** Un fragmento sin `section_title` y sin texto fuera del bloque YAML inicial («solo-YAML») tiene título de afinidad vacío.
- **Sigue en la búsqueda.** Se conserva en el índice y en la búsqueda: no se borra ni se filtra. Si la búsqueda lo pone arriba, sigue arriba; solo pierde el impulso de afinidad.
- **No es destino de R** (ver 3.3).

**Implementación:**
- `domain/conversational/section_affinity.py::affinity_title`: si el texto sin YAML no tiene palabras, devuelve `""` antes de recurrir al título de la fuente.
- Utilidad pública `solo_metadatos(texto)` en el mismo módulo, reutilizada por R.

**Medición:**
- **Y sola:** reduce los fragmentos solo-YAML en el top 5 (con `por_encabezado`, de 12 a 3–4).
- **Costo de Y sola en `documento_completo` sin reranking:** R3 baja de 1.º a 2.º.
- **Y con R:** no hay ninguna pérdida (sección 5).

---

## 3. Corrección R: resolución de referencias entre fuentes

### 3.1 Dónde se aplica

**Punto de aplicación:**
- Dentro de `SimulateConversation._search_and_filter`, que es el mismo camino del Simulador y de `POST /messages`.
- **Después** de la búsqueda (con sus filtros de metadatos, fuentes utilizables y nivel de acceso) y **antes** de la afinidad.
- En la rama con filtros, sobre el pool de candidatos (20).
- En la rama sin filtros, sobre la lista de resultados de la misma búsqueda, pedida con el mismo tamaño de pool para que el comportamiento sea igual.

**Dónde no se aplica:** en Búsqueda RAG del Laboratorio, que sigue mostrando la recuperación pura. Ni en la vía estructurada.

### 3.2 Detección de referencias (sin reglas por proyecto)

- **Universo de nombres.** Los títulos de las **fuentes permitidas para esta consulta**: el mismo conjunto que la búsqueda ya calculó por filtros. Las fuentes fuera de filtros no se consideran nunca.
- **Formas de cada título:**
  - el título completo con extensión («requisitos_ingreso.md»);
  - su raíz sin extensión, solo si parece un identificador: sin espacios, con `_` o `-`, ≥ 6 caracteres («requisitos_ingreso»).

  Un título común sin forma de identificador («Reglamento») solo cuenta con su extensión, para no confundirlo con texto normal.
- **Coincidencia.** Sin distinguir mayúsculas, con límites de palabra («mis_requisitos_ingreso.md2» no cuenta). Fuera del encabezado YAML.
- **Mención de la propia fuente:** se ignora.
- **Nombre que corresponde a más de una fuente** (títulos duplicados): **ambiguo**. No se resuelve y queda en la traza (`referencias_ambiguas`).
- **Nombre de un archivo que no es fuente del proyecto** (p. ej. los PDF originales citados en «Procedencia»): no hace nada.

### 3.3 Puentes y destinos

- **Puente.** Candidato con ≤ 80 palabras fuera del YAML (`MAX_PALABRAS_PUENTE`) que remite al menos a una fuente. Un fragmento más largo que cita otro documento tiene contenido propio y no se toca.
  - En LOTE01 los puentes tienen 50 palabras.
  - Las secciones de contenido de los planes tienen 20–34, pero no citan fuentes.
- **Destino.** Para cada fuente referida, los **mejores candidatos de esa fuente que ya están en el pool**: máximo `MAX_POR_FUENTE` = 2 y `MAX_DESTINOS` = 5 por consulta. Cada uno debe:
  - tener contenido: ≥ 5 palabras fuera del YAML y de las líneas de encabezado (excluye solo-YAML y solo-encabezado);
  - no ser a su vez un puente.
- **Por qué los destinos salen del pool y no de una búsqueda nueva (modo «pool»):**
  - los destinos cumplen exactamente los mismos filtros, vigencia, validación y nivel de acceso que la búsqueda original, porque provienen de ella;
  - no se agregan fragmentos irrelevantes: si el documento referido no tiene ningún fragmento entre los candidatos, no se trae nada;
  - no hay costo adicional. El modo «búsqueda» (buscar dentro de la fuente referida) se midió: mismos resultados y hasta 200 ms adicionales con reranking. Se descarta.
- **Sin recursión ni ciclos.**
  - Solo se examinan los candidatos originales; los destinos no se examinan a su vez.
  - Un puente nunca es destino. Así, A→B→A no produce expansión alguna.
  - Los topes acotan el total.

### 3.4 Orden

1. **Inserción.** Cada destino se inserta en la lista de la búsqueda **inmediatamente antes de su puente**: hereda su puesto. Si ya estaba antes, no se mueve.
2. **Afinidad.** Se aplica la afinidad combinada por RRF (Ronda 102), como hoy.
3. **Restricción final.** Sobre la lista completa, antes de recortar al top `limit`: cada destino queda delante del **primero** de sus puentes. Así, si un puente entra en el resultado, su destino también, y antes que él.
4. **Recorte** al top `limit`.

### 3.5 Trazabilidad

- **`SemanticSearchResult`:** campo nuevo `referenced_from: list[{chunk_id, source_id}]`, vacío si no aplica.
- **`ResultOrderingView` (Simulador):**
  - `via_reference_from` (chunk y fuente del puente);
  - `reference_bridge` (True si el fragmento es puente y su destino está delante).
- **`SimulationTrace`:** `references_resolved` (pares destino→puente) y `ambiguous_references`.
- **Reporte del Simulador:** «traído por referencia desde «Información compartida…» (bachillerato_torres_landa.md)».
- **`/messages`:** `SourceSnippet.referenced_from_chunk_id` (aditivo).
- **`runtime.db`:** ver sección 5.

### 3.6 Activación por etapas

- **Ajuste por proyecto:** «Resolver referencias entre fuentes», con migración aditiva de la tabla `project`, igual que `agent_reranking`.
- **Predeterminado desactivado en la etapa 2a**, para validarlo con la v2 real sin cambiar otros proyectos.
- **Cambio de predeterminado (etapa 2b):** pasa a activado solo si NEXOM lo autoriza.

### 3.7 Limitación conocida

R ordena bien **si el destino correcto está entre los candidatos**. Si la fuente referida está fragmentada por encabezado y la búsqueda prefiere otra sección de esa fuente, puede elegirse esa.
- **Ejemplo:** con reranking, «Procedencia» queda por delante de «Contenido» para «¿qué documentos necesito?».
- **Mitigación:** se toman 2 por fuente (en la medición, R2 pasa de fuera del top 5 a 2.º).
- **Sin cubrir:** la brecha de vocabulario de fondo («documentos» frente a «acta, certificado, CURP»), que es también editorial (Ronda 104).

---

## 4. Reranking: alternativa A (Runtime con reranking) frente a B (sin reranking por defecto en ambos)

**Situación actual.** El Simulador de escritorio aplica el cross-encoder por defecto (ajuste «Automático» = si hay modelo). El Runtime nunca lo aplica: `runtime_context.py` construye `RagService` sin reranker. **Hoy la configuración efectiva es distinta entre ambos sin que se vea.**

**Mediciones** (`medicion_reranking.py`, sandbox de 2 vCPU sin GPU; vale para comparar A con B en la misma máquina, no como cifra de producción):

| Criterio | A: reranking también en el Runtime | B: sin reranking por defecto en ambos |
|---|---|---|
| Calidad: código actual, compartidos `documento_completo` (14 consultas, MRR) | 1.000 | 0.952 (R2 en 3.º) |
| Calidad: código actual, `por_encabezado` | 0.729 | 0.729 |
| Calidad: con Y + R (propuesta), `documento_completo` | 1.000 | 1.000 |
| Calidad: con Y + R, `por_encabezado` | 0.917 (R2 2.º, S1 3.º) | 0.952 (R2 1.º, S1 3.º) |
| Latencia por consulta (Simulador completo) | p50 2 271 ms, p95 4 189 ms | p50 39 ms, p95 53 ms |
| Costo marginal del reranker (40 candidatos largos) | ≈2.6 s en este equipo | 0 |
| Recursos | +92 MB de modelo en disco, ≈+118 MB de memoria residente, 0.34 s de carga | — |
| Despliegue | el modelo debe estar en `RAGSTUDIO_HOME/models` del Runtime (descarga la primera vez o aprovisionamiento previo en instalaciones sin red); el paquete de entrega crece | sin cambios |
| Reproducibilidad | depende de un segundo modelo (versión, CPU); puntajes no comparables con RRF | un solo modelo (embeddings); orden determinista por RRF + afinidad + R |
| Idioma | `ms-marco-MiniLM-L-6-v2` está entrenado en inglés; en las Rondas 91, 101 y 104 empeoró o empató casos en español | — |

**Antecedente.** En la Ronda 40, el consultor midió en su propio equipo +90.6 ms de p50 por el reranker. La diferencia con este sandbox (≈+2.2 s) muestra que la latencia de A depende mucho del hardware. Habría que medirla en el servidor del Runtime antes de elegir A.

**Recomendación técnica** (sin cambiar valores por defecto todavía, como pide NEXOM):
- **Alternativa B.** Con Y + R la calidad es igual o mejor sin reranking. Elimina un modelo en inglés, la latencia y la diferencia entre entornos.
- **Reranking como opción explícita por proyecto («Activado»).** Si un proyecto lo activa:
  - el Runtime debe cargar el modelo;
  - si no lo tiene, debe fallar al arrancar con un mensaje claro, en lugar de omitirlo en silencio.
- **Hasta que NEXOM decida, solo trazabilidad.** Se implementa la sección 5, que hace visible y verificable la diferencia actual: el Simulador mostrará «reranking aplicado» y el Runtime «no aplicado». El valor por defecto no cambia.
- **Corrección documental pendiente:** la nota de la Ronda 46 en el Manual (8.5) y la descripción de la Ronda 102 afirman que el Runtime aplica reranking si hay modelo, y eso no es así. Se propone corregirlas en la etapa 0.

---

## 5. Trazabilidad de ejecución

**Datos de ejecución (un solo objeto, igual en todas las superficies):**

| Campo | Contenido | Origen |
|---|---|---|
| `code_version` | versión de RAG Studio (`pyproject`) | paquete |
| `code_commit` | commit y marca `dirty` si hay cambios locales | `build_info.json` generado al empaquetar; si no existe, `git rev-parse` al arrancar; si tampoco, «desconocido» |
| `snapshot_version`, `snapshot_fingerprint` | versión y `content_fingerprint` de `snapshot_identity.json` | instantánea |
| `index` | proveedor, modelo y dimensiones de embeddings, puntos indexados (`IndexInfo`) y la huella anterior como identificador del índice | instantánea |
| `retrieval_pipeline` | identificador de la versión del procedimiento de recuperación (p. ej. `r102`, `r104-y`, `r104-yr`); cambia cada vez que una ronda altera el orden | constante en el código |
| `reranking` | ajuste del proyecto, si hay modelo disponible, si se aplicó y qué modelo | Ronda 102 + Runtime |
| `reference_resolution` | ajuste y referencias resueltas o ambiguas | R |

**Por superficie:**
- **`/health`** (público hoy): `code_version`, `code_commit`, `retrieval_pipeline`, reranking disponible y modelo, y, para la instantánea fija, `snapshot_fingerprint` e `index`.
  - El commit no es un secreto, pero si NEXOM prefiere no exponerlo sin autenticación, puede moverse a un `/health/details` protegido con la clave operativa.
- **`/messages`:** objeto `execution` (aditivo) con todo lo anterior, más `retrieval_query` y `applied_filters`.
  - En cada `SourceSnippet`, aditivos: `retrieval_rank`, `affinity`, `referenced_from_chunk_id`.
  - Testing Agent puede ignorarlos sin cambios.
- **`runtime.db` (`conversation_log`):** columnas aditivas, con el mismo patrón de las Rondas 19 y 93 (`_ensure_*_columns`); las filas anteriores quedan en NULL:
  - `code_commit`, `retrieval_pipeline`, `snapshot_fingerprint`;
  - `reranking_applied`, `reranking_model`, `retrieval_query`;
  - `chunk_ids` (JSON ordenado).

  Con esto, un `trace_id` basta para saber qué configuración se usó.
- **Simulador:** el reporte agrega al final «RAG Studio <versión> (<commit>), procedimiento <retrieval_pipeline>».
- **El paquete NKP no cambia:** su contrato v1.0.0 no transporta configuración de ejecución.

---

## 6. Mediciones completas (reproducción con supuestos)

Herramientas:
- `evaluacion_y_r.py`: 14 consultas × 2 fragmentaciones × 2 configuraciones de reranking × variantes;
- `casos_borde_referencias.py`: 15 casos sin modelos.

Resultados en `resultados_y_r.json` y `medicion_reranking.json`.

**Variantes:**
- **base:** código actual;
- **Y:** solo-YAML sin afinidad;
- **R:** referencias, 1 destino por fuente, modo pool;
- **YR:** Y + R;
- **YRb:** Y + R, modo búsqueda;
- **YR2:** Y + R, 2 destinos por fuente (**propuesta**).

**Columnas de la tabla:**
- «Puente delante»: consultas donde un puente que remite a la fuente esperada aparece antes que el fragmento correcto.
- «Solo-YAML»: fragmentos sin contenido en los top 5.
- «Peor que base»: consultas que empeoran respecto de base.
- «ms post»: costo máximo del paso posterior a la búsqueda.

| Compartidos / reranking | Variante | R@1 | MRR | Puente delante | Solo-YAML | Peor que base | R2 | S1 | ms post |
|---|---|---|---|---|---|---|---|---|---|
| documento_completo / sin (Runtime hoy) | base | 0.93 | 0.952 | 0 | 6 | — | 3 | 1 | 9 |
| | Y | 0.93 | 0.964 | 1 | 1 | R3 | 1 | 1 | 8 |
| | R | 1.00 | 1.000 | 0 | 4 | — | 1 | 1 | 9 |
| | **YR2** | **1.00** | **1.000** | **0** | **0** | — | 1 | 1 | 11 |
| documento_completo / con (Simulador hoy) | base | 1.00 | 1.000 | 0 | 7 | — | 1 | 1 | 10 |
| | **YR2** | **1.00** | **1.000** | **0** | **0** | — | 1 | 1 | 11 |
| por_encabezado / sin | base | 0.64 | 0.729 | 3 | 12 | — | – | 4 | 6 |
| | Y | 0.79 | 0.848 | 3 | 3 | — | 5 | 3 | 10 |
| | R | 0.64 | 0.774 | 0 | 9 | — | 4 | 3 | 16 |
| | YR | 0.93 | 0.964 | 0 | 0 | — | 1 | 2 | 9 |
| | **YR2** | **0.93** | **0.952** | **0** | **0** | — | 1 | 3 | 11 |
| por_encabezado / con | base | 0.64 | 0.729 | 3 | 12 | — | – | 4 | 6 |
| | YR | 0.86 | 0.893 | 1 | 2 | — | – | 2 | 8 |
| | YRb | 0.86 | 0.893 | 1 | 2 | — | – | 2 | 201 |
| | **YR2** | **0.86** | **0.917** | **0** | 2 | — | 2 | 3 | 9 |

**Cumplimiento de los criterios de NEXOM** (con YR2):
- **Fragmento correcto por delante del puente:** se cumple en las cuatro configuraciones (0 casos).
- **Sin regresiones:** ninguna consulta empeora respecto del código actual; planes, ordinales, información general y RVOE siguen en 1.º en todas las configuraciones.
- **Restricciones de fuentes:** los destinos provienen siempre de la búsqueda filtrada. Sección 5 de `casos_borde_referencias.py`: fuente fuera de filtros y búsqueda sin resultados permitidos.
- **Consistencia Simulador–Runtime:** con el mismo código y el **mismo** ajuste de reranking el resultado es idéntico, porque es el mismo motor. Hoy difieren por el reranking (4); la prueba E2E de la sección 7 lo fija.
- **Referencias inexistentes, ambiguas y circulares:** secciones 2 a 4 de `casos_borde_referencias.py` (además de la mención de la propia fuente, sección 9), todos correctos.

**Diferencia residual entre configuraciones con YR2:** con `por_encabezado`, R2 queda 2.º con reranking y 1.º sin él. S1 baja de 2.º (YR) a 3.º (YR2). Es el costo de traer dos destinos por fuente.

---

## 7. Pruebas a incorporar

**Unitarias, dominio (casos borde → pruebas):**
1. Detección de referencias: título con extensión; raíz identificador; título común sin extensión que no cuenta; límites de palabra; fuente propia; nombre ambiguo; nombre inexistente; mención dentro del YAML que no cuenta.
2. Puente por longitud; destino con contenido; solo-YAML; solo-encabezado; un puente nunca como destino.
3. Ciclo A↔B solo con puentes: sin expansión. Ciclo con contenido: un solo nivel.
4. Topes (`MAX_POR_FUENTE`, `MAX_DESTINOS`).
5. Restricción final: destino delante del primero de sus puentes; sin cambios si el puente no está.
6. Y: `affinity_title` de solo-YAML = «»; los casos de la Ronda 102 (C2) siguen pasando.

**Unitarias, aplicación (`SimulateConversation`):**
7. Con el ajuste desactivado: resultado idéntico al actual (regresión exacta).
8. Con R activado: destino delante del puente en `search_results`, en las ramas con y sin filtros.
9. Fuente referida excluida por filtro de metadatos, por nivel de acceso (`max_access_level`) o por no ser utilizable (no validada o no vigente): no se incorpora.
10. Trazado: `referenced_from`, `ambiguous_references`, `ResultOrderingView.via_reference_from`.

**Integración con LOTE01 real** (`test_ronda102_lote01_simulador.py` y uno nuevo `test_ronda104_referencias.py`):
11. «¿Qué documentos necesito para entrar al bachillerato?»: el fragmento con los requisitos en el top 3 y por delante de los puentes, en `documento_completo` y `por_encabezado`, con y sin reranking.
12. Las 14 consultas: ninguna peor que hoy; los ocho casos de la Ronda 102 siguen en su puesto.

**E2E Simulador = Runtime:**
13. La misma consulta, la misma instantánea y el mismo ajuste dan `chunk_id` y orden idénticos en `ConversationalService.simulate` (escritorio) y en `POST /messages` (`runtime_context` fijado a una copia).

**Trazabilidad:**
14. `/health` y `/messages` incluyen los campos de la sección 5; `runtime.db` guarda las columnas nuevas; una `runtime.db` antigua se actualiza sin perder filas.

**Regresión general:** las suites completas, unitarias e integración (incluidas las Rondas 91 y 100–102), `ruff` y `mypy` sin errores nuevos.

---

## 8. Archivos afectados (por etapa)

| Etapa | Archivos |
|---|---|
| 0. Trazabilidad | `app/build_info.py` (nuevo: versión y commit); `scripts/` de empaquetado (escriben `build_info.json`); `interfaces/api/schemas.py` (`HealthResponse`, `MessageResponse.execution`, `SourceSnippet`); `interfaces/api/app.py`; `interfaces/api/runtime_context.py` (expone identidad, índice y reranking disponible); `application/runtime/commands/handle_incoming_message.py` y `domain/runtime/entities.py` (`ConversationLogEntry`); `infrastructure/database/runtime_repositories.py` (columnas aditivas); `application/conversational/queries/simulate_conversation.py` (`retrieval_pipeline` en el trazado); `ui/conversational/panel.py`; Manual 8.5 y nota de la Ronda 46 (corrección) |
| 1. Y | `domain/conversational/section_affinity.py`; pruebas de dominio |
| 2a. R (desactivado por defecto) | `domain/conversational/source_references.py` (nuevo, funciones puras del prototipo); `simulate_conversation.py` (paso R y restricción final); `application/rag/queries/semantic_search.py` (`SemanticSearchResult.referenced_from`); `domain/projects/entities.py`, `infrastructure/database/models.py` y `repositories.py`, migración de proyecto **0025** (`project.reference_resolution`, nullable); `application/projects/` (comando y servicio); `ui/conversational/panel.py` (ajuste y reporte); `interfaces/api/schemas.py` (`referenced_from_chunk_id`); pruebas 1–13 |
| 2b. R activado por defecto | solo el valor por defecto, tras la validación de NEXOM con la v2 |
| 3. Reranking | según la decisión de NEXOM: A (`runtime_context.py` construye el reranker; validación al arrancar) o B (cambiar «Automático» a «sin reranking» en `SimulateConversation._reranking_decision`; aviso en el Simulador) |
| 4. Documentación | Manual 8.2, 8.3 y 8.5; README; resultados en `docs proyecto` |

Ninguna etapa modifica documentos, fragmentos, metadatos ni índices existentes: no hay que reindexar ni volver a fragmentar.

---

## 9. Riesgos

| Riesgo | Mitigación |
|---|---|
| Falsos positivos de referencia (un texto menciona el nombre de una fuente sin remitir a ella) | Solo títulos con extensión o raíces identificadoras; solo fragmentos ≤ 80 palabras; solo destinos ya recuperados. El efecto es reordenar, nunca agregar contenido no recuperado |
| Puentes que remiten a varias fuentes (áreas, cualidades) traen destinos poco pertinentes | Topes de 2 por fuente y 5 por consulta; la afinidad sigue ordenando entre destinos; costo medido: S1 de 2.º a 3.º en `por_encabezado` |
| Destino equivocado dentro de un documento fragmentado por encabezado | 2 destinos por fuente; limitación documentada (3.7); recomendación editorial |
| Cambio de comportamiento en otros proyectos | R desactivado por defecto hasta la etapa 2b; Y solo afecta a fragmentos sin contenido |
| Exposición del commit en `/health` | Opción de moverlo a un endpoint protegido |
| `runtime.db` antiguas | Columnas aditivas con el patrón ya usado (Rondas 19 y 93) |
| Diferencia de latencia o calidad si se elige A | Medir en el servidor del Runtime antes de decidir; validación al arrancar |
| Reproducción con supuestos distinta del caso real | Etapa de reproducción exacta (1.3) antes de la 2b |

---

## 10. Secuencia de implementación propuesta (cada etapa con autorización propia)

0. **Trazabilidad** (no cambia ningún orden de resultados). Permite completar la reproducción exacta del trace y medir las siguientes etapas en el entorno real.
1. **Y.**
2. **R:**
   - **2a:** implementación desactivada por defecto, validada por NEXOM en la v2;
   - **2b:** activación por defecto.
3. **Decisión de reranking** (A o B) y su implementación.
4. **Documentación y cierre:** Manual, README y resultados.

**Criterio de paso entre etapas:**
- suites completas en verde;
- evaluación de las 14 consultas sin regresiones;
- para 2b y 3, la reproducción exacta del incidente (1.3) con la instantánea real.
