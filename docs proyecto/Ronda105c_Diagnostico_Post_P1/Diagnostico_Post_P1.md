# Ronda 105c: diagnóstico posterior a P1 (UDL-BACH-003 y consulta de documentos)

**Alcance:** diagnóstico sin cambios de código, documentos, índice ni casos de Calidad. P1 (alternativa B estricta) no se altera.

**Evidencias:**
- **[OBS]** observaciones de NEXOM: corrida `085fe5a5-…`, tabla de UDL-BACH-003 y descripción de la consulta de documentos.
- **[EXP]** experimento reproducible `experimento_post_p1.py`:
  - cinco archivos reales de LOTE01, modelos reales y procedimiento r105b sin reranking;
  - intenciones y metadatos supuestos (no se tiene el `project.db` de AGENTE UDL);
  - dos estrategias para los documentos compartidos (`documento_completo` y `por_encabezado`);
  - salidas en `salida_detalle.txt` y `resultados_variantes.json`.
- **[COD]** verificado en el código.

## 1. Conclusiones

1. **La regresión de UDL-BACH-003 no es un cambio de comportamiento del Runtime: es el Simulador mostrando por primera vez lo que el Runtime siempre respondió.**
   - **[COD]** El Runtime nunca aplicó reranking. Con P1, el orden del Runtime antes y después es idéntico (14/14, Ronda 105b).
   - **[EXP]** La corrida verde del 13 de noviembre se obtuvo en el Simulador **con** reranking. Con el texto de búsqueda recortado, el cross-encoder pone a `requisitos_ingreso.md` en primer lugar (puntaje +4.1, Ronda 104). Eso nunca ocurrió en producción.
2. **UDL-BACH-003 y la consulta de documentos comparten una causa y la segunda tiene además otra propia.**
   - **Causa común (A):** fragmentos sin contenido —el encabezado YAML de cada documento— reciben afinidad de título y, por la regla de combinación de la Ronda 102, pasan por delante de fragmentos con el contenido. En la consulta de documentos aparece además el puente.
   - **Causa propia de la consulta de documentos (B):** los fragmentos puente («Información compartida aplicable a este plantel») ganan la búsqueda (brecha de vocabulario, Ronda 105).
   - **A afecta a ambas consultas; B solo a la de documentos.**
3. **Siguiente corrección recomendada: P2a (Y).** Es la más pequeña, general, no toca el índice y resuelve la causa A.

   **[EXP]** En la reproducción corrige UDL-BACH-003 en las dos estrategias de fragmentación. La consulta de documentos necesita además P2b (R) cuando los compartidos están fragmentados por encabezado.

## 2. Mecanismo de la combinación RRF (pregunta 3) [COD]

Orden final (Ronda 102, `combine_with_retrieval`):

> puntaje = 1/(60 + puesto en la búsqueda) + 1/(60 + puesto por afinidad)

**Cómo se calcula el puesto por afinidad:**
- solo cuentan los fragmentos con afinidad > 0;
- los que tienen la misma afinidad comparten puesto;
- los demás no suman nada.

**Propiedades:**
- **P-a.** Un fragmento con afinidad > 0 suma al menos 1/80 ≈ 0.0125 por afinidad. Por eso pasa por delante de **cualquier** fragmento sin afinidad, aunque este sea el 1.º de la búsqueda. Es el comportamiento heredado de la Ronda 91.
- **P-b.** Entre dos fragmentos con afinidad, ser 1.º en afinidad y no 2.º vale lo mismo que subir 1 puesto en la búsqueda (1/61 − 1/62 ≈ 0.00026). Por eso el puesto de afinidad no compensa una distancia de 2 o más puestos en la búsqueda.

**Aplicado a UDL-BACH-003 [OBS + COD].**
- **Puestos de afinidad:** la de `requisitos_ingreso.md` es 0.57 (1.º) y la de Torres Landa 0.18 (2.º, si no hay otra afinidad intermedia).
- **Consecuencia (P-b):** que Torres Landa quede primero implica que estaba **al menos 2 puestos por delante** en la búsqueda (p. ej. Torres Landa 1.º y requisitos 3.º).
- **Cómo confirmarlo:** el reporte del Simulador indica, junto a cada fragmento, «búsqueda #k; afinidad x con «título»». Esos dos datos de la corrida confirmarían o corregirían esta deducción.
- **Indicio de la causa A [EXP]:** en la reproducción, el único fragmento de Torres Landa con afinidad cercana (0.20) es **el fragmento que solo contiene el encabezado YAML**. Su título para la afinidad es el nombre de archivo «bachillerato_torres_landa» (regla C2 de la Ronda 102), y la raíz «bachi» coincide con el nombre de la intención `consultar_requisitos_bachillerato`. Si en la corrida real el título mostrado es «bachillerato_torres_landa», la causa A queda confirmada para este caso.

**Valores reproducidos** (salida_detalle.txt, sin reranking):

| Consulta, estrategia | 1.º final | Fragmento con la respuesta |
|---|---|---|
| UDL-BACH-003, `por_encabezado` | `requisitos_ingreso.md` **solo-YAML** (afinidad 1.00, búsqueda #6, RRF 0.0315) | «Contenido» (búsqueda **#1**, afinidad 0, RRF 0.0164) → **4.º**, detrás de tres fragmentos solo-YAML (P-a) |
| Documentos, `documento_completo` | YAML de Torres Landa (afinidad 0.20, búsqueda #7) | `requisitos_ingreso.md` (afinidad 0.40, búsqueda #13) → **3.º**. Los puentes (búsqueda #1 y #2, afinidad 0) caen al 6.º y 7.º (P-a) |
| Documentos, `por_encabezado` | YAML de Torres Landa | «Contenido» (búsqueda #5, afinidad 0) → **fuera del top 5**: por delante quedan tres fragmentos solo-YAML (P-a) y los dos puentes (búsqueda #1 y #2) |

La forma observada por NEXOM en la consulta de documentos (puentes, información general y un fragmento YAML) coincide con la variante `por_encabezado`. Hay que confirmar la estrategia real (E7).

## 3. Comparación antes y después de P1

| | Simulador antes de P1 | Simulador después de P1 = Runtime antes y después |
|---|---|---|
| Reranking | aplicado (Automático) | no aplicado |
| UDL-BACH-003 | fuente esperada 1.ª (verde, 13 nov.) | 2.ª (amarillo) [OBS] |
| Consulta de documentos | 2.ª (prueba A, Ronda 105) | ausente del top 5 [OBS] |
| ¿Representa a producción? | **no** | **sí** (equivalencia verificada) |

Así, la corrida `085fe5a5-…` es la primera medición fiel de lo que responde el agente desplegado. **No conviene comparar contra la corrida del 13 de noviembre como línea base**: se recomienda tomar `085fe5a5-…` como nueva línea base (sección 6).

## 4. Respuestas a las preguntas 1, 2, 4 y 5

**1. ¿Mismo problema?** Comparten la causa A (fragmentos sin contenido que se adelantan por afinidad). La consulta de documentos suma la causa B (puentes y vocabulario). En la reproducción:
- **Y** (anula A) corrige UDL-BACH-003 en ambas estrategias;
- la consulta de documentos requiere **Y + R** en `por_encabezado`.

**2. ¿Por qué `requisitos_ingreso.md`, con mayor afinidad, queda debajo?** Por P-b: la afinidad solo desempata a distancias cortas de la búsqueda, y sin reranking ese fragmento no queda arriba en la búsqueda.
- **Su rival** (afinidad 0.18) no es contenido general, sino, con toda probabilidad, el fragmento solo-YAML del plan, que no debería tener afinidad (causa A).
- **Cuando los compartidos se fragmentan por encabezado**, la sección con la respuesta («Contenido») tiene afinidad 0 por título. Queda detrás de cualquier fragmento con afinidad (P-a), incluido el YAML de su propio documento.

**4. Quitar «Bachillerato» (P3) [EXP].**

| Consulta, estrategia | Sin P3 | Con P3 (consulta original) |
|---|---|---|
| Documentos, `documento_completo` | 3.º | **1.º** |
| Documentos, `por_encabezado` | ausente | 5.º |
| UDL-BACH-003, ambas estrategias | sin cambio | sin cambio |

- **Combinada con Y + R** en `por_encabezado` **empeora** dos consultas (R2 y R3, de 1.º a 2.º).
- **Valoración:** perjuicio real pero secundario y no uniforme. **No es la causa de UDL-BACH-003.**
- **Mecanismo:** el texto recortado («…ingresar Universidad de León?») conserva «Universidad de León», que aparece en el YAML de **todos** los documentos («institucion: Universidad de León») y en «Información general». Eso favorece justo a los fragmentos sin contenido específico.

**5. Referencias y YAML [EXP].**

| Elemento | Efecto | Peso |
|---|---|---|
| **Fragmentos puente** | Ocupan los puestos #1 y #2 de la búsqueda en la consulta de documentos, en las listas semántica y textual. En UDL-BACH-003 apenas pesan (búsqueda #8) | causa B |
| **YAML (1): fragmento solo-YAML** | Fragmento sin contenido con afinidad de título (C2) que, por P-a, se adelanta. Aparece en los primeros puestos finales de **las dos** consultas y en **las dos** estrategias | **causa A**, la de mayor peso |
| **YAML (2): YAML dentro del fragmento** | Diluye el vector (Ronda 105: coseno 0.280 → 0.356 sin YAML) | menor |

## 5. Mejoras pendientes: qué atiende cada una

Resultados [EXP] en las 14 consultas de LOTE01, sin reranking. MRR = promedio de 1/posición del fragmento correcto. Entre paréntesis, la posición en R1 (UDL-BACH-003) y R2 (documentos):

| Variante | `documento_completo`: MRR (R1, R2) | `por_encabezado`: MRR (R1, R2) | Consultas que empeoran respecto de r105b |
|---|---|---|---|
| r105b actual | 0.952 (1, 3) | 0.729 (4, —) | — |
| **Y** (P2a) | 0.964 (1, **1**) | 0.848 (**1**, 5) | R3 1→2 en `documento_completo` |
| T (P3) | **1.000** (1, 1) | 0.761 (4, 5) | ninguna |
| R (P2b, ajustada en la Ronda 105) | **1.000** | 0.768 (4, 4) | ninguna |
| **Y + R** (P2) | **1.000** (1, 1) | **0.952** (**1**, **1**) | ninguna |
| Y + R + T | **1.000** | 0.929 (1, 2) | ninguna, pero peor que Y + R en `por_encabezado` |
| P4 (índice sin YAML) | **1.000** | 0.848 (1, 5) | ninguna |
| P4 + R | **1.000** | 0.952 (1, 1) | ninguna |

En todas las variantes, las consultas de plan de estudios, ordinales, información general y RVOE siguen en 1.º.

| Mejora | Atiende | Dependencias | Riesgos |
|---|---|---|---|
| **P2a (Y)**: fragmento solo-YAML sin afinidad. Opcional: extenderlo a fragmentos solo-encabezado | Causa A (UDL-BACH-003; parte de la consulta de documentos) | ninguna | Bajo: no toca índice ni contenido; solo quita afinidad a fragmentos sin texto. Mueve consultas donde la afinidad de esos fragmentos ayudaba por casualidad (R3 1→2 en un caso) |
| **P2b (R)**, con el ajuste de títulos de la Ronda 105 | Causa B (puentes) | más eficaz después de Y | Falsos positivos de referencia (mitigados); trae fragmentos de baja relevancia de la misma fuente (p. ej. «Procedencia») |
| **P3 (T)**: no quitar del texto los valores filtrados | Pérdida de señal del texto recortado | ninguna | Efecto mixto; cambia todas las consultas con filtro. **No se recomienda ahora** |
| **P4**: índice sin YAML | Causa A y dilución | requiere reindexar y publicar de nuevo | Cambia todos los vectores; más costoso de validar. Equivale a Y en esta medición. Opción de segunda etapa |

## 6. Propuesta por etapas y criterios de aceptación

**Etapa 1 (recomendada para autorizar ahora): P2a (Y), con valor por defecto activado.**
- Nuevo identificador de procedimiento (p. ej. `r105c`).
- Sin cambios en índices ni documentos.

**Etapa 2: P2b (R)**, desactivada por defecto en la primera entrega (ajuste por proyecto, como en el diseño de la Ronda 104b) y activada tras la validación de NEXOM.

**Más adelante, según la evidencia:** P4 y P3.

**Criterios de aceptación** (cada etapa):
1. **AGENTE UDL, 14 casos de Calidad:**
   - línea base, la corrida `085fe5a5-…` (r105b, fiel al Runtime);
   - UDL-BACH-003 con la fuente esperada en 1.º, **sin modificar las expectativas**;
   - ningún otro caso empeora (veredicto ni puesto de la fuente esperada);
   - Recall@3 = 100 %;
   - MRR ≥ 0.90; objetivo 1.00.
2. **LOTE01, 14 consultas, en las dos estrategias de fragmentación:**
   - ninguna peor que r105b;
   - R1 en 1.º;
   - en R2, el fragmento con los requisitos por delante de los puentes (Etapa 2: en el top 3).
3. **Fragmentos sin contenido:** ninguno de los dos casos foco muestra fragmentos solo-YAML entre los cinco entregados (Etapa 1).
4. **Equivalencia Simulador–Runtime** (`test_ronda105b_equivalencia_reranking.py`, extendida a la nueva variante): mismos fragmentos, orden y puntajes con la misma instantánea, en Automático, Desactivado y Activado.
5. **Consultas no afectadas** (plan, ordinales, información general, RVOE): mismo orden en el Runtime que con r105b.
6. **Suites completas sin fallas nuevas.** Casos de Calidad históricos de Bachillerato y LOTE01 (`calidad_lote01.py`) sin diferencias no explicadas.

**Datos que conviene que NEXOM aporte**, para confirmar con su proyecto real lo que aquí se reprodujo con supuestos:
- para UDL-BACH-003, el «búsqueda #k» y el título de afinidad de los cinco fragmentos (los muestra el Simulador);
- la estrategia de fragmentación de los tres documentos compartidos (E7).

## 7. Estado

- **P1** sigue vigente sin cambios.
- **P2, P3 y P4:** sin implementar.
- **Incidente 493c8033:** abierto. Este análisis confirma que su consulta está afectada por las causas A y B en las condiciones del Runtime, pero la reconstrucción histórica sigue pendiente de las evidencias E1, E4 y E7.
