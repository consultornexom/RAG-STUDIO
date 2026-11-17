# Ronda 104b, Etapa 0: trazabilidad y reproducibilidad (informe de implementación)

**Autorización:** NEXOM, «Autorización de Etapa 0», solo esta etapa.

**Fuera de alcance, sin implementar:**
- Y (Etapa 1);
- R (Etapa 2);
- la decisión y la modificación del reranking (Etapa 3).

**Garantías de esta etapa:**
- no cambia ningún comportamiento por defecto;
- no modifica ranking, reranking, fragmentación, metadatos, documentos ni índices.

## 1. Qué se agregó

| Punto autorizado | Implementación |
|---|---|
| 1. Versión y commit del código | `infrastructure/build_info.py`: versión (`pyproject`), commit y marca de cambios sin commit, desde `build_info.json` o, si no existe, `git`. **Huella del código** SHA-256 por carpeta (`app`, `application`, `domain`, `infrastructure`, `interfaces`, `migrations`, `ui`, `workers`), con saltos de línea normalizados: identifica el código aunque la instalación no tenga `.git`. `scripts/escribir_build_info.py` genera `build_info.json` para los ZIP y paquetes; con `--verificar <carpeta>` compara huellas por carpeta. El `Dockerfile` y el `.spec` de PyInstaller incluyen `build_info.json` si existe. El archivo no se versiona (`.gitignore`) |
| 2. Versión y huella de la instantánea | `runtime_context.describe_snapshot`: versión, huella declarada al publicar (`snapshot_identity.json`) y huella **calculada al cargar, antes de abrir** `project.db`, más `fingerprint_matches` |
| 3. Índice y procedimiento | Índice: proveedor, modelo y dimensiones de embeddings, puntos, fecha, perfil y modelo de consulta del proceso. Procedimiento: `RETRIEVAL_PIPELINE = "r102"` (constante documentada en `simulate_conversation.py`; cambiará con cada ronda que altere el orden) |
| 4. Reranking efectivo | `SimulationTrace`: `reranking_available`, `reranking_available_model` (nuevos), además de `reranking_setting`, `reranking_applied`, `reranking_model` y `reranking_note` (Ronda 102) |
| 5. Texto de búsqueda y filtros | `SimulationTrace.search_text`: texto EXACTO con el que se buscó (antes solo existía `retrieval_query`, nulo si coincidía con la consulta). Filtros aplicados y fuentes excluidas |
| 6. Fragmentos en orden | `conversation_log.chunk_ids` (JSON ordenado; `source_ids` no conservaba el orden) y `execution.results` (posición, `chunk_id`, `source_id`, puntaje, puesto en la búsqueda, afinidad) |
| 7. Exposición | Ver la sección 2 |
| 8. Manual | 8.5: nota de la Ronda 46 corregida (el Runtime **nunca** aplica reranking), párrafo de la Ronda 102 corregido y párrafo nuevo «Datos de ejecución». Corrección también en `Resultados_Ronda102.md`. Sección 7ter en el `CONTRATO_INTEGRACION.md` que genera el paquete de entrega |

**Lo desconocido se declara, no se inventa.** Cada registro lleva `unknown`, con entradas como `code.commit`, `code.dirty`, `snapshot.declared_fingerprint` o `index`.

## 2. Dónde se expone

| Superficie | Contenido | Acceso |
|---|---|---|
| `POST /messages`, campo `execution` (nuevo, opcional) y, en `sources`, `retrieval_rank` y `affinity` | registro completo (`application/runtime/execution_info.py`) | **solo la clave operativa** (`X-API-Key`), o sin clave configurada (modo local de pruebas). Con un token de widget llegan `null`: el canal público no ve detalles internos |
| `GET /health` (público) | agrega solo `code_version` y `retrieval_pipeline` | público, como antes |
| `GET /health/details` (nuevo) | código (versión, commit, huella global y por carpeta), procedimiento, modo, perfil, disponibilidad del reranker, instantánea fija declarada, instantáneas cargadas (identidad, huellas, índice) | `X-API-Key` |
| `runtime.db`, `conversation_log` | columnas nuevas `chunk_ids` y `execution` (JSON), en **todos** los turnos (también los de widget); los turnos fallidos guardan la parte fija | interno |
| Simulador (escritorio) | bloque «Ejecución» al final del reporte: versión, commit, huella, procedimiento, reranking (disponible, ajuste, aplicado) y texto exacto de búsqueda | operador |

**Sin secretos.** Ningún registro contiene credenciales, claves, tokens, rutas del servidor, nombres de equipo ni variables de entorno. Una prueba verifica que la respuesta y `runtime.db` no contienen la clave ni la ruta de la instalación.

## 3. Pruebas de aceptación

| # | Criterio | Evidencia |
|---|---|---|
| 1 | Misma consulta y configuración → mismo orden antes y después | `comparar_orden.py`: las 14 consultas de LOTE01 (archivos y modelos reales) **con y sin reranking** (28 casos), con el código anterior (`1f36a2b`) y el nuevo: **0 diferencias** en acción, intención, confianza y lista ordenada (fuente, huella del texto, puntaje a 6 decimales). Archivos: `orden_antes_etapa0.json`, `orden_despues_etapa0.json`. En el Runtime: `test_el_orden_de_fragmentos_no_cambia_con_o_sin_execution` |
| 2 | `/messages` conserva sus campos y agrega los diagnósticos | `test_messages_con_clave_operativa_trae_execution_completo` (todos los campos existentes presentes) y `test_messages_con_token_de_widget_no_expone_execution` |
| 3 | Bases históricas siguen funcionando | `test_runtime_db_anterior_sin_columnas_nuevas_conserva_sus_filas`: una `runtime.db` con el esquema anterior a la Ronda 19 se actualiza sola (columnas aditivas), conserva su fila y la lee con `chunk_ids`/`execution` nulos. Las pruebas de `runtime.db` existentes pasan |
| 4 | Simulador y Runtime muestran el reranking efectivo | Simulador: `test_ronda104b_el_reporte_incluye_los_datos_de_ejecucion`. Runtime: `execution.reranking` = automático, sin modelo, no aplicado |
| 5 | Los datos identifican versión, instantánea y configuración | `test_runtime_db_guarda_orden_y_ejecucion_localizables_por_trace` (por `trace_id`: código, huellas, orden) y `test_health_publico_sin_detalles_internos_y_details_protegido` |
| 6 | Sin fallos nuevos | Ver totales abajo |

**Pruebas nuevas:**
- `tests/unit/infrastructure/test_build_info.py` (5);
- `tests/unit/application/test_execution_info.py` (3);
- `tests/integration/test_runtime_execution_trace.py` (6);
- una más en `tests/unit/ui/test_simulador_reranking_ronda102.py`.

**Totales:**
- `tests/unit` + smoke: 1027 pasadas (sin UI) + 124 pasadas de UI, más las 2 fallas preexistentes de `test_metadata_conversational_field_refresh.py` (las mismas de rondas anteriores).
- Integración: **572 pasadas, 0 fallidas** (62 archivos; `test_fastembed_image_provider.py` no se ejecuta en este entorno porque descarga un modelo).
- `ruff`: los 14 hallazgos históricos de `docs proyecto`, ninguno nuevo.
- `mypy` (`app application domain infrastructure interfaces ui`): 127, el mismo total que el código anterior con la misma invocación.

## 4. Compatibilidad

- **Consumidores de `/messages`.** Todos los campos anteriores siguen igual: nombre, tipo, presencia y orden de `sources`. Los nuevos son opcionales y nulos por defecto. Testing Agent puede ignorarlos. Para recibir `execution` debe usar `X-API-Key`.
- **`runtime.db`.** Columnas aditivas con el mismo mecanismo de las Rondas 19 y 93: sin pérdida de filas y sin migración manual.
- **Proyectos e instantáneas.** No hay migración de proyecto. Las instantáneas anteriores a la Ronda 92 (sin `snapshot_identity.json`) se sirven igual: la huella declarada queda como desconocida y se informa la calculada al cargar.
- **Costo.** Cada vez que se carga una instantánea en el proceso se calcula su huella (un recorrido de lectura de sus archivos), y una vez por proceso la huella del código. Las respuestas no tienen costo adicional medible: el registro se arma con datos ya calculados.
- **NEXOM Knowledge Package.** Sin cambios: su contrato v1.0.0 no transporta configuración de ejecución.

## 5. Datos que siguen sin poder conocerse

- **Turnos anteriores a esta etapa** (incluido el incidente 493c8033): no tienen `execution` ni `chunk_ids`. Ver `Procedimiento_Evidencias_E1_E7.md`.
- **Un Runtime instalado sin `.git` ni `build_info.json`** informa `commit: null` (en `unknown`), pero sí su huella del código, que permite identificarlo contra commits candidatos.
- **Un ejecutable congelado (PyInstaller)** no tiene archivos `.py`: depende de `build_info.json` para versión, commit y huella.

## 6. Archivos modificados

- **Nuevos:**
  - `infrastructure/build_info.py`;
  - `application/runtime/execution_info.py`;
  - `scripts/escribir_build_info.py`;
  - las tres pruebas de la sección 3;
  - esta carpeta (informe, procedimiento E1–E7, `comparar_orden.py` y resultados).
- **Modificados:**
  - `application/conversational/queries/simulate_conversation.py`: solo campos de traza (`RETRIEVAL_PIPELINE`, `search_text`, disponibilidad del reranker); sin cambios de orden;
  - `application/runtime/commands/handle_incoming_message.py`;
  - `domain/runtime/entities.py`;
  - `infrastructure/database/runtime_repositories.py`;
  - `interfaces/api/runtime_context.py`, `interfaces/api/app.py` e `interfaces/api/schemas.py`;
  - `app/bootstrap.py` (`AppContext.code_identity`);
  - `ui/conversational/panel.py` (bloque «Ejecución»);
  - `application/release/commands/export_deployment_package.py` (texto del contrato, sección 7ter);
  - `packaging/api/Dockerfile` y `packaging/ragstudio.spec`;
  - `.gitignore`;
  - el Manual (`.docx` y `.pdf`);
  - `README.md`;
  - `docs proyecto/Ronda102_Diagnostico_Simulador/Resultados_Ronda102.md` (corrección).

## 7. Cómo usarlo en la validación de NEXOM

1. **Preparar la entrega.** En el checkout que se vaya a desplegar, ejecutar `python scripts/escribir_build_info.py` antes de crear el ZIP o el paquete.
2. **Comprobar lo que sirve el Runtime.** Tras desplegar, `GET /health/details` con `X-API-Key` muestra commit, huella del código e instantánea servida.
3. **Enviar las pruebas con la clave operativa.** Así cada respuesta trae `execution`. En cualquier caso, `runtime.db` lo guarda y se localiza por `trace_id`.
4. **Reproducir el incidente.** Para el 493c8033: `Procedimiento_Evidencias_E1_E7.md`.
