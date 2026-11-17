# Ronda 104: fragmentos «puente» por encima de los requisitos (diagnóstico)

**Caso (NEXOM, instantánea v2, Runtime, trace `493c8033-…`).** Consulta: «¿Qué documentos necesito para entrar al bachillerato?».
- Intención correcta: `consultar_requisitos_bachillerato`, confianza 0.887.
- Los dos primeros resultados son fragmentos «Información compartida aplicable a este plantel» de los planes. Solo remiten a `requisitos_ingreso.md`.
- El fragmento con los requisitos reales queda fuera del top 5.

**Alcance.** Diagnóstico sin cambios en el motor.
- **Reproducción:** `diagnostico_puentes.py`, con los cinco archivos reales de LOTE01, los modelos reales y el motor real.
- **Medición de alternativas:** `prototipo_alternativas.py`, sobre las 14 consultas de la Ronda 102.
- **Limitaciones:** no se tiene la instantánea v2 ni el registro del trace. Las intenciones y metadatos son los de la evaluación de la Ronda 102 (supuestos).

## 1. Hallazgos previos (afectan la reproducibilidad)

### 1.1 El Runtime de RAG Studio nunca aplica reranking

`interfaces/api/runtime_context.py` construye su `RagService` **sin reranker**, así que `has_reranker` es False en `POST /messages`.
- **Escritorio:** el Simulador, en cambio, sí tiene modelo y por defecto reordena (el ajuste «Automático» de la Ronda 102).
- **Consecuencia:** la misma consulta puede ordenarse distinto en el Simulador (con reranking) y en el Runtime (sin reranking).
- **Documentación incorrecta:**
  - la nota de la Ronda 46 en el Manual (8.5) dice que el motor «en producción» siempre usa reranking si hay modelo, y no es así en el Runtime;
  - lo que escribí en la Ronda 102 sobre el ajuste «Reranking en el agente» aplicado al canal de mensajes es, por la misma razón, incorrecto. En el Runtime, «Activado» no tiene efecto y solo genera el aviso de que no hay modelo.

### 1.2 Lo que observó NEXOM coincide con el código ANTERIOR a la Ronda 102

Con el código anterior a la Ronda 102 y sin reranking (como opera el Runtime), la reproducción da exactamente el patrón reportado:

1. HM «Información compartida aplicable a este plantel»;
2. TL «Información compartida aplicable a este plantel»;
3. TL «Procedencia»;
4. HM «Procedencia»;
5. HM «Información general».

Requisitos queda fuera del top 5.

Con el código de la Ronda 102 (`3621dd5`) y los compartidos como `documento_completo`, en cambio, `requisitos_ingreso.md` sube al 3.º y los puentes salen del top 5.

**Hay que confirmar** con qué versión de RAG Studio corre el Runtime que sirve la v2. Hoy no se puede saber desde fuera: ni `/health` ni la respuesta informan la versión del código. Esto se propone corregir (punto 5.4).

## 2. Por qué gana el puente aunque la intención sea correcta (pregunta 1)

**La intención no es una señal de recuperación.** Solo interviene a través de la afinidad de título (Rondas 91 y 102). Los puentes tienen afinidad 0, y entre fragmentos de afinidad 0 manda el orden de la búsqueda. En la búsqueda, el puente gana en todas las señales.

**Señales medidas con el texto que usa el Simulador.** El texto es «¿Qué documentos necesito para entrar ?»: el motor ya quitó «bachillerato», que es el valor filtrado.

| Señal | Puentes HM / TL | Requisitos (documento_completo) | Requisitos (por_encabezado, sección «Contenido») |
|---|---|---|---|
| Semántica | 1.º / 2.º | 11.º | 3.º |
| Textual (BM25) | 1.º / 2.º | fuera de los 40 | fuera de los 40 |
| Reranker (si se aplica) | −3.6 | −8.7 | −10.7 |
| Pool híbrido sin reranking | 1.º / 2.º | 13.º | 5.º |

**Causas generales (ninguna es específica de UDL):**

1. **Brecha de vocabulario.**
   - **Lo que dice la lista de requisitos:** enumera acta de nacimiento, certificado, CURP y fotografías. Nunca usa las palabras «documentos», «entrar» ni «necesito».
   - **Lo que dice el puente:** «La aplicabilidad de esos **documentos** compartidos…» y «requisitos_ingreso.md — requisitos de ingreso». Coincide en BM25 por una palabra accidental y se parece semánticamente a «qué documentos».
2. **Fragmento largo y diluido.** Con `documento_completo`, el fragmento de requisitos incluye el encabezado YAML, el ámbito y la procedencia. Su vector se aleja de la pregunta: queda 11.º en la lista semántica.
3. **Texto de búsqueda empobrecido.** Al quitar «bachillerato» (pendiente señalado en la Ronda 102), la consulta se queda sin ancla de dominio. Con la consulta original, Búsqueda RAG pone requisitos en 2.º (`por_encabezado`) o 6.º (`documento_completo`).
4. **El reranker no ayuda.** El cross-encoder (`ms-marco-MiniLM`, entrenado en inglés) puntúa mejor a los puentes. Además, en el Runtime no se aplica (1.1).

**Efecto lateral de C2 (Ronda 102).** El fragmento que solo contiene el encabezado YAML de cada documento no tiene título ni encabezado. Por C2 toma el título de la fuente («bachillerato_torres_landa», «requisitos_ingreso»), que coincide con la intención, y sube al top 5 sin aportar contenido. Es un defecto a corregir (5.1).

## 3. ¿Puede el reranking reconocer referencias? (pregunta 2)

No de forma fiable:
- un cross-encoder puntúa cada par (consulta, fragmento) por separado y no ve el contenido del documento al que remite el puente;
- el modelo actual es en inglés;
- en el Runtime no se aplica.

**Propuesta:** resolver la referencia de forma determinista, antes del orden final (5.2), en lugar de esperarlo del reranker.

## 4. Expansión y penalización de fragmentos índice (preguntas 3 y 4)

**Penalizar en absoluto los fragmentos que solo remiten a otro documento no es conveniente.** A veces son la única evidencia, por ejemplo ante «¿dónde consulto los requisitos?». Es mejor **colocarlos detrás de su destino** cuando el destino está disponible. Eso es lo que hace la resolución de referencias (5.2).

**Alternativas medidas.** Posición del fragmento correcto en el top 5 final; 14 consultas; Runtime = sin reranking.

| Variante | Compartidos `documento_completo`: MRR / R2 | Compartidos `por_encabezado`: MRR / R2 |
|---|---|---|
| Código actual (Ronda 102) | 0.952 / 3.º | 0.729 / fuera |
| Y: YAML sin afinidad | 0.964 / 1.º | 0.848 / 5.º |
| R: resolución de referencias | **1.000 / 1.º** | 0.752 / 4.º |
| Y + R | **1.000 / 1.º** | 0.917 / 1.º |
| P: afinidad heredada de encabezados superiores | 0.893 / fuera | 0.952 / 3.º |
| Y + P + R | 0.964 / 1.º (R1 baja a 2.º) | **1.000 / 1.º** |

**Con reranking:**
- `documento_completo`: código actual y Y + R / Y + P + R, todas las consultas en 1.º.
- `por_encabezado`: código actual en 0.457 (requisitos, compartidos e información general); con Y + P + R, todo en 1.º salvo R2, que sigue fuera.

**Detalle de R2 con reranking y `por_encabezado`.** El «mejor fragmento» del documento referido, para «qué documentos necesito», es «Procedencia» (habla de «documento derivado») y no «Contenido». Es la misma brecha de vocabulario de la sección 2.

**En ninguna variante se pierden** planes, ordinales ni información general: siguen en 1.º.

**Lectura de los resultados:**
- **R funciona cuando el documento referido es un solo fragmento** (`documento_completo`). Con fragmentación por encabezado depende de elegir bien la sección del destino.
- **P ayuda con `por_encabezado` pero perjudica con `documento_completo`.** La causa es que el título raíz de los planes («Bachillerato — Plantel …») coincide con el nombre de la intención `consultar_requisitos_bachillerato`.
  - Ese nombre está en snake_case y el enmascarado de valores de catálogo no lo reconoce. Es otro detalle a corregir antes de considerar P.
- **Ninguna variante corrige del todo la brecha de vocabulario con fragmentos pequeños.** Eso depende también del contenido (5.5).

## 5. Propuesta (pendiente de autorización)

1. **Y. Fragmentos con solo encabezado YAML: afinidad 0.**
   - Corrige el efecto lateral de C2.
   - Es pequeño, general y sin riesgo para el contenido.
2. **R. Resolución de referencias entre fuentes.**
   - **Cuándo se aplica:** a un candidato corto (≤ 80 palabras sin YAML) que menciona el título o nombre de archivo de **otra fuente permitida por los filtros** del proyecto.
   - **Qué hace:** trae el mejor fragmento con contenido de esa fuente para la consulta y lo coloca justo antes del fragmento puente. El puente se conserva detrás.
   - **Por qué es general:** se basa en los títulos de las fuentes registradas, no en listas fijas. Respeta filtros, vigencia y nivel de acceso: solo busca dentro de las fuentes permitidas, igual que la búsqueda normal.
   - **Trazabilidad:** el trazado dice «traído por referencia desde <fuente>».
   - **Alcance:** se aplica en el Simulador y en el Runtime por igual.
3. **Coherencia del reranking entre Simulador y Runtime (decisión de NEXOM).** Opciones:
   - (a) construir el reranker también en el Runtime, para que el ajuste de la Ronda 102 signifique lo mismo en ambos. Costo: latencia y modelo en el paquete de entrega;
   - (b) que «Automático» signifique «sin reranking» en ambos, y que el Simulador avise.

   Además, corregir la nota del Manual (8.5) y la de la Ronda 102.
4. **Versión verificable.** `/health` y la respuesta de `/messages` informarían la versión del código de RAG Studio y si se aplicó reranking. Así, un trace basta para reproducir.
5. **Pendientes que se miden después, no se implementan ahora:**
   - **P**, tras corregir el enmascarado de los nombres de intención en snake_case;
   - el texto de búsqueda empobrecido al quitar el valor filtrado (Ronda 102).
   - **Recomendación editorial para RAG CONTENT STUDIO, no del motor:** que las secciones de requisitos usen el vocabulario de las preguntas (p. ej., un encabezado «Documentos requeridos»). Si los documentos compartidos se fragmentan por encabezado, evitar que su contenido quede separado del título del documento.

**Pruebas previstas:**
- la consulta de NEXOM con requisitos en el top 3 y por delante de los puentes, con los archivos reales, en `documento_completo` y `por_encabezado`, con y sin reranking;
- puentes que siguen apareciendo detrás de su destino;
- una referencia a una fuente excluida por filtros, que no se trae;
- un fragmento YAML sin afinidad;
- las regresiones de las Rondas 91 y 100 a 102;
- la misma decisión en el Simulador y en `POST /messages`.

## 6. Información que conviene que NEXOM confirme

1. La versión o commit de RAG Studio con la que corre el Runtime que sirve la v2, y con la que se publicó la v2.
2. La estrategia de fragmentación de `requisitos_ingreso.md`, `areas_formacion.md` y `cualidades_aspirante.md` en la v2 (`documento_completo` o `por_encabezado`).
3. Si es posible, el `.agentproj` de la v2 o el registro del trace `493c8033-…`. Con eso se repite el caso exacto en lugar de la reproducción con supuestos.
