# Ronda 102: diagnóstico de la diferencia entre Búsqueda RAG y el Simulador

> **Actualización:** NEXOM autorizó C1, C2 y C4, que ya están implementadas y validadas con los cinco archivos reales de LOTE01. Ver `Resultados_Ronda102.md`.

**Caso de NEXOM (LOTE01_Bachillerato real, código de la Ronda 101).**
- **Consulta:** «¿Cuáles son los requisitos para ingresar al Bachillerato de la Universidad de León?».
- **Búsqueda RAG (híbrida, sin reranking):** `requisitos_ingreso.md` en posición 2.
- **Simulador:** intención correcta (`consultar_requisitos_bachillerato`, 0.789), filtro `nivel_academico=bachillerato`, 0 fuentes descartadas, acción Responder. `requisitos_ingreso.md` **no** aparece entre los 5 fragmentos.

**Alcance.** Diagnóstico sin cambios de código. No tengo los documentos reales de LOTE01. La reproducción usa un corpus SINTÉTICO con la estructura descrita por NEXOM: `diagnostico_simulador.py`, en esta carpeta, con los modelos reales del proyecto. Las conclusiones sobre el mecanismo se verifican en el código; el orden exacto con los documentos reales queda por confirmar.

## 1. Qué hace distinto el Simulador (código actual)

Búsqueda RAG y el Simulador **no** ejecutan la misma búsqueda. Con filtros de metadatos activos, el Simulador (`SimulateConversation._search_and_filter`, que es también el motor de `POST /messages`) hace lo siguiente:

1. **Filtra por metadatos ANTES de buscar** (Ronda 89). Aquí no descarta nada: todas las fuentes tienen `nivel_academico=bachillerato`.
2. **Cambia el texto de búsqueda.** Quita de la consulta los valores ya filtrados y los compartidos por TODAS las fuentes permitidas (Ronda 89). «…ingresar **al Bachillerato** de la Universidad de León» pasa a «…ingresar Universidad de León».
3. **Busca un pool de 20 candidatos con reranking SIEMPRE que haya un reranker instalado** (`rerank=self._rag.has_reranker`). La aplicación de escritorio y Runtime siempre lo instalan. **Desactivar «Reranking» en Búsqueda RAG no lo desactiva en el Simulador ni en Runtime.**
4. **Reordena por afinidad título–intención** (Ronda 91, `domain/conversational/section_affinity.py`). La afinidad es la **clave principal** del orden, y el puntaje de búsqueda solo desempata a igual afinidad.
5. Toma los 5 primeros.

Búsqueda RAG no hace los pasos 2 a 4. Por eso un fragmento en posición 2 en el Laboratorio puede salir del top 5 en el Simulador. Que el resultado no cambiara al dar `nivel_academico=bachillerato` a mano es coherente: el filtro se aplicaba igual, porque se detectaba en la consulta.

## 2. Causa principal: la afinidad de título manda sobre la recuperación (puntos 3 y 4)

En la reproducción, el pool que recibe el Simulador tiene `requisitos_ingreso.md` en **1.ª posición**, con y sin reranking. La afinidad lo baja:

| Pool (búsqueda) | Afinidad | Orden final |
|---|---|---|
| 1. requisitos_ingreso.md «Requisitos de ingreso al Bachillerato» | 0.86 | 3.º |
| 2. plan Torres Landa «Requisitos de ingreso» (solo remite al archivo) | 1.00 | **1.º** |
| 3. plan Hilario Medina «Requisitos de ingreso» (solo remite al archivo) | 1.00 | **2.º** |
| 4–5. «Información general» de ambos planteles | 0.00 | 4.º–5.º |

Con otra primera línea del archivo, por ejemplo «Universidad de León — Servicios Escolares», su afinidad baja a 0.50. Basta con que el proyecto real tenga 5 fragmentos con mayor afinidad (secciones tituladas con palabras de los ejemplos de la intención: «requisitos», «ingreso», «documentos», «entrar»…) para que el documento quede **fuera** del top 5, que es lo que observó NEXOM.

**Los tres mecanismos que lo producen:**
- **(a) La afinidad es la clave principal del orden.** El mejor resultado de la búsqueda solo vuelve a estar adelante si empata en afinidad. En la Ronda 91 resolvió que «Perfil del egresado» se impusiera a secciones de control editorial dentro de UN programa, pero con documentos compartidos anula la recuperación.
- **(b) Los documentos `documento_completo` no tienen título de sección.** La afinidad usa la **primera línea** del texto, que puede no describir el documento (encabezado institucional, título largo).
- **(c) La afinidad es una proporción:** palabras del título que coinciden, dividido entre palabras del título. Un título corto que solo **nombra** el tema («Requisitos de ingreso», que en el plan solo remite al archivo) gana a un título más largo y específico. Además, la palabra «Bachillerato» no cuenta, porque es un valor de catálogo y se enmascara.

**Los documentos compartidos con `documento_completo` sí participan en la recuperación** (punto 4): están en el pool y la búsqueda los pone primero. El problema es el reordenamiento posterior.

## 3. Quitar del texto los valores filtrados (punto 2)

En este caso **no es la causa**: con «…ingresar Universidad de León» el pool sigue teniendo `requisitos_ingreso.md` en 1.º. Quitar el valor filtrado tiene sentido: todas las fuentes permitidas lo comparten y no distingue entre ellas. Se mantiene, y queda a la vista en «Texto de búsqueda» del Simulador.

## 4. Reranking que el operador cree desactivado (punto 1)

No es la causa en la reproducción: el pool con reranking también pone el documento primero. Pero es una **diferencia real de configuración**:
- Simulador y Runtime aplican siempre el cross-encoder si está instalado.
- El Simulador no lo muestra en el trazado.

Validar «sin reranking» en Búsqueda RAG no valida lo que hará el agente.

## 5. Responder con fragmentos que solo remiten a otro documento (punto 5)

**El riesgo es real y está confirmado en el código.**
- **Cuándo se decide Responder:** se decide antes de buscar (intención, variables, guardrails). La búsqueda solo lo cambia a Abstenerse si **no hay ningún** resultado.
- **Qué no se evalúa:** si los fragmentos contienen la respuesta. Aquí los dos primeros dicen «Los requisitos de ingreso se describen en el archivo requisitos_ingreso.md»: hablan del tema, pero no contienen ningún requisito.
- **Lo que aplica hoy:** la advertencia de relevancia baja solo existe en el modo Semántico del Laboratorio.

## 6. Prueba de regresión con LOTE01 real (punto 6)

No puedo incorporarla sin los documentos reales: no están en este entorno. Propuesta:
- NEXOM entrega los 5 archivos del lote, o un `.agentproj` de LOTE01;
- se agrega una prueba con la consulta y el documento esperado (`requisitos_ingreso.md` en el top 5, de preferencia 1.º), más los casos que hoy funcionan (información general, plan de estudios por área y semestre).

Mientras tanto, este diagnóstico queda como reproducción sintética.

## 7. Propuesta de corrección (pendiente de autorización; general, sin reglas para este proyecto)

| # | Cambio | Qué resuelve | Riesgo / cómo se controla |
|---|---|---|---|
| C1 | La afinidad deja de ser la clave principal. Se combina por RRF con el orden de la búsqueda, como una lista más; reordena, pero no puede enterrar el mejor resultado. | Causa principal (a). | Volver a correr las pruebas de la Ronda 91 («perfil de egreso», control editorial) y medir. |
| C2 | Título para fragmentos sin `section_title` (`documento_completo`, `por_tamanio`): su primer encabezado Markdown y, si no tiene, el título de la fuente. Ya no la primera línea cualquiera. | (b). | Solo cambia el título que usa la afinidad; no el texto ni el índice. |
| C3 | Afinidad por cobertura de las raíces distintivas de la intención en lugar de proporción del título, o normalizada con un mínimo de longitud. | (c). | Pruebas de la Ronda 91 y del caso actual. |
| C4 | Reranking del agente visible y configurable por proyecto («Reranking en el agente»; por defecto, como hoy), y el trazado del Simulador indica si se aplicó. | Sección 4. | Sin cambio de comportamiento por defecto. |
| C5 | Señal de evidencia insuficiente: si los primeros fragmentos son cortos y solo remiten a otro archivo, el trazado lo advierte. Opcionalmente, una condición de guardrail («evidencia_insuficiente») para que el diseñador decida abstenerse o canalizar. | Sección 5. | Solo advierte por defecto; la regla la activa el diseñador. Recomendación editorial para RAG CONTENT: no dejar secciones que solo dicen «ver archivo X». |

**Orden recomendado:**
- C1 + C2 + C4: resuelven el caso y la confusión de configuración, sin tocar el índice ni la base de datos.
- C3 y C5: después de medir con los documentos reales.

Antes de implementar, el conjunto de evaluación incorporará este caso (sintético y, con los documentos de NEXOM, real), los casos de la Ronda 91 y los de las Rondas 100 y 101, con y sin reranking.
