# Dockerfile de referencia para interfaces/api/ -- el runtime de
# producción (ADR-002), NO la app de escritorio (ui/): esa necesita
# una sesión gráfica y no tiene sentido en un contenedor. Ver
# packaging/api/README.md para qué se verificó de este archivo y qué
# no (Ronda 12, ver Validacion_observaciones_RAG_STUDIO.md).
#
# Construir desde la RAÍZ del repositorio (necesita ver pyproject.toml
# y los paquetes de código):
#
#     docker build -f packaging/api/Dockerfile -t ragstudio-api .
#
FROM python:3.12-slim

WORKDIR /app

# libgomp1: onnxruntime (dependencia transitiva de fastembed) lo
# requiere en tiempo de ejecución sobre Debian/Ubuntu -- sin él, cargar
# el modelo de embeddings falla con un error de biblioteca compartida
# faltante, no con un mensaje claro de "falta instalar algo".
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Solo el código que interfaces/api/ necesita -- ui/ y plugins/
# deliberadamente NO se copian: este contenedor nunca abre una
# interfaz gráfica ni carga complementos de la app de escritorio.
# Ronda 104b: build_info.json (si se generó con scripts/escribir_build_info.py)
# permite que el Runtime informe su commit sin .git.
COPY pyproject.toml build_info.json* ./
COPY app ./app
COPY application ./application
COPY domain ./domain
COPY infrastructure ./infrastructure
COPY interfaces ./interfaces
COPY workers ./workers

RUN pip install --no-cache-dir -e '.[api]'

# RAGSTUDIO_HOME: dentro del contenedor, todo lo que el proceso
# necesita escribir (runtime.db, logs/) vive aquí -- monta un volumen
# en /data para que sobreviva a que el contenedor se recree.
# RAGSTUDIO_API_KEY y RAGSTUDIO_SNAPSHOT_DIR (obligatorias),
# RAGSTUDIO_SNAPSHOT_VERSION (opcional, solo verificación) y el resto de variables
# opcionales (ver GUIA_DESPLIEGUE.md del paquete de entrega) se pasan
# al arrancar el contenedor (docker run -e / docker-compose
# "environment:"), nunca quedan fijadas en la imagen.
ENV RAGSTUDIO_HOME=/data
VOLUME ["/data"]

EXPOSE 8000

# --factory (recomendado en el docstring de interfaces/api/app.py):
# si falta una variable obligatoria o algo no cuadra (Ronda 92:
# carpeta de instantánea inexistente o raíz del paquete en vez de
# instantanea/, project.db inválido, versión distinta a la declarada,
# perfil de embeddings distinto al del índice -- ver
# interfaces/api/runtime_config.py),
# el contenedor termina con un error explícito en "docker logs" en vez
# de un error de ASGI genérico. Nota conocida, inofensiva: con
# RAGSTUDIO_API_KEY ya en el entorno, esto construye la app dos veces
# (una para el atributo de módulo "app" que el propio archivo también
# define, sin usar; otra para esta llamada del factory) -- verificado
# al correr este mismo comando fuera de Docker (ver README.md de esta
# carpeta): ambas construcciones son baratas (no repiten ninguna
# descarga de modelo), solo se ve duplicada la línea de arranque en el
# log.
CMD ["uvicorn", "interfaces.api.app:create_app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000"]
