# RAG4 Fase -1, Actividad 1 -- Corpus de benchmark (reducido y honesto)

Este corpus se construyó para `RAG_STUDIO_Decision_RAG4_Excepcion_Controlada.docx`,
sección 10 (plan de benchmark de necesidad y ganancia agéntica). Documenta
cómo se llegó al alcance real, distinto del que describía originalmente
el plan (200-500 preguntas, 7 categorías) -- por decisión explícita del
consultor, consultada antes de construir nada (ver bitácora, Ronda 70).

## Fuente del corpus

Proyecto piloto `PRUEBAS_RAG_STUDIO_UDL_2026-08-20/` (dos archivos
`.agentproj`, nunca el proyecto real "AGENTE UDL"): 30 fuentes PDF entre
ambos, de las cuales solo 25 son distintas (Prueba A es un subconjunto
de 5 programas ya incluidos en Prueba B -- verificado por hash de
contenido, no por suposición).

## Hallazgo 1: el contenido piloto no soporta 200-500 preguntas ni las 7 categorías

Con 25 fuentes y 76 chunks reales, un corpus de 200-500 preguntas
hubiera significado preguntas repetidas o triviales. Además, ninguno de
los dos proyectos piloto tiene una sola fuente estructurada (XLSX/CSV)
-- las categorías "Estructuradas" e "Híbridas" del plan original (40-80
preguntas) no tienen ningún material real del que partir. Consultado
explícitamente, el consultor eligió: corpus reducido (~90-100 preguntas)
solo en las categorías que el contenido sí soporta (simples, ambiguas,
multiaspecto, multi-hop, adversariales) -- Estructuradas/Híbridas quedan
documentadas como sin cobertura por falta de material piloto, no
como un descuido.

## Hallazgo 2: el texto ya indexado por el pipeline real tiene una trampa de lectura, no solo ruido

Al inspeccionar el texto que el pipeline de extracción real de RAG
STUDIO ya generó para estas fuentes, cada ficha de programa parecía
tener las etiquetas de sección (REQUISITOS DE INGRESO, PERFIL DEL
EGRESADO, CAMPO DE TRABAJO, PERFIL DEL ASPIRANTE) asociadas al bloque de
contenido equivocado. Comparado a mano contra la imagen real de cada
PDF (5 programas, páginas 1 y 2, ver capturas en este mismo directorio
de trabajo), se confirmó que NO es una asociación aleatoria: cada
etiqueta aparece, en el texto extraído, inmediatamente DESPUÉS de su
propio contenido real (un artefacto de orden de lectura de las bandas
verticales rotadas del diseño de la ficha) -- es decodificable con la
regla correcta, pero un sistema que asuma "el texto después de la
etiqueta es su contenido" (lectura ingenua) obtendría la respuesta
equivocada. Esto es, en sí mismo, un caso de prueba legítimo para
distinguir la Fase -1 (¿el LLM razona sobre el contenido real, o repite
el error de asociación ingenua?) -- no se corrigió "para hacer más
fácil" el benchmark; se preservó la dificultad real del documento.

Este mismo hallazgo (más el defecto de la Ronda 22 en
`infrastructure/extraction/ocr_engine.py` que ya lo anticipaba
parcialmente) motivó la tarea aparte de mejorar el preprocesamiento de
OCR, pendiente para después de cerrar la Fase -1 de RAG 4.

## Cómo se construyó el "gold set"

Para 5 de los 25 programas (Administración de Empresas, Ingeniería en
Computación, Derecho, Psicología, Arquitectura -- los mismos que Prueba
A ya tenía marcados "validado"), el consultor leyó directamente las
imágenes de las 2 páginas del PDF ORIGINAL de cada ficha (no el texto
ya indexado) para construir un `programas_verificados.json` con:
plan de estudios completo por cuatrimestre, requisitos de ingreso,
perfil del egresado, campo de trabajo, perfil del aspirante, y lista de
planteles con RVOE. Es la fuente de verdad de todo el corpus
(`corpus_preguntas.json`) -- cada pregunta cita en `gold_evidence` de
qué programa(s) depende su respuesta correcta.

Los 20 programas restantes de Prueba B NO se usaron para construir
preguntas de este corpus reducido -- hacerlo hubiera exigido leer sus
25 PDFs originales también (fuera de alcance para una Fase -1 acotada);
quedan disponibles para ampliar el corpus más adelante si el resultado
de la Fase -1 justifica invertir en las Fases 0-5 completas.

## Cobertura final

- 94 preguntas: 60 simples, 15 multiaspecto, 7 ambiguas, 6 multi-hop, 6 adversariales.
- Estructuradas / Híbridas: 0 preguntas -- sin cobertura, documentado arriba.
- Las preguntas adversariales especifican en `notes` el texto de inyección
  sintético a insertar en una COPIA del chunk correspondiente (nunca en
  los `.agentproj` originales) -- se aplica en la Actividad 3 (ejecución
  del benchmark), no aquí.
