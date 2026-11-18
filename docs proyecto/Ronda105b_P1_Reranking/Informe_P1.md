# Ronda 105b: implementación de P1 (alternativa B estricta)

**Decisión de NEXOM:** alternativa B en modalidad estricta, con las condiciones 1 a 7.

**Alcance:** solo P1. Siguen pendientes:
- P2, P3 y P4;
- el incidente 493c8033, que continúa abierto.

**Antes de implementar:** se verificó que `9998926` y `d927150` están en `origin/main` (`git fetch` + `git branch -r --contains d927150`).

## 1. Resumen técnico

| Condición | Implementación |
|---|---|
| 1. «Automático» = sin reranking en el Simulador y en el Runtime | `SimulateConversation._reranking_decision`: Automático y Desactivado → sin reranking, haya o no modelo. Antes, Automático aplicaba el reranking si había modelo: el Simulador sí y el Runtime nunca |
| 2. Reranking solo con «Activado» | Única vía que pide `rerank=True`. Sin decisión explícita, `_search_and_filter` ya no reordena (antes: `has_reranker`) |
| 3. Verificación real del modelo y error explícito | **Simulador:** `RagService.ensure_reranker_ready()` carga el modelo antes de buscar; si no hay o no carga → `RerankingRequiredUnavailableError`, la simulación falla con un mensaje claro. **Runtime:** `runtime_context._build` construye el reranker **solo** si el proyecto de la instantánea tiene «Activado», lo carga y, si falla, no sirve la instantánea → **503, `error.code = configuration.reranking_unavailable`, categoría `configuration_error`** (`failure_diagnosis.py`), con un resumen que indica qué hacer y la causa técnica en el detalle. «Disponible» ahora significa **cargado y verificado** (`Reranker.ensure_ready()` e `is_loaded`), no solo configurado |
| 4. El Simulador muestra la configuración efectiva en el Runtime y la registra | Selector con etiquetas nuevas («Automático (predeterminado): sin reranking», «Activado: con reranking (exige el modelo cargado)», «Desactivado: sin reranking»). Debajo, «Configuración efectiva (Simulador y Runtime): …». Aviso al elegir «Activado». Campos nuevos del trazado: `runtime_effective_reranking` y `reranking_model_status`, también en `execution.reranking` (`effective_in_runtime`, `model_status`). El reporte agrega «Configuración efectiva en el Runtime: … — igual a la de esta simulación» |
| 5. Pruebas de equivalencia | Sección 3 |
| 6. Casos de Calidad antes y después | Sección 4 |
| 7. Runtime sin cambios ni requisitos nuevos para proyectos sin «Activado» | Sección 3: el orden de las 28 consultas es idéntico, y una prueba falla si el Runtime intenta construir un reranker para un proyecto sin «Activado» |

**Procedimiento de recuperación:** pasa a `r105b`. Para proyectos sin «Activado», el orden del Runtime es idéntico al de `r102`.

**Sin cambios en:** documentos, fragmentos, metadatos, índices, migraciones, `runtime.db` y dependencias. `project.agent_reranking` conserva sus valores; solo cambia el significado del valor nulo (Automático).

**Otros archivos:**
- Manual 8.5, actualizado;
- `CONTRATO_INTEGRACION.md` del paquete de entrega (sección 7ter).

## 2. Archivos modificados

| Capa | Archivos |
|---|---|
| Dominio | `domain/rag/exceptions.py` (`RerankingRequiredUnavailableError`); `domain/rag/ports.py` (`Reranker.ensure_ready`, `is_loaded`, con valores por defecto) |
| Aplicación | `application/rag/queries/hybrid_search.py`; `application/rag/service.py` (`reranker_loaded`, `ensure_reranker_ready`); `application/conversational/queries/simulate_conversation.py`; `application/runtime/execution_info.py`; `application/runtime/failure_diagnosis.py`; `application/release/commands/export_deployment_package.py` (texto del contrato) |
| Infraestructura | `infrastructure/rerankers/fastembed_cross_encoder.py` |
| Interfaces | `interfaces/api/runtime_context.py` (reranker condicional + `reranker_factory`); `interfaces/api/app.py`; `interfaces/api/schemas.py` |
| UI | `ui/conversational/panel.py` |
| Pruebas | `tests/integration/test_ronda105b_equivalencia_reranking.py` (nuevo); actualizadas: `test_simulate_conversation.py`, `test_simulate_conversation_ronda102.py`, `test_execution_info.py`, `test_simulador_reranking_ronda102.py`, `test_runtime_execution_trace.py`, `test_ronda102_lote01_simulador.py` |
| Documentación | Manual (`.docx` y `.pdf`); README; esta carpeta; `comparar_orden.py` (comparación canónica, ver sección 3) |

## 3. Pruebas de regresión y equivalencia

**Equivalencia Simulador–Runtime** (`test_ronda105b_equivalencia_reranking.py`; misma instalación, misma instantánea publicada, mismas consultas):
- **Automático, Desactivado y Activado con modelo:** el Simulador de escritorio y `POST /messages` entregan los mismos `chunk_id`, en el mismo orden y con los mismos puntajes, la misma acción y la misma `execution.reranking` (aplicado, efectiva, estado del modelo).
- **Automático:** el Runtime **no construye** reranker (la prueba falla si lo intenta) y responde normalmente.
- **Activado sin modelo, o con un modelo que no carga:** el Simulador lanza `RerankingRequiredUnavailableError` y el Runtime responde 503 `configuration.reranking_unavailable`.

**LOTE01 real** (14 consultas, archivos y modelos reales; `comparar_orden.py`):

| Comparación | Resultado |
|---|---|
| Runtime (motor sin modelo) antes vs después | **14/14 iguales** (condición 7) |
| Simulador de escritorio (motor con modelo, Automático) después vs Runtime después | **14/14 iguales** (condición 1) |
| Simulador antes (reranqueaba) vs después | 13/14 con otro orden: es el cambio buscado; el Simulador deja de diferir del Runtime |

**Nota sobre la comparación.** `comparar_orden.py` compara ahora de forma canónica los fragmentos con **texto idéntico en fuentes distintas** (las secciones «Información compartida…» de ambos planes).
- **El motivo:** en la construcción en memoria con ids aleatorios, su orden relativo alterna entre ejecuciones del **mismo** código (comprobado: 3 corridas idénticas dieron 2 órdenes distintos).
- **En el Runtime real no ocurre:** los ids son persistentes.

**Suites:**
- `tests/unit` + smoke: **1030 pasadas**.
- UI: **125 pasadas**, más las 2 fallas preexistentes de `test_metadata_conversational_field_refresh.py`.
- Integración: **577 pasadas, 0 fallidas** (63 archivos; `test_fastembed_image_provider.py` no se ejecuta en este entorno).
- `ruff`: sin hallazgos nuevos (los 14 históricos de `docs proyecto`).
- `mypy`: 127, el mismo total que antes.

## 4. Casos de Calidad: antes y después (condición 6)

**Mismo motor de Calidad** (`RunEvaluation`) con el código anterior (`d927150`) y el nuevo:

**1. Banco histórico de Bachillerato** (`restauracion_v2_01c3ccc3-….agentproj`, 7 casos de Calidad propios; importado como copia en una instalación temporal; el archivo original queda intacto, SHA-256 verificado antes y después; `reejecutar_calidad.py`):

| Indicador | Antes | Después |
|---|---|---|
| Veredictos | 5 verdes, 1 amarillo, 1 rojo | los mismos, caso por caso |
| Recall@3 | 1.0 | 1.0 |
| Veredicto global | rojo (preexistente: «requisitos para entrar a una maestría» espera abstenerse) | rojo |
| Fragmentos entregados por el Simulador | — | iguales |

**Única diferencia:** el Simulador ya no aplica reranking en los 4 casos que respondían (antes «aplicado», ahora «no aplicado»).

**2. Banco LOTE01** (14 casos con fuente esperada, archivos reales; `calidad_lote01.py`):

| Configuración | Antes | Después | Diferencias |
|---|---|---|---|
| Runtime (sin modelo) | amarillo, Recall@3 1.0 | amarillo, Recall@3 1.0 | **ninguna** |
| Escritorio (con modelo) | **verde** | **amarillo** | una sola: **R2** («¿Qué documentos necesito para entrar al bachillerato?») pasa de fuente esperada en 1.º a 3.º |

- **Por qué cambia R2:** es la consulta del incidente 493c8033. Antes, el Simulador la resolvía gracias al reranking que el Runtime no aplica.
- **Qué muestra ahora:** el resultado real del Runtime (amarillo), igual al del Runtime antes y después.

**No se pudo usar:** `Prueba_A_E2E_Oferta_Academica_UDL.agentproj`. No se importa con ningún código reciente, tampoco con el anterior, porque tiene códigos de caso de prueba duplicados (`UNIQUE constraint failed: test_case.project_id, test_case.code`). Es un problema preexistente del paquete, ajeno a P1, y no se modificó.

**NEXOM debe ejecutar sus propios casos de Calidad** de AGENTE UDL tras actualizar (sección 5, paso 7). `reejecutar_calidad.py` hace la comparación antes/después sobre una copia de su `.agentproj`.

## 5. Instrucciones para actualizar la instalación de NEXOM

1. **Antes de actualizar, identificar proyectos con «Activado».** Con el código anterior, el Runtime los servía sin reranking; ahora exigirá el modelo.
   - **Cómo revisarlo:** en el Simulador de cada proyecto (selector «Reranking en el agente») o con `inspeccionar_instantanea.py` sobre la instantánea publicada (campo `proyecto.agent_reranking = 1`).
   - **AGENTE UDL:** la validación de la Etapa 0 no informó el valor del ajuste. Conviene confirmarlo en `execution.reranking.setting` de cualquier respuesta reciente con `X-API-Key`; si es `automatico`, no se ve afectado.
2. **Detener** la app de escritorio y el Runtime. **Respaldar:**
   - la carpeta de datos (`RAGSTUDIO_HOME`: `application.db`, `projects/`, `snapshots/`, `runtime.db`);
   - el paquete de entrega en uso.
3. **Actualizar el código:**
   - **con git:** en la carpeta de RAG Studio, `git fetch` y `git checkout main` y `git pull`, hasta el commit de esta entrega;
   - **con ZIP:** reemplazar la carpeta de código conservando el entorno virtual y la carpeta de datos.

   En ambos casos, opcionalmente, `python scripts/escribir_build_info.py` para que `/health/details` informe el commit aunque no haya `.git`.
4. **No hay dependencias, migraciones ni reindexación nuevas.** No hace falta `pip install`. Si se reinstala el entorno, usar el mismo `requirements.txt`.
5. **Arrancar el Runtime y verificar:**
   - `GET /health` → `retrieval_pipeline: "r105b"`;
   - `GET /health/details` (con `X-API-Key`) → commit de esta entrega;
   - un mensaje de prueba con `X-API-Key` → `execution.reranking`: `setting = automatico`, `applied = false`, `effective_in_runtime = sin_reranking`, `model_status = no_requerido`.
6. **Si algún proyecto debe usar reranking** (opcional):
   - en el Simulador, elegir «Activado» y publicar una versión nueva;
   - copiar al servidor del Runtime la carpeta del modelo `models--Xenova--ms-marco-MiniLM-L-6-v2` (desde `data/models` de la app de escritorio) a `RAGSTUDIO_HOME/models`, o permitir su descarga desde Hugging Face;
   - comprobar que el mensaje de prueba muestra `applied = true`. Si falta el modelo, el Runtime responderá 503 `configuration.reranking_unavailable` para ese proyecto.
7. **Volver a ejecutar los casos de Calidad** de AGENTE UDL en la pestaña Calidad y comparar con la corrida anterior.
   - **Diferencias esperadas:** solo en consultas en las que el Simulador mejoraba por el reranking, como la del incidente; ahora muestran lo que realmente responde el Runtime.
   - **Comparación automática:** `reejecutar_calidad.py --codigo <código anterior> …` y `--codigo <código nuevo> …` sobre una copia del `.agentproj`, y luego `--comparar`.

## 6. Riesgos residuales

- **Usuarios del Simulador:** verán resultados distintos a los anteriores en proyectos con el predeterminado. Son los del Runtime.
- **Proyectos con «Activado»:** sin el modelo en el servidor dejan de servirse (comportamiento estricto decidido). Se mitiga con el paso 1.
- **La calidad de consultas como la del incidente no mejora con P1:** depende de P2–P4, todavía pendientes.
