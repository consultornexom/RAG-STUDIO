# Ronda 106: procedimiento de recuperación r106 (V + Y + R)

**Autorización:** NEXOM, sobre el diagnóstico de la Ronda 105f (commit `92529bf`).

**Alcance:** V, Y y R como un único procedimiento (`r106`), elegible por proyecto, con reversión a `r105b`.

**Sin cambios en:**
- documentos de AGENTE UDL, políticas de fragmentación, índices, metadatos y catálogos;
- intenciones y ejemplos, casos y expectativas de Calidad;
- reranking de P1 (alternativa B estricta).

**Fuera de alcance:** M, P3 y P4. El incidente 493c8033 sigue **abierto**.

**Control de liberación:** esta entrega permite desarrollar y probar. No libera AGENTE UDL ni despliega `r106` en producción hasta que NEXOM verifique sus casos de Calidad reales.

## 1. Cambios técnicos

| Componente | Qué hace | Dónde |
|---|---|---|
| **V** afinidad por valor | puntaje = 1/(61 + puesto en la búsqueda) + afinidad/61. Una afinidad de 0.18 ya no pesa lo mismo que una de 0.57; una afinidad 0 no suma; a igual puntaje gana la búsqueda. | `domain/conversational/section_affinity.py` → `combine_by_value` |
| **Y** solo-YAML | Un fragmento sin título de sección y sin ninguna palabra fuera del YAML tiene título de afinidad vacío (afinidad 0), en vez del nombre del archivo. | `affinity_title(..., exclude_yaml_only=True)` |
| **R** referencias | Diseño de la Ronda 104b con los ajustes de las Rondas 105c a 105f (detalle debajo de la tabla). | `domain/conversational/reference_resolution.py` (nuevo) |
| Procedimiento | `r105b` o `r106`; valor desconocido → error explícito, nunca sustitución silenciosa. | `domain/conversational/retrieval_procedure.py` (nuevo) |
| Motor | `SimulateConversation._search_and_filter`, rama con filtro de metadatos: con `r106` aplica R, Y y V, y al final la restricción de R. Sin filtro, el resultado es idéntico a `r105b`. | `application/conversational/queries/simulate_conversation.py` |

**Detalle de R (resolución de referencias):**
- **Puente:** fragmento de hasta 80 palabras sin YAML que menciona otra fuente **permitida por los filtros**, por su nombre con extensión (`requisitos_ingreso.md`) o por su raíz con forma de identificador. Un título común sin extensión no cuenta.
- **Destinos:** los 2 mejores fragmentos con contenido de esa fuente que ya estén en el conjunto de la búsqueda. Máximo 5 por consulta, sin recursión. Un puente nunca es destino.
- **Orden:** el destino se inserta antes de su puente. Al final, la restricción garantiza que quede por delante de todos sus puentes.
- **Ambigüedad:** un nombre que corresponde a varias fuentes no se resuelve y se informa en la traza.

**Garantía de V + R conjuntos:** no existen ajustes separados. El proyecto elige `r106` (los tres) o `r105b` (ninguno). Así no es posible activar V sin R.

**Lo que no cambia:** intención, confianza, variables, filtros, guardrails, acción y reranking. V, Y y R actúan solo en el orden de los fragmentos ya recuperados y filtrados.

## 2. Ajuste por proyecto y comportamiento predeterminado

- **Almacenamiento:** entrada versionada `retrieval_procedure` de la tabla `configuration` del `project.db`. Esa tabla ya existía, así que **no hay migración de esquema**. Cada cambio agrega una versión y queda el historial.
- **Proyectos nuevos** (crear o clonar): `r106`.
- **Proyectos existentes, instantáneas publicadas y `.agentproj` anteriores a esta ronda:** no tienen la entrada, así que usan **`r105b`**. Su configuración efectiva no cambia en silencio, y **AGENTE UDL sigue en `r105b`** hasta que NEXOM elija `r106`.
- **Cómo se cambia:** Simulador → selector «Procedimiento de recuperación», con dos opciones: `r106` y `r105b`.
  - El cambio se aplica de inmediato en el Simulador y en los casos de Calidad, que usan el mismo motor.
  - Llega al Runtime **al publicar una versión nueva**, igual que el reranking.
- **Reversión:** elegir `r105b` y publicar. El orden vuelve a ser exactamente el anterior (prueba `test_r105b_conserva_el_orden_anterior_exacto`).
- **Portabilidad:** viaja con el `.agentproj` y con la copia importada con un identificador nuevo (prueba `test_el_ajuste_viaja_con_el_agentproj_y_con_la_copia`).

## 3. Visibilidad y equivalencia Simulador–Runtime

**Un solo lector:** `ProjectRetrievalProcedureReader`.
- El Simulador lo aplica sobre el proyecto en edición.
- El Runtime lo aplica sobre el `project.db` de la instantánea servida.
- **Mismo código de motor en los dos.**

**Al cargar una instantánea**, el Runtime valida el procedimiento. Si es desconocido, responde 503 con `configuration.retrieval_procedure_unknown`.

**Dónde se informa el procedimiento:**

| Superficie | Contenido |
|---|---|
| Simulador | Selector y bloque «Ejecución»: «Procedimiento de recuperación: r106 (ajuste del proyecto; el Runtime usa el mismo de la versión publicada)». Junto a cada fragmento: «traído por referencia desde …»; también las referencias ambiguas. |
| `POST /messages` (`execution`, con `X-API-Key`) y `runtime.db` | `retrieval_pipeline` efectivo, `results[].referenced_from` y `ambiguous_references`. |
| `GET /health` | `retrieval_pipeline` (predeterminado para proyectos nuevos: `r106`) y `retrieval_pipelines_supported`. |
| `GET /health/details` | `loaded_snapshots[].retrieval_pipeline`, el efectivo de cada instantánea. |

**Pruebas de equivalencia** (`tests/integration/test_ronda106_equivalencia_procedimiento.py`), con la misma instantánea, las mismas consultas y filtro de metadatos:
- **Sin ajuste, `r105b` y `r106`:** el Simulador y `POST /messages` coinciden en los fragmentos (ids y orden), los puntajes, la acción, `retrieval_pipeline`, `retrieval_rank` y `referenced_from`.
- **Con `r106`:** el documento referido queda delante del puente y el fragmento solo-YAML tiene afinidad 0.
- **El Runtime usa la versión publicada:** cambiar el ajuste del proyecto no altera la versión ya publicada.
- **Procedimiento desconocido:** error explícito en el Simulador y 503 en el Runtime.

## 4. Resultados y comparación con r105b

**Herramienta:** `evaluacion_r106.py`, con el **motor real** (no el prototipo), los cinco archivos reales de LOTE01 y la intención real de requisitos (descripción y 8 + 8 ejemplos). Las demás intenciones son las supuestas. Conteo de subpalabras, el mismo que la Ronda 105f. Resultados en `resultados_r106.json` y `salida_evaluacion.txt`.

MRR = media de 1/posición del fragmento correcto (1.000 = siempre 1.º). «—» = fuera del top 5.

| Configuración | r105b: MRR (R1, R2, R3) | r106: MRR (R1, R2, R3) | Consultas peores | Decisiones distintas |
|---|---|---|---|---|
| **Real de AGENTE UDL** (planes por encabezado, compartidos documento completo) | 0.857 (2, —, 2) | **1.000 (1, 1, 1)** | 0 | 0 |
| Compartidos por encabezado | 0.696 (—, —, —) | 0.857 (3, 3, 1) | 0 | 0 |
| Todo por tamaño 500/60/80 | 0.788 (1, 3, 1) | 0.871 (1, 1, 1) | 0 | 0 |
| Corpus sintético de la Ronda 102 (R1) | 1.º | **1.º** | — | 0 |

**Coincide exactamente** con la variante VYR del prototipo de la Ronda 105f en las tres configuraciones: la implementación reproduce lo validado.

**Detalle de la configuración real con `r106`:**
- **UDL-BACH-003 (R1):**
  1. requisitos (búsqueda #2, afinidad 0.64);
  2. «Información general» de Torres Landa (búsqueda #1, afinidad 0.19).
- **«¿Qué documentos necesito para entrar al bachillerato?» (R2):** en 1.º, requisitos (búsqueda #13, afinidad 0.37); los fragmentos puente de los planes quedan **fuera del top 5**, por detrás.
- **Las otras 11 consultas siguen en 1.º:** plan de estudios, ordinales, información general y RVOE.

**Motor de Calidad** (`RunEvaluation`, banco LOTE01 de 14 casos; `calidad_r106.py --lote01`; `calidad_lote01_r105b_r106.json`):

| | r105b | r106 |
|---|---|---|
| Veredicto global | amarillo | **verde** |
| Recall@3 | 0.929 | **1.000** |
| MRR | 0.857 | **1.000** |
| Casos con cambios | — | R1, R2, R3, todos mejores |
| Casos peores | — | **ninguno** |

**Latencia** (configuración real, 14 consultas × 3): p50 de 39–41 ms con `r105b` y de 42–45 ms con `r106`. Diferencia de unos 1–6 ms.

## 5. Pruebas obligatorias (sección 4 de la autorización)

| # | Prueba | Resultado |
|---|---|---|
| 1 | 14 casos LOTE01, políticas reales | `test_ronda106_procedimiento_r106.py::test_configuracion_real_de_agente_udl`: R1 y R2 en 1.º, requisitos delante de los puentes, ninguna peor, MRR 0.857 → 1.000 |
| 2 | Otras estrategias | `test_otras_estrategias_sin_regresiones[por_encabezado, por_tamanio_todos]`: ninguna consulta peor ni decisión distinta |
| 3 | Corpus sintético de la Ronda 102 | `test_corpus_sintetico_ronda102_…`: requisitos delante de las secciones que remiten a él. Dominio: V sola lo deja 3.º y V + R 1.º (`test_patron_sintetico_ronda102_…`) |
| 4 | 15 casos borde de la Ronda 104b | `tests/unit/domain/test_reference_resolution_ronda106.py`: los 15 más el ajuste de títulos, la mención dentro del YAML, sin duplicados y solo-YAML (26 pruebas) |
| 5 | Afinidad histórica de la Ronda 91 | `test_ronda91_perfil_del_egresado_sigue_primero[r105b, r106]`; además, `test_section_affinity.py` y las pruebas de la Ronda 102 sin cambios |
| 6 | Equivalencia Simulador–Runtime | sección 3 (7 pruebas) |
| 7 | Suites completas | ver debajo de la tabla |

**Suites completas (punto 7):**
- **Unitarias, smoke e interfaz:** 1209 pasadas.
  - 2 fallas **preexistentes**, idénticas en el commit anterior (`test_metadata_conversational_field_refresh.py`, un campo de selección múltiple sin catálogo), ajenas a esta ronda.
- **Integración:** 583 pasadas y 9 omitidas.
  - 3 archivos no se ejecutaron porque descargan modelos a una carpeta temporal y este entorno no tiene red: `test_fastembed_provider`, `test_fastembed_reranker` y `test_fastembed_image_provider`.
- **Única prueba existente actualizada:** `test_runtime_execution_trace.py`. Cambió el contrato de `/health`: `retrieval_pipeline` pasa a ser el predeterminado (`r106`) y se agrega `retrieval_pipelines_supported`.
- **Calidad del código:** `ruff` sin hallazgos en los archivos de la ronda; `mypy` sin errores nuevos.

**Reconocimiento de intención, decisiones, filtros y reglas:** idénticos entre `r105b` y `r106`. Se comprobó en las 14 consultas de las tres configuraciones, en las pruebas unitarias (`test_decision_identica_en_ambos_procedimientos`) y en la equivalencia.

## 6. Instalación Windows de NEXOM: actualización

1. **Detener** la app de escritorio y el Runtime. **Respaldar:**
   - la carpeta de datos `RAGSTUDIO_HOME` (`application.db`, `projects\`, `snapshots\`, `runtime.db`);
   - el paquete en uso.
2. **Actualizar el código** al commit de esta entrega:
   - con git: `git fetch`, `git checkout main`, `git pull`;
   - con ZIP: reemplazar la carpeta de código, conservando el entorno virtual y la carpeta de datos.

   Opcional: `python scripts\escribir_build_info.py`.
3. **No se requieren:**
   - **migraciones:** el ajuste usa la tabla `configuration`, que ya existía;
   - **dependencias nuevas** ni `pip install`;
   - **reindexación:** no cambian fragmentos, metadatos ni índices;
   - **republicación** de las versiones existentes, que siguen en `r105b`.
4. **Verificar que nada cambió:**
   - abrir AGENTE UDL en el Simulador: el selector «Procedimiento de recuperación» debe mostrar **`r105b`**;
   - arrancar el Runtime: `GET /health` → `retrieval_pipelines_supported: ["r105b", "r106"]`;
   - un mensaje de prueba con `X-API-Key` → `execution.retrieval_pipeline = "r105b"`.
5. **Validar `r106` sin publicar** (escritorio):
   - **Elegir `r106`** en el selector.
   - **UDL-BACH-003:** en el Simulador, `requisitos_ingreso.md` debe quedar 1.º.
   - **Consulta de documentos:** «¿Qué documentos necesito para entrar al bachillerato?» debe dejar los requisitos delante de los fragmentos puente, con la nota «traído por referencia desde …».
   - **Casos de Calidad:** ejecutar los 14 casos en la pestaña Calidad y comparar con la corrida base `085fe5a5-eed8-40b5-aabf-8972458fb3e5`.
     - Criterios: Recall@3 100 %, MRR ≥ 0.90 (objetivo 1.00), ningún caso aprobado empeora, intención y decisiones sin cambios.
   - **Comparación automática:** `python "docs proyecto\Ronda106_Procedimiento_r106\calidad_r106.py" --agentproj <copia de AGENTE_UDL.agentproj> --modelos data\models --salida calidad_udl.json`. Importa una copia en una instalación temporal y ejecuta el banco completo con `r105b` y con `r106`. El archivo original no se toca (se verifica su SHA-256).
6. **Si aparece una regresión:** volver a `r105b` en el selector. El cambio es inmediato en el escritorio; en el Runtime, publicar de nuevo.
7. **Despliegue en el Runtime:** solo tras la aprobación de NEXOM (sección 7 de la autorización). Elegir `r106`, publicar una versión nueva y comprobar `execution.retrieval_pipeline = "r106"` y `/health/details` → `loaded_snapshots[].retrieval_pipeline`.

## 7. Riesgos pendientes

- **Las demás intenciones de AGENTE UDL son supuestas en la reproducción.** Lo cubre la validación real de NEXOM con la corrida `085fe5a5`.
- **Compartidos fragmentados por encabezado** (no es el caso de AGENTE UDL): `r106` mejora `r105b` (0.696 → 0.857), aunque R1 y R2 quedan 3.º. La sección con la respuesta se titula «Contenido», con afinidad 0. Requiere afinidad heredada del encabezado superior (P), fuera de alcance.
- **R puede traer un segundo fragmento poco pertinente** de la fuente referida, como «Procedencia». Está acotado a 2 por fuente y 5 por consulta.
- **La escala de V** (una afinidad de 1.0 equivale al primer puesto de la búsqueda) conviene vigilarla con más proyectos.
- **Las corridas de Calidad no guardan el procedimiento con que se ejecutaron.** El Simulador y el Runtime sí lo registran. Al comparar corridas, anotar el procedimiento elegido. Registrarlo en `evaluation_run` requeriría una migración y queda como mejora posible.
- **`GET /health` público informa el procedimiento predeterminado para proyectos nuevos** (`r106`), no el de cada instantánea. El efectivo está en `/health/details` y en `execution`.

## 8. Archivos

| Tipo | Archivos |
|---|---|
| **Nuevos** | `domain/conversational/reference_resolution.py`, `domain/conversational/retrieval_procedure.py`, `application/projects/commands/update_retrieval_procedure.py` |
| **Modificados (motor e interfaz)** | `section_affinity.py`, `simulate_conversation.py`, `conversational/service.py`, `projects/service.py`, `repositories.py` (lector), `runtime_context.py`, `app.py`, `schemas.py`, `execution_info.py`, `failure_diagnosis.py`, `bootstrap.py`, `ui/conversational/panel.py`, `export_deployment_package.py` (guía del paquete) |
| **Pruebas nuevas** | `test_reference_resolution_ronda106.py`, `test_section_affinity_ronda106.py`, `test_simulate_conversation_ronda106.py`, `test_simulador_procedimiento_ronda106.py`, `test_ronda106_procedimiento_r106.py`, `test_ronda106_equivalencia_procedimiento.py`, más 5 pruebas en `test_project_service.py` |
| **Documentación** | Manual (8.2, «Cómo se elige el apartado», y 8.5, Simulador), README, este informe y herramientas `evaluacion_r106.py` y `calidad_r106.py` |
