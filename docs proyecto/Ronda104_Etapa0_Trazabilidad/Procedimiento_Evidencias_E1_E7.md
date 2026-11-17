# Procedimiento para recuperar las evidencias E1–E7 del incidente 493c8033

**Alcance.** El incidente ocurrió con la instantánea v2 **antes** de la Etapa 0. Ese Runtime no registraba versión de código, reranking, texto de búsqueda ni orden de fragmentos, así que esos datos **no existen para el trace 493c8033** y hay que reconstruirlos con las evidencias siguientes.

Los turnos atendidos por un Runtime actualizado a la Etapa 0 ya llevan todo esto en `runtime.db` y, con la clave operativa, en la respuesta (`execution`).

**Reglas:**
- **Copias, no originales.** Todo se hace sobre copias. No abrir la instantánea original con RAG Studio ni con el Runtime antes de copiarla (ver E6).
- **Ninguna evidencia lleva secretos.** No copiar en ellas `RAGSTUDIO_API_KEY`, tokens de widget, secretos de webhook ni archivos `.env`. Si un registro de Testing Agent incluye encabezados de autenticación, eliminarlos antes de compartirlo.
- **Resultados separados.** Los resultados de la reproducción exacta se registran aparte de la reproducción con supuestos.

## E1. Respuesta completa recibida por Testing Agent

- **Qué guardar:** el JSON íntegro de la respuesta de `POST /projects/b17cc73c-…/messages` del trace `493c8033-…` (identificador completo tal como figura en el informe original de NEXOM), más los encabezados de respuesta (sin los de autenticación).
- **Qué permite saber:**
  - el orden de `sources` (`chunk_id`, `score`);
  - **si hubo reranking**, por el rango de los puntajes:
    - la fusión RRF híbrida da puntajes entre 0 y ≈0.05 (tres listas con k = 60: como máximo 3/61 ≈ 0.049);
    - el cross-encoder da logits fuera de ese rango (p. ej. −3.6 o +4.1).

## E2. Turno en `runtime.db`

En el servidor del Runtime, sobre una **copia** de `runtime.db` (ruta: `RAGSTUDIO_RUNTIME_DB_PATH` o, si no está definida, la predeterminada dentro de `RAGSTUDIO_HOME`):

```
sqlite3 copia_runtime.db "select id, conversation_id, created_at, snapshot_version, message, matched_intent,
  confidence, action, source_ids, latency_ms, trace_id from conversation_log
  where trace_id like '493c8033%';"
```

En el incidente, `chunk_ids` y `execution` estarán vacíos (NULL), porque son anteriores a la Etapa 0. Eso no es un error: indica que esos datos no se registraron.

## E3. Solicitud enviada

Del registro de Testing Agent:
- el cuerpo exacto (`message`, `variables`, `conversation_id`);
- **qué tipo de credencial** se usó: clave operativa o token de widget, y con qué nivel de acceso máximo. No se necesita el valor de la credencial.

El nivel de acceso del token cambia las fuentes permitidas.

## E4. Código del Runtime

En la carpeta desde la que corre el Runtime:

1. **Si hay `.git`:**
   - `git rev-parse HEAD`;
   - `git status --short`, para ver si había cambios sin commit.
2. **Si no hay `.git`:** el nombre y el SHA-256 del ZIP de código desplegado (`sha256sum <zip>`). Si existe `build_info.json`, su contenido.
3. **En cualquier caso:**
   - la huella del código de la instalación, comparada con commits candidatos. En un checkout de RAG Studio, en el commit candidato:

     ```
     git checkout <commit candidato>
     python scripts/escribir_build_info.py --verificar <carpeta del Runtime>
     ```

     Compara la huella de cada carpeta común (`app`, `application`, `domain`, `infrastructure`, `interfaces`, `migrations`, `workers`) y responde COINCIDEN o NO COINCIDEN.
     - El script es de la Etapa 0: en commits anteriores no existe. Para esos commits, copie `scripts/escribir_build_info.py` e `infrastructure/build_info.py` del commit actual a una carpeta aparte, o compare dos carpetas con `diff -r`.
     - Candidatos: `af7c123` (Ronda 101), `3621dd5` (Ronda 102), `b43ae4f` (01d), y los ZIP entregados.
   - `pip freeze` del entorno del Runtime (versiones de `fastembed`, `onnxruntime`, `qdrant-client`).

## E5. Configuración del proceso

- Valores de `RAGSTUDIO_SNAPSHOT_DIR` (solo el nombre de la carpeta final, no la ruta completa si es sensible), `RAGSTUDIO_SNAPSHOT_VERSION`, `RAGSTUDIO_EMBEDDING_PROFILE` y `RAGSTUDIO_HOME`.
- Cómo se arrancó: servicio, Docker o comando.
- Nunca `RAGSTUDIO_API_KEY` ni secretos.

## E6. Instantánea servida

**Copia** de la carpeta de la instantánea v2 o del paquete de entrega `.zip`, preferentemente **la del paquete original** (el ZIP no se modifica al servir).
- **Cuidado al servir una carpeta:** el Runtime, al abrir `project.db`, puede aplicarle migraciones. Una carpeta ya servida puede no ser idéntica a la publicada.
- **Comprobación:** comparar el `content_fingerprint` de su `snapshot_identity.json` con el del manifiesto del paquete.

## E7. Inspección de la instantánea (solo lectura)

```
python "docs proyecto/Ronda104_Fragmentos_Puente/inspeccionar_instantanea.py" <E6> \
  --chunks <chunk puente 1>,<chunk puente 2>,<chunk de requisitos> \
  --json E7_inspeccion.json
```

> Los tres identificadores de fragmento (los dos puentes, `428a1151-…` y `59baa137-…`, y el de los requisitos, `8fe5e2de-…`) se copian completos del informe original de NEXOM y se verifican contra E1.

**Qué informa:**
- la identidad de la instantánea;
- la revisión de esquema;
- si existen `chunk.section_path` y `project.agent_reranking`;
- las políticas de fragmentación y la última política aplicada por fuente (**estrategia de los tres documentos compartidos**);
- fragmentos por fuente, incluidos los solo-YAML;
- el detalle de los tres fragmentos del trace.

## Reproducción exacta y criterio para darla por reproducida

1. Para cada versión candidata de código (E4), levantar el Runtime fijado a una **copia** de E6 (`RAGSTUDIO_SNAPSHOT_DIR`), con las bibliotecas de E4 y el perfil de E5.
2. Enviar la solicitud de E3 y comparar con E1.
3. **Se da por reproducido solo si se cumplen TODAS:**
   1. la misma acción, intención y confianza (a 3 decimales);
   2. la **misma lista ordenada** de `chunk_id` en `sources`;
   3. los mismos puntajes (a 3 decimales) y el mismo régimen de puntaje (RRF o reranker, ver E1);
   4. la versión de código usada coincide con la del Runtime del incidente por **commit** (E4.1/E4.2) **o por huella del código** (E4.3);
   5. la instantánea usada coincide con la servida por `content_fingerprint`.
4. **No basta** con que coincida la revisión de esquema de `project.db` (E7). Solo indica la versión mínima del código que abrió la base, no la que respondió. Tampoco basta con que coincida el orden con un código cuya identidad no se verificó en (4).
5. Si alguna condición no puede verificarse por falta de evidencia, el resultado se registra como «**compatible, no confirmado**», enumerando lo desconocido.
