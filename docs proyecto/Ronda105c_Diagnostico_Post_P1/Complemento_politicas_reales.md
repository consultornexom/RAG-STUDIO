# Ronda 105e: diagnóstico con las políticas efectivas de AGENTE UDL

**Políticas confirmadas por NEXOM (vista previa del pipeline):**
- planes (`programa_academico`): `por_encabezado` 500/60/80;
- `areas_formacion.md`, `cualidades_aspirante.md` y `requisitos_ingreso.md`: `documento_completo`.

**Alcance:** sin cambios de motor, fuentes, índice ni casos. P1 sin cambios; incidente 493c8033 abierto.

**Reproducción:** `experimento_post_p1.py --compartidos documento_completo`, la configuración exacta informada. Resultados en `resultados_politicas_reales.json` y `salida_detalle_politicas_reales.txt`.

## 1. La reproducción coincide con el índice real

| Dato | Real | Reproducción |
|---|---|---|
| Fragmentos indexados | 29 | **29** |
| Fragmento [0] de Torres Landa | solo YAML, 135 tokens | solo YAML, 130 subpalabras |

**[COD] Por qué 29:** la fragmentación produce 37 fragmentos, pero el índice no incluye los 8 que solo contienen un encabezado de una línea (4 por plan: título del plan, «Plan de estudios» y los dos encabezados de área). Lo hace `RagService.index_source` desde antes de esta serie de rondas.

**Lectura corregida del diagnóstico anterior:**
- Esta configuración es la que la Ronda 105c llamó «`documento_completo`»: los compartidos como documento completo y los planes por encabezado.
- **El complemento `por_tamanio` de la Ronda 105d no corresponde al proyecto y queda descartado.** Con él también se descartan sus conclusiones sobre M, que dependían del título «Bachillerato — Plantel …» de un fragmento de tamaño.

## 2. Por qué la reproducción anterior no daba el 2.º lugar observado

Con las intenciones supuestas (las 4 activas del proyecto histórico de Bachillerato, más una de plan de estudios), UDL-BACH-003 sale **1.º** en r105b:
- «Información general» de Torres Landa es el **1.º de la búsqueda**, pero su afinidad con la intención es 0, así que queda 6.º;
- en la observación real tiene **afinidad 0.18** y queda 1.º.

**Hipótesis comprobable:** el texto real de la intención `consultar_requisitos_bachillerato` (nombre, descripción o ejemplos) contiene la palabra **«información»**.

**Prueba:** se repitió la reproducción con esa única diferencia (descripción «Consultar información general de los requisitos de ingreso al bachillerato.»). El resultado reproduce **las dos observaciones de NEXOM, posición por posición:**

| Posición | UDL-BACH-003 observado | Reproducido con la hipótesis |
|---|---|---|
| 1 | `bachillerato_torres_landa.md` (0.18) | Torres Landa, «Información general» (0.23; búsqueda #1) |
| 2 | `requisitos_ingreso.md` (0.57) | requisitos (0.65; búsqueda #2) |
| 3 | `bachillerato_hilario_medina.md` (0.18) | Hilario Medina, «Información general» (0.23) |
| 4 | `bachillerato_hilario_medina.md` (0.10) | Hilario Medina, solo-YAML (0.20) |
| 5 | `cualidades_aspirante.md` (0.07) | cualidades (0.15) |

**Consulta de documentos (reproducida):**
1. y 2. los dos puentes «Información compartida»;
3. y 4. «Información general»;
5. un fragmento solo-YAML.

Es la secuencia que describió NEXOM.

**Mecanismo [COD], combinación por puestos de la Ronda 102:**
- Torres Landa (búsqueda #1, afinidad 2.ª) suma 1/61 + 1/62.
- Requisitos (búsqueda #2, afinidad 1.ª) suma 1/62 + 1/61.
- **Empatan exactamente**, y el empate lo resuelve el orden de la búsqueda, que favorece a Torres Landa.

Con el puesto, una afinidad débil (0.18) vale lo mismo que una fuerte (0.57).

**Cómo confirmar la hipótesis:**
- **Intención:** el texto de `consultar_requisitos_bachillerato` en Diseño conversacional.
- **Simulador:** en UDL-BACH-003, la línea del 1.º resultado debe decir «búsqueda #1; afinidad 0.18 con «Información general»».

Mientras no se confirme, los resultados de las secciones 3 y 4 se presentan con **los dos juegos de intenciones**.

## 3. Comparación solicitada (14 consultas LOTE01, configuración real, sin reranking)

MRR (1.000 = el fragmento correcto siempre primero) y posición del fragmento correcto en R1 (UDL-BACH-003), R2 (documentos) y R3 (requisitos con plantel). **«—»** = fuera del top 5. Conteo de subpalabras. Con la hipótesis, los conteos `palabras` y `x3` dan los mismos resultados; con las intenciones supuestas, `palabras` coincide con la Ronda 105c.

| Variante | Con la hipótesis «información»: MRR (R1, R2, R3) | Intenciones supuestas: MRR (R1, R2, R3) |
|---|---|---|
| **r105b** | 0.857 (**2**, **—**, 2) | 0.952 (1, 3, 1) |
| M | 0.871 (2, 5, 2) | 0.964 (1, 1, **2**) |
| Y (P2a) | 0.871 (2, 5, 2) | 0.964 (1, 1, **2**) |
| M + Y | 0.871 (2, 5, 2) | 0.964 (1, 1, **2**) |
| Y + R (P2) | 0.964 (**2**, 1, 1) | **1.000** |
| M + Y + R | 0.964 (**2**, 1, 1) | **1.000** |
| **V** (nueva, sección 4) | **1.000** (1, 1, 1) | **1.000** |
| V + Y + R | **1.000** | **1.000** |

En todas las variantes, las consultas de plan de estudios, ordinales, información general y RVOE siguen en 1.º.

**Conclusiones de la comparación:**
- **Ninguna de las alternativas pedidas (M, Y, M + Y, Y + R, M + Y + R) resuelve UDL-BACH-003** bajo la hipótesis que reproduce lo observado. R1 sigue 2.º, porque ninguna cambia que la afinidad débil pese igual que la fuerte.
- **Y + R (y M + Y + R) resuelven la consulta de documentos** sin empeorar ninguna consulta.
- **M no aporta nada en esta configuración.** Con las intenciones supuestas, M o Y solas empeoran R3 (1.º → 2.º).

## 4. Corrección que resuelve los dos casos: V

**V: la afinidad suma según su valor, no según su puesto.**
- **Fórmula:** puntaje = 1/(61 + puesto en la búsqueda) + afinidad/61.
- **Qué cambia:** hoy la segunda mejor afinidad suma casi lo mismo que la primera, aunque valga un tercio. Con V, una afinidad de 0.18 suma menos de un tercio de lo que suma 0.57.
- **Qué conserva:** que un fragmento sin afinidad no suma nada por ese concepto.
- Es un ajuste de la regla de la Ronda 102 (C1), sin reglas por nombres de documento ni de programa.

**Efecto medido:**
- **Configuración real:** resuelve UDL-BACH-003 y la consulta de documentos con los dos juegos de intenciones (MRR 1.000; con la hipótesis, en los tres conteos), sin empeorar ninguna consulta.
- **Otras configuraciones:** compartidos por encabezado o todo por tamaño, ninguna consulta empeora respecto de r105b.

**Riesgo identificado [COD]:** reabre el patrón sintético de la Ronda 102, en el que secciones de otros documentos con el título exacto de la intención («Requisitos de ingreso», afinidad 1.00) solo remiten al archivo.
- **Cálculo:** con V, esas secciones (búsqueda #2 y #3, 1/62 + 1/61 ≈ 0.0325) volverían a superar al documento de requisitos (búsqueda #1, afinidad 0.86: 1/61 + 0.86/61 ≈ 0.0305).
- **Dónde aparece:** no en los documentos reales de LOTE01, pero es el caso para el que se diseñó C1.
- **Cobertura con R:** ese patrón son justamente fragmentos puente, y la resolución de referencias pone su destino delante.

**Por eso la combinación robusta es V + Y + R.**

## 5. Recomendación de implementación mínima

1. **Antes de autorizar, confirmar la hipótesis** con los dos datos de la sección 2: el texto de la intención y la línea del Simulador. Si no se confirma, este análisis debe repetirse con las intenciones reales.
2. **Para AGENTE UDL con su configuración real, la corrección mínima que resuelve los dos casos sin regresiones medidas es V.**
3. **Para no reabrir el patrón de la Ronda 102 en otros proyectos, recomendamos autorizar V junto con Y + R** (R desactivada por defecto hasta su validación, como en el diseño de la Ronda 104b). Con V + Y + R se obtuvo MRR 1.000 en la configuración real con ambos juegos de intenciones.
   - **Con los compartidos por encabezado**, V + Y + R no empeora ninguna consulta respecto de r105b, aunque con la hipótesis «información» M + Y + R quedó algo mejor (0.905 contra 0.857).
   - **Con todo por tamaño** se midió V sola, sin regresiones; V + Y + R no se midió en esa configuración.
4. **M:** opcional; no se recomienda ahora porque no aporta en la configuración real. **P3 y P4:** siguen sin recomendarse.
5. **Alternativa de configuración (sin código), decisión de NEXOM:** si se confirma la hipótesis, revisar el texto de la intención de requisitos para que describa el tema sin palabras genéricas («información»).
   - **Con las intenciones supuestas** (sin «información»), r105b ya pone UDL-BACH-003 en 1.º.
   - **Lo que no resuelve:** la consulta de documentos (3.º) ni la fragilidad de fondo.
   - **No es un cambio de las expectativas de las pruebas, sino del diseño del agente.**

**Criterios de aceptación para V + Y + R:**
1. **AGENTE UDL, 14 casos de Calidad** (línea base `085fe5a5-…`):
   - UDL-BACH-003 con la fuente esperada en 1.º, sin cambiar expectativas;
   - ningún caso empeora;
   - Recall@3 = 100 %;
   - MRR ≥ 0.90.
2. **LOTE01, 14 consultas** con la configuración real: ninguna peor que r105b; R1 y R2 en 1.º.
3. **Las otras configuraciones de LOTE01** (compartidos por encabezado y todo por tamaño): ninguna consulta peor que r105b.
4. **Prueba del patrón sintético de la Ronda 102:** el documento de requisitos queda por delante de las secciones que solo remiten a él.
5. **Pruebas de la Ronda 91:** «Perfil del egresado» sigue primero.
6. **Equivalencia Simulador–Runtime** con la misma instantánea.
7. **Suites completas** sin fallas nuevas.
