"""Caso de uso: exportar el paquete de entrega al cliente (Ronda 10, ver
Validacion_observaciones_RAG_STUDIO.md) -- un solo artefacto exportable
que reúne la instantánea publicada de un proyecto (ADR-002, Fase 1), un
token de widget recién emitido y acotado a ese proyecto (Fase 4), el
snippet de embebido del widget (Fase 3) y las instrucciones de
despliegue de `interfaces/api/` (Fase 2/4), más un informe formal
dirigido al cliente y una guía técnica dirigida a quien vaya a operar
el runtime.

Distinto de ExportDeliverablesPackage (Etapa 7): ese empaqueta
EVIDENCIA de que el proyecto pasó las compuertas de calidad; este
empaqueta los ARTEFACTOS Y LA CONFIGURACIÓN necesarios para levantar
el runtime de producción y embeber el widget en el sitio del cliente.
Son paquetes independientes, para audiencias distintas -- no hace
falta haber solicitado ninguna liberación formal para exportar este
(mismo criterio que "Publicar instantánea…").

Reutiliza IssueWidgetToken (application.runtime.commands) en vez de
reimplementar la emisión de tokens -- mismo criterio de composición
entre fachadas que ya usa ReleaseService con QualityService/
ConversationalService."""
from __future__ import annotations

import secrets

from application.runtime.commands.issue_widget_token import IssueWidgetToken
from application.runtime.commands.revoke_widget_token import RevokeWidgetToken
from domain.projects.exceptions import ProjectNotFoundError
from domain.projects.ports import ProjectRepository
from domain.release.entities import DeploymentPackage
from domain.release.exceptions import NoPublishedSnapshotError
from domain.release.ports import DeploymentPackager, ProjectSnapshotRepository
from domain.runtime.ports import WidgetTokenRepository

def _env_vars_doc(snapshot_version: int) -> list[tuple[str, bool, str]]:
    """Variables del runtime (Ronda 92: una sola fuente para la guía y el
    .env.example; nombres oficiales con prefijo RAGSTUDIO_)."""
    return [
        ("RAGSTUDIO_SNAPSHOT_DIR", True,
         "Ruta ABSOLUTA a la subcarpeta `instantanea/` de este paquete ya extraído (por ejemplo "
         "/opt/entrega_cliente_<proyecto>_v<N>/instantanea, o C:\\entregas\\entrega_cliente_<proyecto>_v<N>"
         "\\instantanea en Windows) -- NO la raíz del paquete. Fija la instantánea exacta que sirve el "
         "proceso. Si vas a correr varias réplicas (sección 11), cada una necesita su PROPIA copia extraída."),
        ("RAGSTUDIO_SNAPSHOT_VERSION", False,
         f"Verificación opcional de la versión servida (la de este paquete es {snapshot_version}). Si se "
         "omite, la versión se toma de `instantanea/snapshot_identity.json`. Si se define, debe coincidir "
         "con esa versión; si no coincide, el runtime NO arranca y explica la diferencia. Solo es necesaria "
         "con una instantánea antigua que no traiga snapshot_identity.json ni el manifest.json del paquete "
         "(ver check_config). Nunca se supone 1 por defecto."),
        ("RAGSTUDIO_API_KEY", True,
         "Clave operativa global. Obligatoria: sin ella el proceso no arranca. Trátala como un secreto (no "
         "la incrustes en un <script> público -- para eso está el token de widget). Se generó un valor "
         "aleatorio propio de esta entrega más abajo. El nombre heredado RAG_API_KEY solo se acepta por "
         "compatibilidad, con aviso; usa siempre RAGSTUDIO_API_KEY."),
        ("RAGSTUDIO_HOME", False,
         "Carpeta de trabajo del runtime: registro operativo (logs/ragstudio-api.log), runtime.db (bitácora "
         "y tokens de widget) y caché de modelos de embeddings. Con RAGSTUDIO_SNAPSHOT_DIR definida es "
         "opcional (por defecto, la carpeta de datos del usuario que ejecuta el proceso); conviene fijarla, "
         "por ejemplo /var/lib/ragstudio."),
        ("RAGSTUDIO_EMBEDDING_PROFILE", False,
         "Perfil de embeddings (\"simetrico\" o \"asimetrico_e5_large\"). Normalmente NO hace falta: se "
         "deriva del modelo con que se construyó el índice de la instantánea, y si se define uno distinto "
         "el proceso no arranca."),
        ("RAGSTUDIO_RUNTIME_DB_PATH", False,
         "Ruta del archivo runtime.db (bitácora de conversaciones + tokens de widget). Por defecto, "
         "runtime.db dentro de RAGSTUDIO_HOME."),
        ("RAGSTUDIO_WIDGET_ALLOWED_ORIGINS", False,
         "Orígenes (dominios) autorizados a llamar a este servicio desde el navegador, separados "
         "por coma -- necesario para que el widget funcione embebido en el sitio del cliente. "
         "Sin configurar, el navegador bloquea la llamada del widget por CORS."),
        ("RAGSTUDIO_CHANNELING_WEBHOOK_URL", False,
         "URL (http/https) de un webhook saliente al que se notifica cada vez que el motor conversacional "
         "decide \"canalizar\" (derivar a un humano). Sin configurar, solo se muestra el texto de derivación."),
        ("RAGSTUDIO_CHANNELING_WEBHOOK_SECRET", False,
         "Secreto opcional que se envía en el encabezado X-Webhook-Secret de cada notificación de "
         "canalización, para que el receptor del webhook pueda verificar su origen."),
        ("RAGSTUDIO_LOG_LEVEL", False,
         "Nivel de registro operativo (DEBUG, INFO, WARNING, ERROR; por defecto INFO). Se escribe en "
         "RAGSTUDIO_HOME/logs/ragstudio-api.log, con rotación automática."),
        ("RAGSTUDIO_RATE_LIMIT_PER_MINUTE", False,
         "Límite opcional de solicitudes por minuto (entero >= 1), por IP del visitante, contra /messages. "
         "Sin configurar, no hay límite propio (ver sección 9)."),
    ]


def _build_informe(project_name: str, project_id: str, snapshot_version: int) -> str:
    return f"""# Informe de entrega -- {project_name}

## Qué se le está entregando

Este paquete contiene todo lo necesario para poner en operación el
agente conversacional del proyecto **{project_name}** (id `{project_id}`),
construido y validado en RAG STUDIO, en un canal real (un widget de
chat embebible en un sitio web).

Concretamente, incluye:

1. **Una instantánea de solo lectura del proyecto** (carpeta
   `instantanea/`, versión {snapshot_version}): el contenido, los
   metadatos, las reglas de conversación y el índice de búsqueda ya
   construidos y evaluados en RAG STUDIO, congelados en el momento en
   que se publicó esta instantánea. El agente que se despliegue con
   esta instantánea responderá exactamente con el comportamiento que
   ya se validó -- no se recalcula ni se reentrena nada al desplegar.
2. **Un token de acceso para el widget** (ver `GUIA_DESPLIEGUE.md`),
   único para este proyecto: permite que el widget converse con el
   agente sin exponer la clave operativa completa de la instalación.
3. **El código del widget de chat embebible** (`widget-embed.html`):
   el fragmento HTML que se pega en el sitio web del cliente para que
   el agente aparezca como una burbuja de chat.
4. **Una guía técnica de despliegue** (`GUIA_DESPLIEGUE.md`) y una
   **plantilla de variables de entorno** (`.env.example`) para quien
   vaya a instalar y operar el servicio.
5. **Un manifiesto** (`manifest.json`) que identifica la entrega:
   proyecto y versión entregados (identidad del conocimiento, igual en
   todas las exportaciones de esa versión) y un identificador propio de
   esta exportación física (`deployment_package_id`), distinto en cada
   exportación.
6. **Un contrato de integración** (`CONTRATO_INTEGRACION.md`) para el
   equipo que construya o mantenga el agente conversacional que
   consumirá este servicio: la forma real de cada solicitud y
   respuesta, qué significa cada resultado posible, y una plantilla de
   system prompt recomendada para su propio modelo de lenguaje.

## Qué NO incluye este paquete

- **Hospedaje**: este paquete no incluye un servidor, dominio ni
  certificado TLS. Alguien debe ejecutar el servicio en algún lugar
  (una máquina propia, un servidor en la nube, un contenedor) y
  exponerlo con HTTPS.
- **Generación de lenguaje natural**: el agente no redacta respuestas
  nuevas con un modelo de lenguaje; responde con los fragmentos de la
  documentación que resultaron más relevantes para la pregunta, o
  deriva a un humano cuando corresponde. Este es un límite conocido y
  documentado del diseño del agente, no un defecto de este paquete.
- **Integración con un canal distinto al widget web** (por ejemplo,
  WhatsApp): si se requiere, es un desarrollo adicional sobre el mismo
  servicio, no algo que este paquete ya resuelva.
- **Mantenimiento continuo del contenido**: si la documentación fuente
  cambia, hay que volver a RAG STUDIO, actualizarla ahí, y publicar y
  entregar una instantánea nueva -- esta instantánea queda fija tal
  como se publicó siempre que el despliegue siga la guía técnica
  (variable RAGSTUDIO_SNAPSHOT_DIR, apuntando a la copia de este
  paquete). Si en cambio se configura para leer directamente la
  instalación de escritorio de origen, el runtime empezará a servir
  cualquier instantánea nueva que se publique ahí, sin aviso.

## Seguridad

El token de widget incluido en este paquete puede revocarse en
cualquier momento (por ejemplo, si el sitio donde se embebió deja de
usarse) sin afectar la clave operativa ni a otros proyectos --
ver la sección de revocación en `GUIA_DESPLIEGUE.md`.
"""


def _build_guia_despliegue(
    project_id: str, widget_token_id: str, snapshot_version: int, max_access_level: str,
) -> str:
    variables_md = "\n".join(
        f"- `{name}` ({'obligatoria' if required else 'opcional'}): {desc}"
        for name, required, desc in _env_vars_doc(snapshot_version)
    )
    return f"""# Guía de despliegue técnico -- proyecto {project_id}

Este servicio (`interfaces/api/`) es un servicio hermano de la app de
escritorio RAG STUDIO, con su propio ciclo de instalación y
despliegue -- no requiere tener la app de escritorio abierta ni
instalada en la misma máquina. Este paquete trae los DATOS y la
CONFIGURACIÓN (instantánea, token, snippet); el CÓDIGO de RAG STUDIO
(el paquete Python, `interfaces/api/` incluido) se instala por
separado -- no viaja dentro de este .zip.

## 0. Dos carpetas distintas: el CÓDIGO y este PAQUETE

Este paquete (versión de instantánea **{snapshot_version}**) trae solo
DATOS y CONFIGURACIÓN. El servicio se ejecuta con el CÓDIGO de RAG
STUDIO, que se instala aparte. Distribución recomendada:

    /opt/ragstudio/                                   <- código de RAG STUDIO (contiene interfaces/ y pyproject.toml)
        .venv/                                        <- entorno virtual del CÓDIGO (no del paquete)
    /opt/entrega_cliente_{project_id}_v{snapshot_version}/   <- este .zip extraído
        manifest.json, GUIA_DESPLIEGUE.md, .env.example, ...
        instantanea/                                  <- RAGSTUDIO_SNAPSHOT_DIR
            project.db, snapshot_identity.json, indexes/...

En Windows, lo mismo con rutas como `C:\\ragstudio\\` y
`C:\\entregas\\entrega_cliente_{project_id}_v{snapshot_version}\\instantanea`.

- El entorno virtual pertenece al proyecto RAG STUDIO, no al paquete
  de entrega: nunca se crea dentro de la carpeta del paquete.
- `uvicorn` se ejecuta DESDE la carpeta del código (`/opt/ragstudio`),
  porque ahí está el módulo `interfaces`. Si debe ejecutarse desde otra
  carpeta, agrega `--app-dir /opt/ragstudio`.
- La carpeta del paquete solo se referencia mediante
  `RAGSTUDIO_SNAPSHOT_DIR`; no se copia dentro del código.

## 1. Instalar el código de RAG STUDIO

    cd /opt/ragstudio
    python -m venv .venv
    source .venv/bin/activate          # Windows: .venv\\Scripts\\Activate.ps1
    pip install -e '.[api]'

(el extra `api` agrega FastAPI/uvicorn, no necesarios para la app de
escritorio).

## 2. Extraer este paquete

`manifest.json`, en la raíz del paquete, identifica la entrega: `project_id`
y `snapshot_version` son la identidad del conocimiento entregado, y
`deployment_package_id` (igual a `package_id`) identifica solo esta
exportación física, que es nueva en cada exportación. Ver
`CONTRATO_INTEGRACION.md`, sección 1bis.

Extrae este .zip en su propia carpeta (por ejemplo
`/opt/entrega_cliente_{project_id}_v{snapshot_version}`). La ruta que
necesitas es la de su subcarpeta `instantanea/`, que contiene
`project.db` y `snapshot_identity.json` (proyecto `{project_id}`,
versión {snapshot_version}). No hace falta recrear ningún registro ni
copiarla a una instalación de escritorio.

## 3. Configurar variables de entorno

Variables obligatorias para este modo de despliegue (instantánea fija):

    RAGSTUDIO_SNAPSHOT_DIR=/opt/entrega_cliente_{project_id}_v{snapshot_version}/instantanea
    RAGSTUDIO_API_KEY=<la clave de .env.example>

`RAGSTUDIO_SNAPSHOT_VERSION` es opcional: el runtime toma la versión de
`instantanea/snapshot_identity.json` (aquí, {snapshot_version}). Si la defines,
funciona como verificación: debe valer {snapshot_version} o el runtime no
arranca.

`.env.example` sirve como plantilla para mecanismos que leen archivos
`.env` (`docker run --env-file .env`, `EnvironmentFile=` de systemd).
`uvicorn` NO lee `.env` por sí mismo: en una terminal exporta las
variables en el entorno del proceso.

Linux/macOS (bash):

    export RAGSTUDIO_SNAPSHOT_DIR=/opt/entrega_cliente_{project_id}_v{snapshot_version}/instantanea
    export RAGSTUDIO_API_KEY='<clave>'
    # opcional, solo como verificación:
    # export RAGSTUDIO_SNAPSHOT_VERSION={snapshot_version}

Windows (PowerShell):

    $env:RAGSTUDIO_SNAPSHOT_DIR = "C:\\entregas\\entrega_cliente_{project_id}_v{snapshot_version}\\instantanea"
    $env:RAGSTUDIO_API_KEY = "<clave>"
    # opcional, solo como verificación:
    # $env:RAGSTUDIO_SNAPSHOT_VERSION = "{snapshot_version}"

Todas las variables:

{variables_md}

## 4. Validar y arrancar el servicio

Primero valida la configuración sin arrancar nada (desde la carpeta del
código, con el entorno virtual activo):

    cd /opt/ragstudio
    python -m interfaces.api.check_config --verificar-huella

Responde `LISTO` con el proyecto, la versión y el perfil de embeddings
resueltos, o `NO LISTO` con la lista completa de problemas (carpeta
inexistente, se apuntó a la raíz del paquete en vez de `instantanea/`,
falta `project.db`, la versión no coincide, falta la clave, perfil de
embeddings distinto al del índice...). Corrige y repite hasta ver
`LISTO`. `--verificar-huella` comprueba además que el contenido de la
instantánea no se alteró desde que se publicó; úsalo antes del primer
arranque.

Después arranca el servicio (desde la misma carpeta):

    uvicorn interfaces.api.app:create_app_from_env --factory --host 0.0.0.0 --port 8000

`create_app_from_env` hace la misma validación: si algo no cuadra, el
proceso termina al arrancar con el mismo mensaje, en vez de servir una
identidad incorrecta.

Verifica el servicio en marcha:

    curl http://localhost:8000/health

Respuesta esperada para este paquete:

    {{"status": "ok", "loaded_projects": [], "snapshot_mode": "fija",
     "snapshot_project_id": "{project_id}", "snapshot_version": {snapshot_version},
     "embedding_profile": "..."}}

Si `snapshot_version` no es {snapshot_version} o `snapshot_project_id`
no es `{project_id}`, el proceso está sirviendo otra instantánea: detén
el servicio y revisa `RAGSTUDIO_SNAPSHOT_DIR`. `loaded_projects` se
llena tras el primer mensaje atendido (`{project_id}:{snapshot_version}`).
Las solicitudes a otro `project_id` responden 404.

## 5. Embeber el widget en el sitio del cliente

Pega el contenido de `widget-embed.html` en las páginas del sitio
donde deba aparecer el asistente, y reemplaza `data-api-base` por la
URL pública real donde quede expuesto este servicio (con HTTPS en
producción).

## 6. Revocar o renovar el token del widget

El token incluido en este paquete tiene id `{widget_token_id}` (el
valor completo está en `widget-embed.html`) y puede revocarse en
cualquier momento con la clave operativa (`RAGSTUDIO_API_KEY`):

    curl -X DELETE http://localhost:8000/projects/{project_id}/widget-tokens/{widget_token_id} \\
      -H "X-API-Key: <la clave operativa>"

Para emitir uno nuevo (por ejemplo, tras revocar el anterior), y ver
todos los tokens vigentes del proyecto (sin su valor real, solo para
identificarlos):

    curl -X POST http://localhost:8000/projects/{project_id}/widget-tokens \\
      -H "X-API-Key: <la clave operativa>"
    curl http://localhost:8000/projects/{project_id}/widget-tokens \\
      -H "X-API-Key: <la clave operativa>"

El token que trae este paquete (id `{widget_token_id}`) se emitió con
`max_access_level = "{max_access_level}"` -- SIN TECHO ("restringido"
ve todo lo que el proyecto tenga marcado como usable) a menos que se
indique lo contrario más abajo. Si este widget va a exponerse a un
público más amplio que el previsto originalmente y el proyecto ya
clasifica sus fuentes por nivel de confidencialidad (público, interno,
confidencial, restringido -- ver el Manual del Usuario, ficha de
fuente), conviene emitir un token nuevo con un techo explícito y
revocar este, mandando `max_access_level` en el cuerpo de la solicitud:

    curl -X POST http://localhost:8000/projects/{project_id}/widget-tokens \\
      -H "X-API-Key: <la clave operativa>" \\
      -H "Content-Type: application/json" \\
      -d '{{"max_access_level": "publico"}}'

Valores válidos: `publico`, `interno`, `confidencial`, `restringido`
(de más a menos restrictivo el nombre, pero de MENOS a MÁS permisivo
en cuánto deja ver -- "publico" es el techo más bajo, "restringido" no
impone ningún techo). Omitir el campo (como hace este paquete por
defecto) preserva el comportamiento de siempre: el widget ve todo lo
que ya podía ver antes de que existiera esta capacidad. Ver
`CONTRATO_INTEGRACION.md`, sección 3, sobre cómo este techo afecta a
`sources` en cada respuesta.

## 7. Canalización a un humano (opcional)

Si se requiere que el equipo del cliente se entere cuando el agente
deriva una conversación a un humano, configura
`RAGSTUDIO_CHANNELING_WEBHOOK_URL` con la URL de un endpoint propio
que reciba esas notificaciones (ver `.env.example`). Ese aviso se
entrega en la misma solicitud del visitante (con un tope de espera de
5 segundos por intento) -- si el destino es lento, conviene que ese
endpoint responda rápido y haga su propio procesamiento después. Si el
primer intento falla (un blip de red transitorio), se reintenta una
vez más antes de darse por vencido; si aun así falla, el visitante
sigue recibiendo el mensaje de canalización con normalidad (nunca se
le hace esperar por eso ni se le muestra un error), pero el fallo
queda registrado en `logs/ragstudio-api.log` (ver sección 9) -- conviene
revisar ese archivo de vez en cuando si esta variable está configurada,
para notar si el destino empieza a fallar de forma sostenida.

## 8. Un solo visitante a la vez por instantánea

Este proceso atiende cada instantánea (un proyecto en una versión
dada) de una en una internamente, para evitar un conflicto conocido
del índice de búsqueda local con dos solicitudes simultáneas -- un
tráfico alto y sostenido de un mismo proyecto hace fila, no falla.
Proyectos distintos (o versiones distintas del mismo proyecto) se
siguen atendiendo en paralelo sin este límite.

## 9. Diagnóstico y límite de tasa (recomendado antes de un lanzamiento público)

El servicio escribe su propio registro operativo en
`logs/ragstudio-api.log` (dentro de `RAGSTUDIO_HOME`, con rotación
automática; la primera línea de cada arranque resume proyecto,
versión y perfil servidos) -- consúltalo primero si
algo no funciona como se espera; nunca contiene el texto de los
mensajes de los visitantes (eso vive en la pestaña Monitoreo de RAG
STUDIO, no aquí).

Si el widget va a embeberse en un sitio con visitantes anónimos (no
solo un piloto interno), conviene configurar
`RAGSTUDIO_RATE_LIMIT_PER_MINUTE` con un tope razonable para el
tráfico esperado (por ejemplo, 30) -- sin él, el servicio no frena a
un origen que mande solicitudes sin parar, y dado que cada instantánea
atiende "un visitante a la vez" (punto 8), eso puede hacer fila para
el resto de los visitantes legítimos. Al excederse el límite, el
servicio responde 429 en vez de encolar indefinidamente.

## 10. Retención de la bitácora de conversaciones (recomendado)

`runtime.db` guarda, sin límite de tiempo por defecto, el texto real
de cada mensaje que un visitante le escribió al agente -- si el
proyecto puede recibir datos personales (nombres, matrículas,
cualquier dato que alguien decida escribir), conviene definir cuánto
tiempo conservarlos y purgar el resto periódicamente; cuántos días es
una decisión del cliente/operador, no algo que RAG STUDIO fije por
defecto.

Para purgar, con el mismo código ya instalado en el paso 1 (no
requiere que el servicio esté corriendo):

    python -m interfaces.api.purge_conversations --retention-days 90 --dry-run
    python -m interfaces.api.purge_conversations --retention-days 90

El primer comando solo informa cuántas conversaciones se borrarían;
el segundo las borra de verdad y deja constancia en
`logs/ragstudio-api.log`. Para automatizarlo, prográmalo con `cron` (o
un temporizador de systemd) con la periodicidad y la ventana de
retención que correspondan -- por ejemplo, una vez al día.

Cifrado en reposo de `runtime.db` (y de la instantánea) no es algo que
este paquete resuelva: es responsabilidad de dónde se despliegue
(un volumen o disco cifrado), el mismo criterio que ya aplica a HTTPS
(ver "Hospedaje" en `INFORME_ENTREGA.md`).

## 11. Escalar más allá de un proceso (tráfico alto y sostenido)

El punto 8 ya explica que un solo proceso atiende cada instantánea "de
una en una" -- un límite real, no cosmético: bajo tráfico alto y
sostenido de un mismo proyecto, las solicitudes hacen fila dentro del
propio proceso y la latencia percibida por los visitantes crece con la
cola. Si eso ya está ocurriendo (revísalo en `logs/ragstudio-api.log`,
por los tiempos de `latencia_ms` de cada mensaje atendido), la forma
de escalar es correr **varias réplicas independientes** de este
servicio (varios procesos, contenedores o instancias systemd) detrás
de un balanceador de carga (nginx, un Application Load Balancer, etc.)
que reparta las solicitudes entre ellas -- no hace falta afinidad de
sesión: desde la Ronda 12, el estado de una conversación de varios
turnos vive en el navegador del visitante (el widget), no en este
servicio, así que dos mensajes consecutivos del mismo visitante pueden
caer en réplicas distintas sin ningún problema.

Al montar varias réplicas, dos cosas deben tratarse de forma distinta:

- **La instantánea (`RAGSTUDIO_SNAPSHOT_DIR`): cada réplica necesita su
  PROPIA COPIA**, no la misma ruta compartida entre procesos. El
  índice de búsqueda local (Qdrant embebido) toma un bloqueo exclusivo
  del sistema de archivos mientras un proceso lo tiene abierto; dos
  procesos SIN RELACIÓN entre sí (a diferencia de dos hilos dentro del
  mismo proceso, ya protegidos por el candado de `RuntimeContext`, ver
  punto 8) que abran la MISMA carpeta de índice bajo tráfico
  concurrente real chocan de forma intermitente contra ese bloqueo, con
  un error 500 explícito para el visitante que perdió la carrera. Esto
  se verificó de forma real (no es una suposición): dos procesos reales
  apuntando a la misma carpeta de instantánea, bajo 60 solicitudes
  concurrentes, produjeron 3 fallos con 500 (`RuntimeError: Storage
  folder ... is already accessed by another instance of Qdrant
  client`); los mismos 60 mensajes contra dos procesos con una COPIA
  propia cada uno terminaron en 0 fallos. Extrae este .zip (o, si
  tienes varios paquetes de entrega del mismo proyecto, la carpeta
  `instantanea/`) una vez POR RÉPLICA, en una ruta distinta.
- **La bitácora de conversaciones (`RAGSTUDIO_RUNTIME_DB_PATH`,
  `runtime.db`): al contrario, todas las réplicas deben apuntar al
  MISMO archivo** (en un volumen/disco compartido entre las réplicas,
  por ejemplo un volumen de red o un disco de red montado en todas).
  `runtime.db` es SQLite en modo WAL, que sí tolera varios procesos
  leyendo y escribiendo a la vez (es el mismo mecanismo que ya usan la
  app de escritorio y este servicio entre sí) -- si en cambio cada
  réplica escribiera su propio `runtime.db` por separado, la pestaña
  Monitoreo de RAG STUDIO (que lee un solo archivo) solo vería una
  fracción de las conversaciones reales, según cuál réplica atendió
  cada visitante.

Con esto, cada réplica adicional multiplica la capacidad disponible
para EL MISMO proyecto (más allá de la cola de "un visitante a la vez"
de una sola réplica) sin arriesgar la corrección: en una verificación
real con dos réplicas (cada una con su copia propia de la instantánea)
recibiendo la misma carga concurrente que una sola réplica, las dos
réplicas juntas atendieron más solicitudes por segundo que una sola,
sin ningún error, mientras que compartir una sola carpeta de
instantánea entre procesos sí produjo errores reales para algunos
visitantes. Las cifras exactas de velocidad dependen por completo del
hardware donde se despliegue (núcleos de CPU disponibles, sobre todo)
-- no se repiten aquí porque no serían representativas de tu máquina de
producción; lo que sí es una garantía de diseño, verificada, es la
comparación relativa: copia propia por réplica = sin errores;
carpeta compartida entre procesos = riesgo real de 500 intermitentes.

## 12. Observabilidad básica (opcional): GET /projects/{project_id}/metrics

Pista C.1 del ADR-003 (docs proyecto/RAG_STUDIO_Propuesta_C1_Observabilidad.docx):
un resumen agregado sobre la misma bitácora de conversaciones que ya
usa la pestaña Monitoreo de la app de escritorio (turnos totales,
conteo por acción, latencia promedio, tasa de abstención) -- mismo
criterio de protección que `/widget-tokens` (punto 6): SOLO con la
clave operativa (`X-API-Key`), nunca con un token de widget, porque no
es información que deba llegarle a un visitante final.

    curl http://localhost:8000/projects/{project_id}/metrics \\
      -H "X-API-Key: <la clave operativa>"

Acepta un parámetro opcional `since` (fecha/hora ISO 8601) para acotar
la ventana -- por ejemplo, `?since=2026-08-01T00:00:00Z` agrega solo
los turnos desde esa fecha. Sin `since`, agrega todo el histórico del
proyecto. `avg_latency_ms`, `p95_latency_ms`, `p99_latency_ms` y
`abstention_rate` llegan como `null` cuando no hay ningún turno que
promediar en la ventana pedida (nunca `0.0`, que sería un dato falso).
Desde la Ronda 93, `failed_turns` y `failure_rate` cuentan los turnos
que no pudieron atenderse por un error técnico (acción `fallo` en
Monitoreo); esos turnos NO entran en `abstention_rate` (que se calcula
sobre turnos atendidos) ni en las latencias. Sin fallos, los valores
son idénticos a los de versiones anteriores.
`p95_latency_ms`/`p99_latency_ms` (Pista C.5 del ADR-003, roadmap de
pendientes de RAG 5, Ronda 44) son los percentiles 95 y 99 de la
latencia -- útiles para detectar turnos lentos que el promedio
esconde. Esta capacidad es enteramente opcional -- si no se usa, no
cambia nada del resto de este servicio ni de `POST /messages`.
"""


def _build_env_example(project_id: str, snapshot_version: int) -> str:
    # RAGSTUDIO_API_KEY (auditoría Ronda 10, hallazgo B10): se genera
    # un valor aleatorio real por cada exportación, no una cadena fija
    # ("cambia-esto-por-una-clave-secreta") repetida en todos los
    # paquetes entregados -- si el operador copia este archivo tal
    # cual a `.env`, el runtime queda protegido por un secreto único
    # de esta entrega, no por un valor público y predecible.
    random_api_key = secrets.token_urlsafe(32)
    lines = [
        f"# Plantilla de variables de entorno para interfaces/api/ -- proyecto {project_id}, "
        f"instantánea v{snapshot_version}",
        # Ronda 94: la lista sale de la misma tabla que la guía (no se escribe a mano).
        "# OBLIGATORIAS: " + ", ".join(n for n, req, _d in _env_vars_doc(snapshot_version) if req) + ".",
        "# Valida antes de arrancar: python -m interfaces.api.check_config (desde la carpeta del código).",
        "",
    ]
    for name, required, desc in _env_vars_doc(snapshot_version):
        lines.append(f"# [{'OBLIGATORIA' if required else 'opcional'}] {desc}")
        if name == "RAGSTUDIO_API_KEY":
            lines.append(f"{name}={random_api_key}")
        elif name == "RAGSTUDIO_SNAPSHOT_DIR":
            lines.append(f"{name}=/ruta/absoluta/a/entrega_cliente_{project_id}_v{snapshot_version}/instantanea")
        elif name == "RAGSTUDIO_SNAPSHOT_VERSION":
            # Ronda 94: comentada -- opcional; si se descomenta debe coincidir.
            lines.append(f"# {name}={snapshot_version}")
        else:
            lines.append(f"# {name}=")
        lines.append("")
    return "\n".join(lines)


def _build_contrato_integracion(project_id: str, project_name: str) -> str:
    # Ronda 19 (ver Validacion_observaciones_RAG_STUDIO.md, recomendación
    # #3 de la Ronda 18): dirigido a quien construya o mantenga el AGENTE
    # CONVERSACIONAL EXTERNO, no a quien opera el servicio (eso ya lo
    # cubre GUIA_DESPLIEGUE.md) -- describe la forma real de la
    # materia prima que POST /messages entrega, para que integrarla bien
    # no dependa de leer el código fuente de interfaces/api/.
    return f"""# Contrato de integración para el agente conversacional -- proyecto {project_name}

Este documento es para el equipo que construye o mantiene el AGENTE
CONVERSACIONAL EXTERNO que va a consumir la materia prima que expone
este servicio -- no para quien lo despliega u opera (eso lo cubre
`GUIA_DESPLIEGUE.md`). Describe la forma real de cada solicitud y
respuesta de `POST /projects/{project_id}/messages`, qué significa cada
resultado posible, y una plantilla de system prompt recomendada.

## 1. Lo más importante: este servicio NO genera lenguaje natural

RAG STUDIO recupera y evalúa la documentación de origen -- fragmentos
relevantes, intenciones, guardrails, canalización -- pero nunca redacta
una respuesta nueva con un modelo de lenguaje. Es responsabilidad de
SU agente (el LLM que ustedes aporten, con el system prompt que
definan) convertir lo que este servicio entrega en una respuesta final
para el usuario. Este es un límite de diseño deliberado, documentado
desde el origen de este servicio, no un defecto de esta entrega.

## 1bis. Identidades: qué identifica cada campo (Ronda 95)

`manifest.json` (raíz del paquete) trae un bloque `identity` y estos
campos, con significados distintos que no deben mezclarse:

| Campo | Identifica | ¿Cambia entre exportaciones? |
|---|---|---|
| `project_id` | El proyecto de RAG STUDIO (aquí `{project_id}`). En RAG STUDIO la unidad que se publica es el proyecto completo, con todos sus lotes. | No. Es igual para v2, v4, v5... del mismo proyecto. |
| `snapshot_version` | La versión publicada (v2, v4...). | Solo si se publica otra versión. |
| `snapshot_id` | El registro de esa versión publicada. | No, entre exportaciones de la misma versión. |
| `content_fingerprint` | El contenido de la instantánea (huella portable). | No, entre exportaciones de la misma versión. |
| `deployment_package_id` | ESTA exportación física (este .zip). | Sí: cada exportación recibe uno nuevo, aunque sea la misma versión. |
| `package_id` | Lo mismo que `deployment_package_id`. Se conserva con ese nombre solo por compatibilidad. | Sí. |
| `knowledge_base_id` | Reservado: identidad lógica portable del contrato NEXOM Knowledge Package v1.0.0 (incremento RAG-INC-01). | Hoy siempre `null`. |
| `source_batches` | Lotes de RAG CONTENT que alimentaron el proyecto (huella y etiqueta). Solo procedencia. | Crece cuando se importan lotes nuevos. |

Reglas para un consumidor que agrupa versiones (por ejemplo, NEXOM
Testing Agent):

- **Agrupar versiones sucesivas por `project_id`** (`grouping_key` en el
  bloque `identity`). Ordenarlas por `snapshot_version`.
- **No usar `package_id` ni `deployment_package_id` como identidad
  lógica**: sirven para auditar qué exportación física originó cada
  versión. Dos exportaciones de la misma versión son el mismo contenido
  (mismo `snapshot_id` y `content_fingerprint`) con distinto
  `deployment_package_id`.
- Si su producto mantiene su propio "package lógico" (por ejemplo,
  LIC_DAE dentro de AGENTE UDL), asócienlo por `project_id` más la
  selección o confirmación del operador, y guarden
  `deployment_package_id` solo como metadato de auditoría del artefacto
  importado, nunca como su clave lógica. RAG STUDIO no conoce ese nombre:
  publica el proyecto completo.
- Para reconocer una versión ya registrada: mismo `project_id`, mismo
  `snapshot_version` y mismo `content_fingerprint` es la MISMA versión
  (reimportarla no debe crear otra). Mismo `project_id` y
  `snapshot_version` con distinto `content_fingerprint` es una
  inconsistencia: hay que rechazarla y avisar, no sobrescribir.
  Excepción: si alguno de los dos manifiestos es anterior a la Ronda 95
  (sin `manifest_version` 2), su huella pudo calcularse al exportar una
  instantánea antigua y no ser comparable; en ese caso traten la
  diferencia como advertencia para revisión del operador, no como
  rechazo automático. Entre manifiestos `manifest_version` 2, el mismo
  `snapshot_id` confirma que es la misma versión publicada.
- `project_id` cambia si el proyecto se importa en RAG STUDIO "como
  copia" (con otro id). En ese caso es otro proyecto y empieza otra
  agrupación. `knowledge_base_id` resolverá ese caso cuando exista.
- Los paquetes exportados antes de la Ronda 95 no traen
  `deployment_package_id` ni `identity`. Para ellos, `package_id` es
  igualmente el id de la exportación y `project_id` + `snapshot_version`
  (claves de nivel superior) dan la misma agrupación.
Ejemplo (mismo proyecto, dos versiones exportadas en momentos distintos):

```text
exportación 1                                 exportación 2
"identity": {{                                 "identity": {{
  "project_id": "6073eda1-...",                  "project_id": "6073eda1-...",
  "snapshot_version": 2,                         "snapshot_version": 4,
  "snapshot_id": "a1...",                        "snapshot_id": "b7...",
  "content_fingerprint": "sha256:9c...",         "content_fingerprint": "sha256:41...",
  "deployment_package_id": "1d8fdf60-...",       "deployment_package_id": "3af073c9-...",
  "knowledge_base_id": null,                     "knowledge_base_id": null,
  "grouping_key": "project_id"                   "grouping_key": "project_id"
}}                                              }}
```

Ambas pertenecen al mismo grupo (`project_id` igual): el consumidor
registra `AGENTE UDL -> [su package lógico] -> v2, v4` y conserva cada
`deployment_package_id` como el artefacto físico que originó cada versión.

- El runtime en marcha informa en `GET /health` el `snapshot_project_id`
  y el `snapshot_version` que sirve: coinciden con `project_id` y
  `snapshot_version` del manifiesto.

## 2. Forma de la solicitud

```json
POST /projects/{project_id}/messages
{{
  "message": "¿cuál es el horario de atención?",
  "variables": {{}},
  "conversation_id": null
}}
```

- `message` (obligatorio, 1 a 2000 caracteres): la pregunta real del
  usuario final, tal cual la escribió -- no la reformulen ni le agreguen
  contexto antes de enviarla.
- `variables` (opcional, por defecto `{{}}`): datos que ya se conocen de
  esta conversación (ver sección 5, "aclarar").
- `conversation_id` (opcional, nuevo en esta ronda -- ver sección 4):
  omítanlo (o manden `null`) en el primer mensaje de una conversación
  nueva; reenvíen el que la respuesta les devuelva en los mensajes
  siguientes de la MISMA conversación.

Autenticación: encabezado `X-Widget-Token` (recomendado para un agente
que atiende visitantes anónimos) o `X-API-Key` (solo para un piloto de
un único sitio de confianza) -- ver `GUIA_DESPLIEGUE.md` para cómo se
emiten y revocan.

## 3. Forma de la respuesta

```json
{{
  "action": "responder",
  "response_text": null,
  "matched_intent": "Consultar horario",
  "confidence": 0.87,
  "sources": [
    {{"source_id": "s1", "chunk_id": "c1", "text": "El horario es de 9 a 17.", "score": 0.91,
     "page_start": 2, "page_end": 2, "section_title": "Horario de atención"}}
  ],
  "snapshot_version": 3,
  "log_id": "...",
  "conversation_id": "...",
  "latency_ms": 42.3,
  "trace_id": "...",
  "missing_variables": [],
  "structured_result": null,
  "image_results": []
}}
```

`sources` es la materia prima real -- el resultado de la búsqueda
semántica ya evaluada contra las compuertas de calidad del proyecto
(fuentes vigentes y validadas, ver el Manual del Usuario, capítulo 5.4).
Cada elemento trae el fragmento de texto completo (`text`), de qué
fuente viene (`source_id`) y qué tan relevante resultó (`score`, 0 a 1,
mayor es más relevante). `page_start`/`page_end` (Pista C.5 del
ADR-003, roadmap de pendientes de RAG 5) son la página donde empieza y
termina el fragmento -- solo para fuentes PDF; `null` en ambos para
fuentes sin páginas (TXT/DOCX/Markdown) o cuando no se pudo resolver.
Útiles si quieren que su LLM cite "según la página 2 del documento" en
vez de solo repetir el texto. `section_title` (Ronda 58) es el título
de la sección o encabezado bajo el que cayó el fragmento (p. ej.
"Horario de atención") -- `null` cuando la fuente no se fragmentó por
encabezados. Los tres campos son aditivos y opcionales: una integración
que hoy solo lee `text`/`score` sigue funcionando igual si los ignora.

Control de acceso (Pista B.3 del ADR-003): el token con el que ustedes
autentiquen cada solicitud (`X-Widget-Token`, ver sección 2 y
`GUIA_DESPLIEGUE.md`) puede tener un TECHO de nivel de confidencialidad
asignado al emitirse -- si lo tiene, `sources` ya viene filtrado del
lado del servidor para excluir cualquier fragmento de una fuente por
encima de ese techo, ANTES de llegar a esta respuesta. Su integración
no necesita (ni puede) aplicar ningún filtro propio de confidencialidad
sobre `sources`: si un fragmento aparece aquí, el propio servicio ya
determinó que el canal autenticado tiene permitido verlo. El token
usado para EL PAQUETE DE ENTREGA que acompaña a este contrato no tiene
techo asignado (ve todo lo que el proyecto tenga marcado como usable) a
menos que quien opere el servicio haya emitido uno nuevo con un techo
explícito -- ver `GUIA_DESPLIEGUE.md`, sección 6.

`structured_result` (enrutamiento multi-índice determinista, Pista B.4
del ADR-003): campo ADITIVO, presente solo cuando la intención
reconocida está configurada para resolverse contra un bloque de datos
estructurados (una hoja XLSX o un CSV ya ingerido, en vez de -- nunca
además de -- fragmentos de texto libre) y encontró al menos una fila.
Cuando llega distinto de `null`, `sources` viene vacío para ese mismo
turno: son dos caminos mutuamente excluyentes para la misma respuesta,
nunca ambos a la vez. Su forma:

```json
"structured_result": {{
  "rows": [
    {{"chunk_id": "c9", "source_id": "s5", "section_title": "Costos", "row_index": 3,
     "values": {{"plantel": "Campus Norte", "costo": "1500"}}}}
  ],
  "aggregation": null
}}
```

`rows` es la lista de filas ya filtradas (cada `values` es el registro
completo de esa fila, con los nombres de columna reales del archivo de
origen) -- páselas a su LLM generador exactamente como pasaría
`sources`, con la misma instrucción de "responde solo con base en
esto". `row_index` (Pista C.2a del ADR-003) es la posición de esa fila
dentro del bloque de origen -- útil si quieren que su LLM cite "la fila
4 de la hoja Costos" en vez de solo repetir los valores; es opcional
usarlo, dos filas con los mismos `values` solo se distinguen por este
campo. `aggregation` queda reservado para una fase futura de RAG
STUDIO (sumas, promedios, conteos agrupados) -- en esta versión del
contrato siempre llega `null`; ignórenlo con seguridad. Una integración
que hoy solo lee `sources` sigue funcionando exactamente igual si
nunca revisa `structured_result` -- no es un cambio disruptivo del
contrato existente, es una capacidad nueva y opcional.

## 4. `conversation_id`: cómo mantener el contexto de una conversación

Este servicio no mantiene ninguna sesión propia del lado del servidor
más allá de agrupar sus turnos bajo un mismo `conversation_id` para
fines de auditoría (pestaña Monitoreo) y mejora continua (banco de
pruebas de calidad) -- la lógica de qué responder en cada turno sigue
sin depender de turnos anteriores, salvo por las `variables` que
ustedes mismos reenvíen (sección 5).

- Primer mensaje de una conversación nueva: omitan `conversation_id` (o
  manden `null`). La respuesta siempre trae uno, generado por el
  servidor.
- Mensajes siguientes de la MISMA conversación: reenvíen ese mismo
  valor tal cual. Si lo omiten, cada mensaje se registra como una
  conversación nueva e independiente -- sin error, pero sin poder
  reconstruir después que eran la misma conversación.
- No hace falta ningún formato particular: es un identificador opaco,
  generado por el servidor -- no lo construyan ustedes mismos ni le
  asuman ninguna estructura.

## 5. Qué hacer con cada valor de `action`

- **`responder`**: el motor encontró contenido relevante y suficiente,
  en `sources` (fragmentos de texto) o en `structured_result` (filas de
  un bloque de datos estructurados -- ver sección 3; nunca los dos a la
  vez). `response_text` siempre llega `null` -- es la señal de que le
  corresponde a SU LLM generador redactar la respuesta final a partir
  de lo que sí venga poblado, con el system prompt de la sección 6. Si
  ambos vienen vacíos, no hay nada relevante que mostrar: no le pidan a
  su LLM que "invente" una respuesta de todos modos.
- **`aclarar`**: falta un dato obligatorio para resolver la intención
  reconocida. `response_text` ya trae la pregunta aclaratoria lista
  para mostrar tal cual (no necesita su LLM); `missing_variables[0]` es
  el nombre de la variable a la que corresponde. En el siguiente mensaje,
  manden la respuesta del usuario como `variables: {{"<esa variable>":
  "<lo que contestó>"}}`, junto con el `message` ORIGINAL (no el de la
  aclaración) y el mismo `conversation_id`.
- **`abstenerse`**: el motor decidió, por diseño, no responder (baja
  confianza, guardrail de seguridad/privacidad, etc.). `response_text`
  trae el motivo en lenguaje humano, listo para mostrar. No intenten
  "forzar" una respuesta con su LLM en este caso -- la abstención es
  una decisión de negocio ya evaluada contra las reglas del proyecto,
  no una falta de información que su LLM pueda compensar.
- **`canalizar`**: el motor decidió derivar a una persona. `response_text`
  trae el mensaje para el usuario. Si además necesitan que su propio
  sistema se entere de la derivación (para atenderla de verdad), pídanle
  a quien opera este servicio que configure `RAGSTUDIO_CHANNELING_WEBHOOK_URL`
  (ver `GUIA_DESPLIEGUE.md`, sección 7) en vez de intentar inferirlo
  solo de esta respuesta.

## 5bis. Cuando la solicitud falla: categoría, etapa y Trace ID (Ronda 93)

Envíen en cada solicitud un encabezado `X-Trace-Id` con su propio
identificador de caso o de corrida (letras, dígitos y `._:-`, hasta 128
caracteres). El servicio lo devuelve en el encabezado de respuesta
`X-Trace-Id`, en el campo `trace_id` de la respuesta y en
`logs/ragstudio-api.log`. Si no lo envían, el servicio genera uno.

Si el turno no se puede atender por un error técnico, la respuesta NO es
un texto plano: es JSON con la causa clasificada.

```json
HTTP 500 (motor) / 503 (no se pudo cargar la instantánea) / 404 (instantánea inexistente)
{{
  "detail": "Falló el cálculo de embeddings de la consulta (embedding_error): ...",
  "error": {{
    "category": "embedding_error",
    "stage": "embeddings_consulta",
    "code": "embedding.RuntimeError",
    "message": "Falló el cálculo de embeddings de la consulta (embedding_error): ...",
    "trace_id": "el-que-ustedes-enviaron",
    "log_id": "id del turno fallido en runtime.db",
    "snapshot_version": 2,
    "exception_type": "RuntimeError",
    "timestamp": "2026-10-06T18:00:00+00:00",
    "retryable": false
  }}
}}
```

- `category` (nunca vacía): `retrieval_error`, `embedding_error`,
  `timeout`, `configuration_error`, `snapshot_error`, `guardrail_error`,
  `intent_error`, `source_error`, `storage_error`, `infrastructure_error`,
  `unexpected_exception` (excepción real en un componente sin categoría
  más específica) o `unclassified` (sin evidencia para clasificar).
  `llm_error` está reservada: este servicio no llama a ningún modelo de
  lenguaje, así que un error de SU LLM nunca vendrá de aquí.
- `stage`: `carga_instantanea`, `embeddings_consulta`,
  `deteccion_intencion`, `deteccion_variables`, `filtrado_metadatos`,
  `busqueda`, `reordenamiento`, `guardrails`, `registro_bitacora`,
  `motor_conversacional` o `desconocida`.
- `retryable`: `true` cuando reintentar más tarde puede funcionar
  (bloqueo temporal del índice o de la base, tiempo de espera).
- El turno fallido queda en la pestaña Monitoreo de RAG STUDIO (acción
  `fallo`) con la categoría, la etapa, el detalle técnico y el mismo
  `trace_id`.
- Errores de la propia solicitud -- credencial inválida (401), cuerpo
  inválido (422), límite de tasa (429, con `Retry-After`) -- NO traen el
  objeto `error`: responden `{{"detail": ...}}` (formato estándar). No son
  fallos del motor; clasifíquenlos de su lado (p. ej. configuración del
  agente o límite de tasa). El turno tampoco se guarda en Monitoreo.

Recomendación para un agente de pruebas: mapeen `error.category` a su
columna de categoría de error y `error.trace_id`/`error.log_id` a su
evidencia. Si su propio proceso falla ANTES de recibir respuesta de este
servicio (tiempo de espera de red, su LLM), esa categoría es suya: este
servicio no la puede conocer.

## 6. Plantilla de system prompt recomendada (para la acción `responder`)

Cuando `action` es `"responder"`, este es un punto de partida razonable
para el system prompt de su LLM generador -- ajústenlo al tono y las
políticas propias de {project_name}:

```
Eres el asistente conversacional de {project_name}. Responde
ÚNICAMENTE con base en los fragmentos de contexto que se te
proporcionan a continuación -- nunca completes con conocimiento
propio ni inventes datos que no estén en ellos.

Si los fragmentos no contienen información suficiente para responder
con confianza, dilo explícitamente en vez de especular.

Cuando afirmes algo basado en un fragmento, ese fragmento ya fue
seleccionado como el más relevante para la pregunta -- no hace falta
que cites su identificador interno al usuario final, pero sé fiel a
su contenido literal.

Responde en el mismo idioma en el que te escribió el usuario, en tono
claro y directo.
```

## 7. Reportar retroalimentación de relevancia (opcional, Pista C.4a del ADR-003)

Capacidad opcional -- su integración sigue funcionando exactamente
igual si nunca la usa. Permite reportar, para un turno ya atendido, si
alguna de las fuentes que `sources` les entregó fue relevante,
irrelevante, o si de verdad la usaron al construir la respuesta final
que le mostraron al usuario:

```json
POST /projects/{project_id}/messages/{{log_id}}/feedback
{{
  "entries": [
    {{"source_id": "s1", "signal": "citado_en_respuesta"}},
    {{"source_id": "s2", "signal": "irrelevante"}}
  ]
}}
```

- `{{log_id}}` es el `log_id` que la respuesta original de `POST
  /messages` ya les devolvió para ese mismo turno -- no hace falta
  ningún dato nuevo que no tuvieran ya.
- `source_id` (y, opcionalmente, `chunk_id`) son los mismos que ya
  venían en `sources` de esa respuesta.
- `signal` es una de tres: `"relevante"` / `"irrelevante"` (un juicio
  explícito sobre esa fuente) o `"citado_en_respuesta"` (no es un
  juicio -- es que de verdad se apoyaron en ella para construir la
  respuesta final, sin que eso implique evaluarla como correcta).
- Autenticación: la misma credencial (`X-Widget-Token` o `X-API-Key`)
  que ya usaron para el `POST /messages` original.
- Respuesta: `{{"recorded": N}}` con cuántas señales se guardaron.
- RAG STUDIO NO ajusta ningún parámetro de búsqueda automáticamente a
  partir de estas señales en esta versión -- se capturan para
  observabilidad y para una fase futura de mejora continua, nunca
  cambian el comportamiento de un turno futuro por sí solas.

## 7bis. `image_results`: búsqueda por similitud visual (opcional, Fase 3 de multimodalidad nativa, RAG 3)

Campo ADITIVO, presente solo si el proyecto tiene fuentes de tipo Imagen indexadas y este turno resultó en `action: "responder"` -- una integración que hoy solo lee `sources` sigue funcionando exactamente igual si lo ignora. A diferencia de `structured_result` (sección 3), `image_results` NUNCA reemplaza a `sources`: es un TERCER canal de evidencia, independiente y nunca fusionado con los otros dos, porque texto e imágenes viven en espacios vectoriales distintos y no comparables (mezclarlos produciría un orden sin sentido). Su forma:

```json
"image_results": [
  {{"source_id": "s7", "chunk_id": "c22", "image_relative_path": "logo-institucional.png", "score": 0.88}}
]
```

- `score` (0 a 1, mayor es más relevante) es una similitud visual/semántica calculada en un espacio vectorial propio de imágenes -- NO es comparable numéricamente contra el `score` de `sources` (no resten ni combinen ambos puntajes).
- `image_relative_path` es la ruta del archivo de imagen, relativa a `sources/original/` dentro de la instantánea publicada que sirve este proyecto -- puede venir `null` si la fuente todavía no tiene una copia de archivo legible.
- **Limitación conocida, no un descuido**: esta versión del servicio no expone ningún endpoint HTTP para descargar el archivo de imagen a partir de `image_relative_path` -- solo se entrega la referencia. Si su agente corre en un proceso o una red separada de la instalación de RAG STUDIO, sin acceso compartido al sistema de archivos de la instantánea publicada, hoy no podrá resolver esta ruta a un archivo real; consideren esto antes de construir una integración que dependa de mostrar la imagen misma (no solo su referencia) al usuario final.
- Igual que en `sources`, el control de acceso de la Pista B.3 del ADR-003 (sección 3, párrafo de "Control de acceso") ya se aplicó del lado del servidor antes de que un elemento llegue a `image_results`.

## 7ter. `execution`: datos de ejecución para diagnóstico (Ronda 104b)

Campo ADITIVO, presente **solo** cuando la solicitud usa la clave operativa
(`X-API-Key`); con un token de widget (`X-Widget-Token`) llega `null`. Una
integración que lo ignore sigue funcionando igual. Contiene, sin
credenciales, rutas ni secretos:

```json
"execution": {{
  "format_version": 1,
  "code": {{"version": "0.1.0", "commit": "…", "commit_source": "build_info|git|null",
            "dirty": false, "fingerprint": "…", "unknown": []}},
  "snapshot": {{"project_id": "…", "version": 2, "declared_fingerprint": "sha256:…",
                "fingerprint_at_load": "sha256:…", "fingerprint_matches": true}},
  "index": {{"embedding_model": "…", "dimensions": 384, "points_count": 120,
             "query_embedding_profile": "simetrico"}},
  "retrieval_pipeline": "r102",
  "reranking": {{"setting": "automatico", "model_available": false, "applied": false, "model": null}},
  "search_text": "¿Qué documentos necesito para entrar ?",
  "applied_filters": {{"nivel_academico": "bachillerato"}},
  "results": [{{"position": 1, "chunk_id": "…", "source_id": "…", "score": 0.031,
               "retrieval_rank": 4, "affinity": 0.4}}],
  "unknown": []
}}
```

- `unknown` enumera lo que el servicio no pudo determinar (p. ej. `code.commit`
  si el código se instaló sin `.git` ni `build_info.json`): nunca se inventa.
- `snapshot.fingerprint_matches = false` indica que la instantánea cambió
  desde su publicación (por ejemplo, la abrió antes un proceso que le aplicó
  migraciones).
- Con la clave operativa, cada elemento de `sources` trae además
  `retrieval_rank` y `affinity`.
- Lo mismo queda guardado en `runtime.db` (`conversation_log.execution` y
  `conversation_log.chunk_ids`, en orden), localizable por `trace_id`.
- `GET /health` (público) informa `code_version` y `retrieval_pipeline`;
  `GET /health/details` (con `X-API-Key`) informa commit, huella del código,
  identidad de la instantánea servida, índice y disponibilidad del reranker.

## 8. Preguntas frecuentes

- **¿Podemos ignorar `conversation_id` y llevar nuestro propio manejo de
  sesión?** Sí -- es opcional. Si no lo reenvían, cada mensaje se trata
  como una conversación nueva del lado de RAG STUDIO (afecta solo a la
  bitácora de Monitoreo, no a la calidad de la respuesta de un turno
  individual).
- **¿Por qué `response_text` viene `null` para `"responder"` pero no
  para las demás acciones?** Porque solo `"responder"` depende de
  contenido variable de la documentación -- las demás (`aclarar`,
  `abstenerse`, `canalizar`) usan texto ya redactado y aprobado dentro
  del diseño conversacional del proyecto, no algo que su LLM deba
  reformular.
- **¿El `score` de `sources` es comparable entre distintos proyectos o
  entre corridas?** No hay esa garantía -- úsenlo solo para ordenar
  relativamente los resultados de UNA misma respuesta, no como un
  umbral absoluto reutilizable en su propio código.

## 9. Doble validación de calidad (opcional, Ronda 59): GET /projects/{project_id}/quality

Si además de evaluar la calidad de las respuestas con su propio
criterio ustedes quieren leer también la evidencia de calidad que RAG
STUDIO ya calcula sobre este proyecto (su banco de pruebas de Calidad),
este endpoint expone la corrida de evaluación más reciente de alcance
"completa":

```json
GET /projects/{project_id}/quality
{{
  "project_id": "{project_id}",
  "has_complete_run": true,
  "last_run_id": "...",
  "last_run_started_at": "...",
  "last_run_finished_at": "...",
  "overall_verdict": "verde",
  "has_blocking_failures": false,
  "recall_at_3": 0.92,
  "mrr": 0.85,
  "regression_gate_passed": true,
  "regression_gate_reason": "..."
}}
```

- Autenticación: SOLO con la clave operativa (`X-API-Key`), nunca con
  un token de widget -- mismo criterio que `/metrics` (ver
  `GUIA_DESPLIEGUE.md`): es información sobre la salud del proyecto,
  no algo que deba ver el visitante final de un sitio.
- `has_complete_run` es `false` (con el resto de los campos en `null`)
  si el proyecto todavía no tiene ninguna corrida de evaluación de
  alcance "completa" registrada.
- `recall_at_3` y `mrr` son `null` si ningún caso de esa corrida
  declaró una fuente esperada -- no hay nada que cuantificar, no es un
  0.0 real.
- `regression_gate_passed`/`regression_gate_reason` reflejan el mismo
  resultado que la compuerta de liberación "Regresión de recuperación"
  -- `true` también cuando esa compuerta se da por cumplida por falta
  de datos (menos de dos corridas "completa" registradas todavía).
- Importante: estos datos se leen del proyecto en edición activa, no
  de la instantánea que sirve `POST /messages` -- si el proyecto sigue
  evolviendo después de publicar una instantánea, pueden no
  corresponder exactamente al contenido que esa instantánea sirve en
  un momento dado.

Un uso pensado para esta capacidad: si ustedes operan un agente de
pruebas propio que valida este proyecto antes de liberarlo a un
cliente final (ver sección 10), su tablero puede combinar sus propios
resultados con estas métricas -- una doble validación de calidad, sin
tener que abrir la aplicación de escritorio de RAG STUDIO. Es
enteramente opcional -- si no se usa, no cambia nada del resto de este
servicio.

## 10. Ambiente de pruebas pre-liberación (para un agente de validación propio)

Si antes de liberar este proyecto a un cliente final ustedes quieren
que un agente propio (por ejemplo, un entorno de pruebas interno)
consuma los mismos artefactos de conocimiento que recibiría ese
cliente, no hace falta esperar a la liberación formal -- este servicio
ya lo permite, sin ninguna capacidad adicional:

1. Publiquen una instantánea del proyecto (botón "Publicar
   instantánea…" de la pestaña Liberación, en la aplicación de
   escritorio) -- deliberadamente independiente de solicitar una
   liberación formal; un proyecto puede estar en cualquier estado de
   su ciclo de vida (incluido "en pruebas") y publicar una instantánea
   utilizable.
2. Emitan un token de widget para el proyecto (sección 2) -- tampoco
   exige que el proyecto esté liberado.
3. Su agente de pruebas llama a `POST /projects/{project_id}/messages`
   con ese token, exactamente igual que lo haría el canal de
   producción final -- recibe los mismos fragmentos, páginas, títulos
   de sección y (si corresponde) resultados estructurados que recibiría
   el agente conversacional del cliente.

Cuando terminen de validar y decidan liberar el proyecto de verdad, no
hay que deshacer nada de lo anterior: pueden seguir usando el mismo
token (o revocarlo y emitir uno nuevo, si prefieren separar el tráfico
de pruebas del tráfico real) y publicar una instantánea más reciente
antes de entregarla al cliente final.
"""


def _build_widget_snippet(project_id: str, widget_token: str) -> str:
    # defer (auditoría Ronda 10, hallazgo A1): ya no es indispensable
    # -- WIDGET_JS captura document.currentScript en su ámbito síncrono
    # de ejecución, no dentro de init(), así que funciona con o sin
    # defer -- pero sigue siendo la práctica recomendada para no
    # bloquear el parseo de la página del cliente mientras se descarga
    # este script.
    return f"""<script
  defer
  src="https://TU-DOMINIO-AQUI/widget.js"
  data-project-id="{project_id}"
  data-api-base="https://TU-DOMINIO-AQUI"
  data-widget-token="{widget_token}"
  data-title="Asistente"
></script>
"""


class ExportDeploymentPackage:
    def __init__(
        self, project_repository: ProjectRepository, snapshot_repository: ProjectSnapshotRepository,
        widget_token_repository: WidgetTokenRepository, packager: DeploymentPackager,
    ):
        self._project_repository = project_repository
        self._snapshot_repository = snapshot_repository
        self._widget_token_repository = widget_token_repository
        self._issue_widget_token = IssueWidgetToken(widget_token_repository)
        self._packager = packager

    def execute(self, project_id: str, destination_path: str) -> str:
        project = self._project_repository.get(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        snapshot = self._snapshot_repository.get_latest(project_id)
        if snapshot is None:
            raise NoPublishedSnapshotError(project_id)

        token = self._issue_widget_token.execute(project_id)

        package = DeploymentPackage(
            project_id=project_id,
            project_name=project.name,
            snapshot_version=snapshot.version,
            snapshot_dir=snapshot.snapshot_dir,
            snapshot_id=snapshot.id,
            widget_token=token.token,
            widget_token_id=token.id,
            informe=_build_informe(project.name, project_id, snapshot.version),
            guia_despliegue=_build_guia_despliegue(project_id, token.id, snapshot.version, token.max_access_level),
            env_example=_build_env_example(project_id, snapshot.version),
            widget_snippet=_build_widget_snippet(project_id, token.token),
            contrato_integracion=_build_contrato_integracion(project_id, project.name),
        )
        try:
            return self._packager.export(package, destination_path)
        except Exception:
            # Auditoría Ronda 10, hallazgo B5: sin esta compensación, un
            # fallo del empaquetador (disco lleno, ruta sin permisos, a
            # mitad de copiar la instantánea) dejaba el token YA EMITIDO
            # activo en runtime.db sin que nadie lo supiera ni lo
            # revocara -- un token válido, indefinidamente, para un
            # paquete que nunca llegó a existir. Se revoca aquí y se
            # relanza el error original tal cual, para que quien llamó
            # siga viendo la causa real del fallo.
            RevokeWidgetToken(self._widget_token_repository).execute(token.id)
            raise
