# Empaquetado operativo de interfaces/api/ (Ronda 12)

Ítem del análisis de "grado profesional" del entregable al cliente
(ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 11-12): antes de
esta ronda, `GUIA_DESPLIEGUE.md` (generado por "Exportar paquete de
entrega al cliente…") solo documentaba el comando de `uvicorn` a mano
-- sin ningún artefacto reproducible que reduzca el margen de error
humano al desplegar. Esta carpeta agrega dos rutas de despliegue de
referencia: contenedor (Docker) o proceso administrado por systemd,
para quien prefiera una u otra según su infraestructura.

Esto es **empaquetado de `interfaces/api/` (el runtime de
producción)**, no de la app de escritorio -- ver `packaging/` (la
carpeta raíz de empaquetado, un nivel arriba) para el `.spec` de
PyInstaller de la app de escritorio, que es un problema completamente
distinto.

## Qué se verificó y qué no (léase con honestidad, mismo criterio que `packaging/README.md`)

- **No se construyó la imagen Docker de verdad.** Este entorno de
  construcción no tiene Docker instalado (`docker: command not
  found`), así que `Dockerfile`/`docker-compose.yml` están bien
  fundamentados (siguen exactamente los mismos pasos que
  `GUIA_DESPLIEGUE.md` ya documenta y que SÍ se verificaron reales,
  ver el punto siguiente) pero nunca se construyeron ni se corrieron
  dentro de un contenedor real.
- **El comando real que ambos artefactos ejecutan sí se verificó de
  punta a punta, fuera de Docker**: se publicó una instantánea real
  de un proyecto de prueba, se arrancó
  `uvicorn interfaces.api.app:create_app_from_env --factory --host
  127.0.0.1 --port 8791` con `RAGSTUDIO_HOME`/`RAGSTUDIO_API_KEY`
  reales configurados, y `curl http://127.0.0.1:8791/health`
  respondió `{"status":"ok","loaded_projects":[]}` con código 200. El
  registro operativo (Ronda 11) escribió de verdad la línea de
  arranque en `logs/ragstudio-api.log`. Esto confirma que el `CMD`
  del `Dockerfile` y el `ExecStart` del `.service` son correctos y
  arrancan el servicio real -- lo único no verificado es la
  construcción de la imagen en sí (empaquetado de dependencias del
  sistema con `apt-get install libgomp1`, etc.), que requiere Docker.
- **Se descubrió, en esa misma verificación, un detalle menor ya
  documentado en el docstring de `interfaces/api/app.py`**: con
  `RAGSTUDIO_API_KEY` ya presente en el entorno (el caso normal en
  producción), el módulo se importa y construye la app UNA vez para
  el atributo `app` (sin usar, pensado para quien no use
  `--factory`) y una SEGUNDA vez para la llamada explícita del
  factory -- se ve como la línea de arranque duplicada en el log.
  Inofensivo (ninguna construcción repite una descarga de modelo;
  `RuntimeContext` calienta el proveedor de embeddings solo al
  atender el primer mensaje real, no al construir la app), documentado
  en el `Dockerfile` para que no se confunda con un error.
- **Los archivos `.service`/`.timer` se validaron con
  `systemd-analyze verify`** (disponible en este entorno, a
  diferencia de Docker): no reportó ningún error de sintaxis. Sí
  reportó dos avisos esperables en ESTE entorno, no en el destino
  real: (a) que los binarios referenciados
  (`/opt/ragstudio/.venv/bin/uvicorn`/`python`) no existen -- correcto,
  esa ruta es de la máquina de destino, no de este entorno de
  construcción; y (b) que los archivos están "marcados como
  ejecutables" -- un artefacto del sistema de archivos de este
  entorno de construcción (montado con permisos que este sandbox no
  puede cambiar con `chmod`, verificado); al copiarlos a un host real,
  ejecuta `chmod 644 *.service *.timer` para quitar ese aviso ahí (no
  afecta el funcionamiento, systemd los procesa igual).
- **No se probó `docker-compose.yml` de punta a punta** (misma razón:
  sin Docker en este entorno) ni el `healthcheck` definido ahí --
  aunque `python3 -c "import urllib.request; ..."` es exactamente lo
  que ya prueba `curl` en el punto anterior, solo reescrito para no
  depender de que la imagen base incluya `curl`.
- **Escalabilidad a varias réplicas (GUIA_DESPLIEGUE.md, sección 11)**:
  sí se verificó de punta a punta, con procesos `uvicorn` reales (no
  Docker, por la misma limitación de este entorno) -- se publicó una
  instantánea real, se copió a una segunda carpeta independiente, y se
  lanzaron dos procesos reales por separado. Contra la MISMA carpeta de
  instantánea, 60 solicitudes concurrentes reales (30 hilos) produjeron
  3 fallos reales con 500 (`RuntimeError: Storage folder ... is already
  accessed by another instance of Qdrant client`, visible en el log del
  proceso). La misma carga contra dos procesos con una copia propia
  cada uno terminó en 0 fallos. Las cifras de latencia/throughput
  absolutas de esa prueba (este entorno de construcción solo tiene 2
  núcleos de CPU compartidos) no se documentan como representativas de
  ningún hardware de producción real -- lo que se documenta en
  `GUIA_DESPLIEGUE.md` es la comparación relativa (copia propia = sin
  errores; carpeta compartida = riesgo real), que sí es una propiedad
  de diseño transferible a cualquier máquina.

## Docker

```bash
# Desde la raíz del repositorio:
docker build -f packaging/api/Dockerfile -t ragstudio-api .
docker run --rm -p 8000:8000 \
  -e RAGSTUDIO_API_KEY=<clave del .env.example del paquete de entrega> \
  -e RAGSTUDIO_SNAPSHOT_DIR=/snapshot \
  -v /ruta/al/paquete/instantanea:/snapshot:ro \
  -v ragstudio-data:/data \
  ragstudio-api
```

O con `docker-compose.yml` (ver comentarios dentro del archivo).

## systemd

```bash
# En la máquina de destino, como root:
useradd --system --home /opt/ragstudio ragstudio
mkdir -p /opt/ragstudio
# ... instalar el código + crear el venv en /opt/ragstudio (ver
# GUIA_DESPLIEGUE.md, paso 1) ...
# ... copiar aquí el .env generado a partir de .env.example, como
# /opt/ragstudio/ragstudio-api.env, y protegerlo: ...
chmod 600 /opt/ragstudio/ragstudio-api.env
chown ragstudio:ragstudio /opt/ragstudio/ragstudio-api.env

cp ragstudio-api.service ragstudio-purge-conversations.service ragstudio-purge-conversations.timer /etc/systemd/system/
chmod 644 /etc/systemd/system/ragstudio-*.service /etc/systemd/system/ragstudio-*.timer
systemctl daemon-reload
systemctl enable --now ragstudio-api.service
systemctl enable --now ragstudio-purge-conversations.timer
```

`ragstudio-purge-conversations.service`/`.timer` implementan la
recomendación de retención de datos de `GUIA_DESPLIEGUE.md` (sección
"Retención de la bitácora de conversaciones") como una tarea
programada real, en vez de depender de que alguien se acuerde de
correr el script a mano. Ajusta `--retention-days` en el `.service`
antes de instalarlo -- no hay un valor por defecto a propósito (ver
`application/runtime/commands/purge_old_conversations.py`).

## Validación previa y verificación (Ronda 92)

Antes de arrancar (desde la carpeta del código, con su venv activo):

```bash
python -m interfaces.api.check_config --verificar-huella
```

Imprime `LISTO` con proyecto, versión y perfil resueltos, o `NO LISTO`
con todos los problemas. Tras arrancar, `GET /health` devuelve
`snapshot_mode`, `snapshot_project_id` y `snapshot_version`: comprueba
que coinciden con el paquete desplegado. Obligatorias: `RAGSTUDIO_SNAPSHOT_DIR`
y `RAGSTUDIO_API_KEY`. `RAGSTUDIO_SNAPSHOT_VERSION` es opcional (Ronda 94):
la versión se toma de `instantanea/snapshot_identity.json`; si se define,
debe coincidir o el proceso no arranca. Nunca se supone 1 por defecto. El nombre
oficial de la clave es `RAGSTUDIO_API_KEY` (`RAG_API_KEY` solo se
acepta como alias heredado, con aviso).
