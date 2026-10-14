# RAG4 Fase -1, Actividad 2 -- prototipo aislado del planificador (para correr en tu máquina)

Este prototipo no se pudo ejecutar de punta a punta desde este entorno
de consultoría: `ollama.com` y `huggingface.co` están bloqueados por su
lista blanca de red (confirmado con `curl`, error `blocked-by-allowlist`),
y `huggingface.co` es también de donde RAG STUDIO descarga su propio
modelo de embeddings la primera vez -- así que ni siquiera Sistema A
(sin ningún LLM de por medio) pudo correr aquí. Lo que **sí** se
verificó desde este entorno, contra tu repositorio y tu proyecto piloto
reales:

- `preparar_proyecto_piloto.py` descomprime `Prueba_B_Cobertura_OCR_25_programas.agentproj` y aplica las 4 inyecciones adversariales correctamente (ver salida más abajo).
- `harness.py` construye un `RagService` real (mismos adaptadores que `app/bootstrap.py`) contra ese proyecto piloto -- llegó hasta intentar cargar el modelo de embeddings real, y falló ahí exactamente por el mismo bloqueo de red (no por un error de mi código).
- `plan_schema.py` rechaza correctamente un plan con un campo inyectado extra y un plan que pide un `retriever` no autorizado -- las dos protecciones centrales de la sección 7 del documento de decisión.
- Los 8 scripts compilan sin errores de sintaxis (`python3 -m py_compile`).

En tu máquina, con acceso normal a internet, esto debería correr sin
ningún cambio de código.

## 1. Instalar Ollama y un modelo pequeño

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b   # o qwen2.5:3b -- cualquier modelo de instrucciones de 1-4B params corre razonablemente en CPU
ollama serve              # si el instalador no dejó ya un servicio corriendo en segundo plano
```

Nota sobre "instalar en `/media/disco/Data/RAG STUDIO`": Ollama se
instala como un servicio del sistema operativo (binario + servicio
systemd en Linux), no como un paquete dentro de una carpeta de
proyecto -- no hay una forma soportada de "instalarlo dentro" del
repositorio. Lo que sí vive dentro del repositorio es este prototipo
(`docs proyecto/RAG4_Fase-1_Benchmark/prototipo/`), que se CONECTA a
Ollama por HTTP (`localhost:11434`) una vez que ya está instalado y
corriendo en tu sistema.

## 2. Preparar el entorno Python

Usa el mismo entorno virtual donde ya corres RAG STUDIO (necesita
`pydantic`, `fastembed`, `qdrant-client`, etc. -- las dependencias
reales del proyecto, no solo las de este prototipo).

```bash
cd "/media/disco/Data/RAG STUDIO"
source .venv/bin/activate   # o el venv que ya uses para correr la app
```

## 3. Preparar la copia de trabajo del proyecto piloto

**Nunca se modifican los `.agentproj` originales ni el proyecto real "AGENTE UDL".**

```bash
cd "docs proyecto/RAG4_Fase-1_Benchmark/prototipo"
python3 preparar_proyecto_piloto.py \
    --pilot-root "../../../PRUEBAS_RAG_STUDIO_UDL_2026-08-20" \
    --which B \
    --dest ./trabajo/piloto_b \
    --corpus ../corpus_preguntas.json \
    --programs ../programas_verificados.json
```

Esto debe imprimir 4 líneas de "Inyección aplicada..." (una por
programa adversarial) -- ya verificado desde este entorno.

## 4. Correr el benchmark completo (94 preguntas x 2 sistemas)

```bash
PYTHONPATH="../../../..:." python3 run_benchmark.py \
    --snapshot-dir ./trabajo/piloto_b \
    --ollama-model llama3.2:3b \
    --corpus ../corpus_preguntas.json \
    --out ./trabajo/resultados_benchmark.jsonl
```

`PYTHONPATH` debe incluir la raíz del repositorio de RAG STUDIO (para
`from application.rag.service import RagService`, etc.) -- ajusta la
ruta relativa si corres el comando desde otro directorio.

Antes de la corrida completa, prueba con `--limit 5` para confirmar que
todo está bien conectado (Ollama respondiendo, RagService encontrando
resultados) sin esperar las 94 preguntas.

## 5. Ver un primer resumen cuantitativo

```bash
python3 analizar_resultados.py \
    --resultados ./trabajo/resultados_benchmark.jsonl \
    --programs ../programas_verificados.json \
    --snapshot-dir ./trabajo/piloto_b
```

## Limitaciones de este prototipo (documentadas, no descuidos)

- **`query_structured` no se puede ejercitar**: el proyecto piloto no
  tiene ninguna fuente XLSX/CSV (ver `README.md` de Actividad 1). Si el
  planificador lo pide, `sistema_b_planificador.py` lo registra como
  error explícito en vez de inventar un resultado.
- **El analizador automático (`analizar_resultados.py`) no decide el
  criterio de aprobación** de la sección 10.4 del documento de
  decisión -- ese criterio es cualitativo ("mejora significativa de
  evidencia correcta") y exige leer las respuestas reales. El script
  solo entrega latencia, número de retrievals y un proxy de cobertura
  de fuentes -- un punto de partida para la Actividad 4, no el
  análisis completo.
- **Un solo modelo local probado en el diseño** (el código acepta
  cualquier modelo ya descargado con `ollama pull`, pero no se probó
  end-to-end contra ninguno desde este entorno, por el bloqueo de red
  ya explicado). Antes de confiar en los resultados, vale la pena
  correr `--limit 5` y leer a mano las 5 respuestas.
- **`temperature=0.0` fijo**: deliberado (ver comentario en
  `ollama_client.py`) para que la métrica de "estabilidad entre
  ejecuciones" (tabla 10.2) mida variación real del modelo, no
  aleatoriedad evitable -- si quieres medir con temperatura > 0, es un
  parámetro de una línea en `sistema_b_planificador.py`.
- **`index_snapshot_id` es solo el nombre de la carpeta**, no un hash
  real de contenido -- suficiente para este prototipo aislado (un solo
  snapshot por corrida), pero no es el mecanismo de versionado real de
  RAG STUDIO (`ProjectSnapshot`, ver `domain/release/entities.py`).
