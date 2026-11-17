# Ronda 102: resultados de C1, C2 y C4 (Simulador)

Autorización de NEXOM: C1, C2 y C4. C3 y C5 quedan documentadas como pendientes. El diagnóstico previo está en `Diagnostico_Simulador_Requisitos.md`.

**Validación con los cinco archivos reales de LOTE01_Bachillerato.**
- Archivos: los entregó NEXOM con `manifiesto.csv`. Se copiaron a `tests/fixtures/lote01_bachillerato/` con su nombre real.
- Integridad: el SHA-256 coincide con el manifiesto, y una prueba lo verifica.
- Carga: los documentos se cargan tal cual, con su encabezado YAML. No se modificó su estructura ni sus metadatos (condición 6).

## 1. Qué mostró LOTE01 real que el corpus sintético no mostraba

- **Encabezado YAML como título.** Los cinco documentos empiezan con un encabezado YAML (`---`). Con `documento_completo`, el título que el Simulador usaba para la afinidad era la primera línea, es decir, **«---»**. Los tres documentos compartidos tenían afinidad **cero** con cualquier intención.
- **Qué pasaba entonces.** Quedaban detrás de cualquier sección de los planes cuyo título tuviera alguna afinidad, o, sin afinidad para nadie, en el orden de la búsqueda.
- **La sección que compite en la búsqueda.** En los planes reales, la sección que remite a los compartidos es «Información compartida aplicable a este plantel» (no «Requisitos de ingreso»). La búsqueda la pone muy arriba porque menciona literalmente `requisitos_ingreso.md — requisitos de ingreso`.

## 2. Cambios

- **C1 (`combine_with_retrieval`, `domain/conversational/section_affinity.py`).**
  - **Cómo se combina.** El orden final fusiona por RRF (k = 60, el mismo de la búsqueda híbrida) dos listas en partes iguales: el puesto en la búsqueda y el puesto por afinidad (solo fragmentos con afinidad > 0; los empates comparten puesto).
  - **A igual resultado:** se conserva el orden de la búsqueda.
  - **Qué cambia respecto de antes.** Antes, la afinidad era la clave principal y la búsqueda solo desempataba. Ahora, entre fragmentos con afinidad, un mejor puesto en la búsqueda compensa un peor puesto de afinidad.
  - **Qué se conserva (Ronda 91).** Los fragmentos sin ninguna afinidad de título siguen quedando detrás de los que sí la tienen.
- **C2 (`affinity_title`).** Cuando un fragmento no tiene título de sección, el título para la afinidad se elige en este orden:
  1. el primer encabezado Markdown, saltando el bloque YAML inicial;
  2. si no tiene, el título de la fuente sin extensión;
  3. si no hay nada, cadena vacía (afinidad 0).

  Se aplica a cualquier estrategia: `documento_completo`, `por_tamanio` o el preámbulo de `por_encabezado`. Los fragmentos con `section_title` no cambian.
- **C4 (reranking en el agente).**
  - **Ajuste:** `Project.agent_reranking` (migración de proyecto **0024**, columna nullable, sin backfill). Valores: `None` = Automático (predeterminado, el comportamiento anterior), `True` = Activado, `False` = Desactivado.
  - **Dónde se edita:** selector «Reranking en el agente» en el Simulador.
  - **Corrección (2026-11-17, Ronda 104b):** lo que sigue sobre el canal de mensajes era incorrecto: el Runtime de RAG Studio se construye sin modelo de reranking, de modo que en `POST /messages` el reranking nunca se aplica, sea cual sea el ajuste (con «Activado» lo avisa en `execution.reranking.note`). Ver el Manual 8.5 y `docs proyecto/Ronda104_Etapa0_Trazabilidad/`.
  - **Quién lo usa:**
    - el Simulador;
    - el canal de mensajes `POST /messages`, que lo lee de la instantánea publicada mediante `ProjectAgentRerankingReader`. Un cambio llega al canal al publicar una versión nueva.
  - **Qué muestra el trazado:**
    - si se aplicó y qué modelo intervino (`reranking_applied`, `reranking_model`, `reranking_setting`);
    - un aviso si está Activado sin modelo (`reranking_note`).
- **Separación de métricas en el propio Simulador.** `SimulationTrace.result_ordering` da, para cada fragmento entregado:
  - su puesto en la recuperación inicial;
  - su afinidad;
  - el título con que se midió.

  El reporte lo muestra así: «búsqueda #2; afinidad 0.86 con «Requisitos de ingreso»».

## 3. Evaluación con LOTE01 real (`evaluacion_simulador.py`)

**Corpus y configuración de la evaluación.**
- Casos: 14 consultas en cinco grupos:
  - requisitos (3);
  - compartidos: áreas y cualidades (2);
  - información general y RVOE (3);
  - planes por semestre y área (4);
  - ordinales «5.º» y «6to» (2).
- Etapas medidas por separado, como pidió NEXOM:
  - **lab:** Búsqueda RAG, consulta original, sin filtros;
  - **pool:** recuperación inicial del Simulador (texto de búsqueda y fuentes filtradas, 20 candidatos);
  - **final:** top 5 tras el reordenamiento conversacional.
- **Supuestos, por no tener el `.agentproj` de NEXOM:**
  - **intenciones:** las cuatro activas del proyecto histórico de Bachillerato (textos reales), más `consultar_plan_estudios` (supuesta);
  - **metadatos:** `nivel_academico` (obligatoria) y `plantel` (opcional, de varios valores);
  - **políticas:** planes `por_encabezado` 500/60/80 y compartidos `documento_completo`.

**Métricas de fragmento correcto: R@1 / R@3 / MRR.** lab y pool son idénticos antes y después: la recuperación no cambió.

| Reranking | Grupo | lab | pool (recuperación inicial) | final ANTES | final DESPUÉS |
|---|---|---|---|---|---|
| con reranking | todos | 0.79 / 0.86 / 0.83 | 0.71 / 0.86 / 0.80 | 0.79 / 0.93 / 0.85 | **1.00 / 1.00 / 1.00** |
| con reranking | requisitos | 0.33 / 0.33 / 0.42 | 0.33 / 0.67 / 0.57 | 0.33 / 0.67 / 0.51 | **1.00 / 1.00 / 1.00** |
| con reranking | compartido | 0.50 / 1.00 / 0.67 | 0.50 / 1.00 / 0.67 | 0.50 / 1.00 / 0.67 | **1.00 / 1.00 / 1.00** |
| con reranking | general | 1.00 / 1.00 / 1.00 | 0.67 / 0.67 / 0.72 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |
| con reranking | plan | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |
| con reranking | ordinal | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |
| sin reranking | todos | 0.64 / 0.86 / 0.77 | 0.64 / 0.93 / 0.77 | 0.64 / 0.86 / 0.76 | **0.93 / 1.00 / 0.95** |
| sin reranking | requisitos | 0.00 / 0.33 / 0.25 | 0.00 / 0.67 / 0.30 | 0.00 / 0.33 / 0.25 | **0.67 / 1.00 / 0.78** |
| sin reranking | compartido | 1.00 / 1.00 / 1.00 | 0.00 / 1.00 / 0.42 | 0.00 / 1.00 / 0.42 | **1.00 / 1.00 / 1.00** |
| sin reranking | general | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |
| sin reranking | plan | 0.75 / 1.00 / 0.88 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |
| sin reranking | ordinal | 0.50 / 1.00 / 0.75 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |

**Dónde se perdía y dónde se sigue perdiendo relevancia.** Posiciones del fragmento correcto; «–» significa que estaba fuera del top 5.

| Caso | Reranking | lab | pool | final antes | final después |
|---|---|---|---|---|---|
| R1 (consulta de NEXOM) | con | 1 | 1 | 1 | 1 |
| R1 (consulta de NEXOM) | sin | 2 | 2 | 2 | **1** |
| R2 «¿Qué documentos necesito para entrar al bachillerato?» | con | 5 | 5 | 5 | **1** |
| R2 | sin | 6 | **13** | – | **3** |
| R3 «Requisitos de ingreso … plantel Torres Landa» | con | 14 | 2 | 3 | **1** |
| R3 | sin | 14 | 3 | 4 | **1** |
| S1 áreas | con | 3 | 3 | 3 | **1** |
| S1 áreas | sin | 1 | 3 | 3 | **1** |
| S2 cualidades | sin | 1 | 2 | 2 | **1** |
| Resto (G1, G2, O1, P1–P6) | con / sin | — | — | 1 | 1 (ninguno empeora) |

**Lectura de los resultados.**
- **Reordenamiento (antes de esta ronda).** Era donde se perdía relevancia: con títulos «---» y la afinidad como clave principal, los documentos compartidos quedaban por debajo de secciones de los planes.
- **Recuperación inicial (sigue igual, fuera del alcance de C1, C2 y C4).** En R2 sin reranking el pool baja de 6 (lab) a 13. Al quitar «bachillerato» (valor filtrado) del texto de búsqueda, la consulta queda casi sin términos de contenido («¿Qué documentos necesito para entrar al?»), y el preámbulo YAML de los planes sube. Aun así, el resultado final mejora de fuera del top 5 a 3.º.

**Contribución de cada corrección (ablación con los mismos candidatos).** Posición final del fragmento correcto en los casos afectados.

| Configuración | R1 sin | R2 con | R2 sin | R3 con / sin | S1 con / sin | S2 sin |
|---|---|---|---|---|---|---|
| Antes | 2 | 5 | – | 3 / 4 | 3 / 3 | 2 |
| Solo C1 | 2 | 5 | – | 3 / 4 | 3 / 3 | 2 |
| Solo C2 | 1 | 1 | 1 | 1 / 1 | 1 / 1 | 1 |
| C1 + C2 (implementado) | 1 | 1 | 3 | 1 / 1 | 1 / 1 | 1 |

**Qué muestra la ablación.**
- **En LOTE01 real, C2 es la que resuelve.**
- **C1 protege de otro patrón,** el del diagnóstico sintético: secciones tituladas exactamente como la intención que solo remiten al archivo.
  - Antes de esta ronda: `requisitos_ingreso.md` quedaba **3.º**.
  - Con C1 + C2: **1.º**.
  - Con un título poco descriptivo («Universidad de León — Servicios Escolares»): antes **3.º**, ahora **1.º**.
- **Costo de C1 en LOTE01 real:** R2 sin reranking queda 3.º en vez de 1.º (con solo C2). La afinidad ya no puede subir un fragmento desde el puesto 13 de la búsqueda hasta el primero.

## 4. Regresión

**Pruebas.**
- **Ronda 91:** `test_simulate_conversation_variables.py::test_con_filtro_se_ponen_primero_las_secciones_afines_a_la_intencion` y `test_section_affinity.py`.
- **Rondas 100 y 101:** `test_contexto_jerarquico.py` (11) y `test_hierarchy_retrieval.py`.
- Todas pasan. La búsqueda híbrida y el reranking no se modificaron: lab y pool dan posiciones idénticas antes y después en los 28 casos.

**Pruebas nuevas.**
- `tests/unit/domain/test_section_affinity.py` (+5): C1 y C2, incluido el caso sintético de NEXOM y el de la Ronda 91.
- `tests/unit/application/test_simulate_conversation_ronda102.py` (8): ajuste de reranking ×4 combinaciones, aviso sin modelo, comportamiento anterior sin ajuste, trazado de orden, título de la fuente.
- `tests/unit/application/test_project_service.py` (+4) y `tests/integration/test_project_repository.py` (+1): persistencia y lector del ajuste.
- `tests/unit/ui/test_simulador_reranking_ronda102.py` (2): selector y reporte.
- `tests/integration/test_ronda102_lote01_simulador.py` (5), **con los cinco archivos reales y los modelos reales**:
  - integridad de los archivos;
  - la consulta de NEXOM con `requisitos_ingreso.md` en 1.º, con y sin reranking;
  - ocho casos de información general, planes, ordinales y compartidos, con y sin reranking.

  Con el código anterior, esta prueba falla.

**Totales.**
- `tests/unit` + smoke: 1142 pasadas. Siguen las 2 fallas preexistentes de `test_metadata_conversational_field_refresh.py`.
- Integración: 566 pasadas, 0 fallidas. `test_fastembed_image_provider.py` no se ejecutó (descarga de modelo).
- `ruff`: 14 hallazgos, los mismos históricos de `docs proyecto`.
- `mypy`: sin errores nuevos (mismo total que el código anterior con la misma invocación).

## 5. Posibles regresiones y riesgos

1. **Un fragmento con alta afinidad de título pero mal puesto en la búsqueda sube menos que antes.**
   - **Efecto:** un apartado como el de la Ronda 91 sube si está razonablemente arriba en la búsqueda. Si está, por ejemplo, en el puesto 15, y hay varios fragmentos con alguna afinidad mejor recuperados, ya no llega al 1.º.
   - **En los datos medidos:** no ocurrió en LOTE01 ni en las pruebas de la Ronda 91. El caso más cercano es R2 sin reranking (3.º).
2. **Afinidad cero sigue quedando detrás.** Un fragmento sin ninguna afinidad de título sigue quedando detrás de cualquiera con afinidad (comportamiento de la Ronda 91 que C1 conserva). Si NEXOM prefiere atenuarlo, es materia de C3.
3. **Fragmentos que antes no tenían título.** Con C2, el preámbulo y los fragmentos de `por_tamanio` sin encabezado toman el título de la fuente. Si el nombre del archivo comparte palabras con una intención (por ejemplo, `requisitos_ingreso.md`), ese fragmento gana afinidad. Es el efecto buscado en documentos compartidos.
4. **Cambio de comportamiento por ajuste.** C4 no cambia nada por defecto. Al desactivar el reranking en un proyecto, el canal de mensajes cambia solo cuando se publica una versión nueva.
5. **Alcance de C4.** El NEXOM Knowledge Package no transporta el ajuste: no forma parte del contrato v1.0.0. NEXOM Runtime debe definir su propia política de reranking.

## 6. Pendientes

- **C3** (afinidad por cobertura de las raíces distintivas de la intención) y **C5** (señal de evidencia insuficiente: fragmentos que solo remiten a otro archivo). Siguen documentadas en el diagnóstico, para evaluar con evidencia real.
- **Pérdida en la recuperación inicial** al quitar el valor filtrado (R2 sin reranking: lab 6 → pool 13). No forma parte de C1, C2 ni C4. Se propone evaluarla junto con C3.
- **Validación en el proyecto real de NEXOM.** Se validó con los cinco archivos reales, pero con intenciones, metadatos y políticas supuestas. Antes de cerrar, NEXOM debe repetir la consulta en su proyecto LOTE01. El Simulador muestra ahora, para cada fragmento, el puesto en la búsqueda y la afinidad, lo que permite comparar directamente con esta evaluación.
- **Proyectos existentes:** se migran solos a la 0024 al abrirlos. No hace falta reindexar ni volver a fragmentar: C1 y C2 se calculan al consultar.

## 7. Archivos

- **Código:**
  - `domain/conversational/section_affinity.py`;
  - `application/conversational/queries/simulate_conversation.py`;
  - `application/conversational/service.py`;
  - `application/rag/service.py` y `application/rag/queries/hybrid_search.py` (solo `reranker_model_name`);
  - `domain/projects/entities.py`;
  - `application/projects/service.py` y `application/projects/commands/update_agent_reranking.py`;
  - `infrastructure/database/models.py` y `infrastructure/database/repositories.py`;
  - `migrations/project/versions/0024_project_agent_reranking.py`;
  - `app/bootstrap.py` e `interfaces/api/runtime_context.py`;
  - `ui/conversational/panel.py`.
- **Evaluación:**
  - `evaluacion_simulador.py`;
  - `resultados_lote01_antes.json` y `resultados_lote01_despues.json`;
  - `diagnostico_simulador.py` (sintético).
- **Manual:** 8.2 (cómo se elige el apartado) y 8.5 (Reranking en el agente).
