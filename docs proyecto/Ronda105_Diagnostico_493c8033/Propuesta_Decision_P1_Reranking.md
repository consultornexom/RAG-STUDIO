# Ronda 105b: propuesta de decisión P1 (configuración efectiva de reranking)

**Estado:** propuesta para decisión de NEXOM. No se implementa nada hasta su autorización expresa.

**Pendientes, sin evaluar ni autorizar:**
- P2 (Y + R con el ajuste de títulos de la Ronda 105);
- P3 (consulta original para el reranker);
- P4 (excluir YAML del índice).

**Incidente 493c8033:** sigue abierto como explicación compatible, no confirmada. Se retira como premisa la afirmación «reranking aplicado» en el incidente, porque NEXOM no tiene evidencia de ella.

## 1. Situación actual (verificada en código, commit `9998926`)

| | Simulador (app de escritorio) | Runtime de RAG Studio (`POST /messages`) |
|---|---|---|
| ¿Se construye el modelo de reranking? | Sí, siempre (`app/bootstrap.py`) | **No, nunca** (`interfaces/api/runtime_context.py`) |
| «Automático» (predeterminado de todo proyecto) | aplica el reranking | no lo aplica |
| «Activado» | aplica | no lo aplica; avisa en `execution.reranking.note` |
| «Desactivado» | no aplica | no aplica |
| Qué significa «disponible» | que el modelo está **configurado**, no que esté descargado | siempre `false` |

**Consecuencias:**
1. **El Simulador no representa al Runtime.** En la configuración predeterminada, lo que se valida en el Simulador (con reranking) no es lo que responde el Runtime (sin reranking). Es la diferencia aceptada en la Ronda 105.
2. **Defecto adicional encontrado al preparar esta propuesta.** En un equipo sin el modelo descargado y sin conexión a internet, el Simulador intenta reordenar con «Automático», no puede cargar el modelo y la simulación **falla** con «No se pudo cargar el modelo de reranking…». Esto ocurre porque el Simulador informa «disponible» aunque el modelo no esté descargado.

## 2. Alternativas

### Alternativa A: el Runtime también aplica reranking

**Comportamiento:**
- El Runtime construye el mismo cross-encoder que el escritorio (`Xenova/ms-marco-MiniLM-L-6-v2`).
- «Automático» y «Activado» aplican el reranking en ambos componentes; «Desactivado» no lo aplica en ninguno.
- Simulador y Runtime quedan iguales **si y solo si** el modelo está presente en ambos equipos.

**Modelos y dependencias:**
- No hay dependencias nuevas de Python: `fastembed` y `onnxruntime` ya se usan para los embeddings.
- Se necesitan los archivos del modelo (≈92 MB) en `RAGSTUDIO_HOME/models` del Runtime:
  - o los descarga de Hugging Face la primera vez, lo que requiere internet en el servidor;
  - o se aprovisionan antes en el paquete de entrega, la imagen Docker o un volumen.
- Hay que confirmar la licencia del modelo para su distribución en el paquete.

**Recursos, medidos en el sandbox de 2 vCPU** (`medicion_reranking.json` de la Ronda 104b):

| | Sin reranking | Con reranking |
|---|---|---|
| Latencia por consulta (p50 / p95) | 39 / 53 ms | 2 271 / 4 189 ms |
| Memoria residente | — | ≈+118 MB por proceso |
| Carga del modelo | — | 0.34 s si ya está descargado |

En la Ronda 40, el consultor midió en su propio equipo +90.6 ms de p50. **La latencia de A depende fuertemente del hardware.** Antes de adoptarla habría que medir en el servidor del cliente (`scripts/benchmark_reranker_latency.py`, o una medición equivalente del Runtime).

**Instalaciones en equipos del cliente:**
- todos los servidores del Runtime necesitan el modelo;
- las instalaciones sin internet requieren aprovisionarlo;
- el paquete de entrega crece unos 92 MB;
- en equipos modestos, el tiempo de respuesta puede pasar de decenas de milisegundos a segundos;
- el consumo de CPU por consulta aumenta, y con ello la capacidad de atender consultas simultáneas disminuye.

**Calidad (14 consultas reales de LOTE01, código actual):**

| Documentos compartidos | Con reranking (MRR) | Sin reranking (MRR) |
|---|---|---|
| `documento_completo` | 1.000 | 0.952 |
| `por_encabezado` | 0.729 | 0.729 |

- En la consulta del incidente, el reranking ayudó en el Simulador (prueba A: 2.º lugar contra ausente).
- **Pero el modelo está entrenado en inglés y su efecto en español es inestable:**
  - Ronda 91: puntajes casi iguales y ruidosos;
  - Ronda 101: «6.º semestre» por encima del «5.º» pedido;
  - Ronda 105: con el texto de búsqueda recortado prefiere el fragmento puente.

**Ventajas:**
- conserva la mejora que hoy se observa en el Simulador;
- no cambia lo que los usuarios ven en el Simulador.

**Desventajas y riesgos:**
- **cambia el orden de las respuestas en producción de todos los proyectos** (todos están en «Automático»);
- más latencia y memoria, y un segundo modelo que hay que versionar y aprovisionar;
- sigue sin resolver el defecto del equipo sin modelo: hay que volverlo explícito;
- un modelo en inglés pasa a decidir el orden en producción.

### Alternativa B: sin reranking por defecto en ambos

**Comportamiento:**
- El predeterminado («Automático», que hoy tienen todos los proyectos) pasa a significar **sin reranking** en el Simulador y en el Runtime.
- **El Runtime no cambia nada:** ya opera así.
- **El Simulador deja de reordenar** en los proyectos con el predeterminado, y pasa a mostrar exactamente lo que respondería el Runtime.
- «Desactivado»: igual que hoy.
- «Activado» queda como **opción explícita por proyecto**. Su comportamiento en el Runtime es una subdecisión (sección 3).

**Modelos y dependencias:** ninguno adicional en el Runtime. El escritorio conserva el modelo para:
- el Laboratorio (casilla «Reranking real»);
- los proyectos con «Activado».

**Recursos:**
- el Runtime, sin cambios: decenas de milisegundos en el sandbox;
- el Simulador, más rápido en los proyectos con el predeterminado.

**Instalaciones en equipos del cliente:**
- **ningún requisito nuevo;**
- se elimina la falla del Simulador sin internet en los proyectos con el predeterminado.

**Calidad:**
- La de producción no cambia.
- **El Simulador deja de mostrar una calidad que producción no tiene.** Para la consulta del incidente, el Simulador pasará a mostrar el resultado de la prueba B (documento ausente): es el comportamiento real del Runtime. La mejora de esa consulta deberá venir de P2–P4 y del contenido, evaluada con el Simulador y el Runtime en la misma configuración.

**Ventajas:**
- configuración efectiva igual en pruebas y despliegue, sin requisitos de infraestructura;
- producción no cambia;
- reproducible (un solo modelo, el de embeddings) y verificable con la trazabilidad de la Etapa 0;
- elimina la dependencia de un modelo en inglés en el camino conversacional.

**Desventajas y riesgos:**
- los usuarios verán en el Simulador resultados distintos a los de hoy (los reales del Runtime): hay que comunicarlo;
- se pierde la mejora del reranking en casos donde ayudaba, aunque en producción nunca existió;
- los casos de prueba de Calidad validados con el Simulador y reranking podrían cambiar de resultado: conviene volver a ejecutarlos.

## 3. Subdecisión dentro de B: qué hace el Runtime con un proyecto en «Activado»

| Opción | Comportamiento | Valoración |
|---|---|---|
| **B-estricta** (recomendada) | **Al publicar:** RAG Studio advierte que el Runtime necesitará el modelo. **Al cargar la instantánea:** si el Runtime no tiene el modelo, rechaza servir ese proyecto con un error explícito (503 `configuration.reranking_unavailable`, visible en `/health/details` y en `runtime.db`). Si lo tiene, lo aplica (A solo para ese proyecto) | Coherente por construcción: o se aplica en ambos o no se sirve. Requiere que el Runtime **pueda** construir el modelo cuando un proyecto lo pide |
| B-aviso | El Runtime sirve sin reranking y lo indica en `execution.reranking.note` y en `/health/details` (como hoy) | Más tolerante, pero vuelve a permitir una diferencia silenciosa entre pruebas y despliegue para quien no lea la nota |

## 4. Recomendación

**Alternativa B, con «Activado» en modalidad B-estricta**, más dos medidas de verificabilidad que valen para cualquier alternativa:

1. **Disponibilidad real, no configurada.** «Modelo disponible» = el modelo se cargó, comprobándolo al arrancar o en la primera carga. Si un proyecto exige reranking y el modelo no carga, el error es explícito antes de responder, en el Simulador y en el Runtime. No se degrada en silencio ni falla a mitad de la simulación.
2. **Configuración efectiva visible antes de probar.**
   - El Simulador muestra junto al selector «Configuración efectiva en el Runtime: sin reranking / con reranking (requiere modelo en el servidor)».
   - El reporte de cada simulación indica si coincide con lo que haría el Runtime.
   - La trazabilidad de la Etapa 0 (`execution.reranking`) permite comprobarlo en cada respuesta real.

**Motivos:**
- **Producción no cambia:** se evita una reordenación masiva no evaluada.
- **No impone requisitos nuevos** a las instalaciones del cliente.
- **El Simulador pasa a predecir el Runtime,** que es la condición para que las pruebas de NEXOM sean válidas.
- **El reranking se convierte en una decisión explícita por proyecto,** que solo puede activarse donde el despliegue lo soporte y tras medir su latencia en el hardware real.
- **No se toma el reranking como corrección del incidente.** La mejora de calidad se evaluará con P2–P4 en la configuración que realmente usa producción.

**Si NEXOM prefiere A:** antes de autorizarla debería
- medir latencia y memoria en el servidor real;
- definir cómo se aprovisiona el modelo sin internet;
- aceptar que cambia el orden de todas las respuestas en producción, con una evaluación previa del conjunto ampliado (Ronda 105, sección 10).

## 5. Alcance de una implementación de B (para autorización posterior)

**Archivos previstos:**
- `application/conversational/queries/simulate_conversation.py` (`_reranking_decision`: el predeterminado = sin reranking; «Activado» exige modelo cargado);
- `interfaces/api/runtime_context.py` (construir el reranker solo si algún proyecto servido tiene «Activado»; verificar carga; error explícito);
- `infrastructure/rerankers/fastembed_cross_encoder.py` (comprobación de carga);
- `ui/conversational/panel.py` (etiquetas del selector y «configuración efectiva en el Runtime»);
- publicación y paquete de entrega (advertencia cuando un proyecto tiene «Activado»);
- Manual 8.5;
- `RETRIEVAL_PIPELINE` pasa a un identificador nuevo, porque cambia el orden del Simulador.

**Sin cambios:** documentos, fragmentos, metadatos, índices ni migraciones. `project.agent_reranking` conserva sus valores; solo cambia el significado del valor nulo (predeterminado).

**Pruebas:**
- Simulador y Runtime dan el mismo orden y la misma `execution.reranking`, en las tres configuraciones, sobre la misma instantánea (prueba E2E);
- «Activado» sin modelo → error explícito en ambos;
- «Activado» con modelo → aplicado en ambos;
- en el Runtime, las 28 consultas de LOTE01 dan el mismo orden antes y después: el Runtime no debe cambiar;
- el Simulador con el predeterminado da el mismo orden que el Runtime;
- volver a ejecutar los casos de Calidad existentes e informar las diferencias.

**Riesgos de la implementación:**
- el cambio visible en el Simulador (comunicación a usuarios);
- proyectos que ya tengan «Activado»: se identificarán y se informarán antes de aplicar el cambio.
