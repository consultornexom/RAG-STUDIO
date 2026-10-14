# F-1 — Acta de revisión del borrador v0.1 y agenda de la sesión conjunta

**Fecha:** 2026-09-24
**Documento revisado:** `F-1_Esquema_Confianza_Firma_BORRADOR.md` (v0.1 con Anexo A), SHA-256 `3ba308bfa024577c26f1a9dd9c267a062b9982970b3eb2486065ff35499a293c`. Hash verificado por RAG Studio tras la revisión; coincide con el que citó NEXOM.
**Dictamen de NEXOM:** el v0.1 queda **aprobado como base oficial de trabajo de la sesión F-1**. No es una especificación implementable y no autoriza implementación. El v0.1 no se modifica, para que su hash siga siendo la referencia de esta revisión. Las correcciones se incorporarán en la v0.2.

**Alcance:** F-1 no obliga a modificar el contrato NKP 1.0.0 ni invalida su aceptación. Tampoco bloquea la importación de humo ni el hito 01a de RAG-INC-01. Es una capa posterior de autenticidad productiva y administración de confianza.

## 1. Correcciones bloqueantes para la v0.2

| # | Corrección | Qué debe quedar en la v0.2 |
|---|---|---|
| 1 | Integrar el Anexo A en el cuerpo normativo | Eliminar las alternativas que quedan en las secciones 6, 7 y 13. Una clave `revoked` invalida todas sus firmas; `revoked_at` no conserva firmas anteriores sin sellado de tiempo confiable. El nombre es **NEXOM Knowledge Package Trust Profile 1.0**; el `schema_version = 1.0.0` del paquete no cambia; no se anuncia NKP 1.1.0. El Anexo A desaparece como capa correctora |
| 2 | Raíz anclada fuera del almacén de confianza | La instalación del Runtime incluye, por un medio independiente: la clave pública raíz (o el conjunto de raíces), `root_key_id`, su huella SHA-256, el dominio de confianza y la versión inicial admitida. La rotación normal requiere la firma de la raíz anterior y de la nueva. La recuperación por pérdida o compromiso total sigue un procedimiento excepcional fuera de banda. Referencia: principios de confianza inicial, expiración y antirretroceso de TUF |
| 3 | Firmar el contexto, no solo el objeto JSON | Entrada criptográfica `"NEXOM-NKP-RELEASE/1\0" + RFC8785(statement)` para liberaciones y `"NEXOM-NKP-TRUST-STORE/1\0" + RFC8785(store)` para el almacén, con separación de contexto al estilo DSSE. `statement` incluye: tipo de declaración, versión del perfil, `producer_id`, ambiente, `package_id`, versión del contrato, hash del ZIP, `content_digest`, `checksums_json_hash`, fecha de firma e identificador de la liberación aprobada. Algoritmo: Ed25519 (RFC 8032) |
| 4 | Regla estricta para claves retiradas | `active` puede autorizar nuevas importaciones. `retired` no autoriza un paquete presentado por primera vez; los que ya se aceptaron con ella siguen válidos si constan en el registro del Runtime. `revoked` invalida todos los paquetes que firmó. Un paquete histórico puede volver a liberarse con una clave activa tras una revisión independiente. Motivo: sin sellado ni registro previo, `signed_at` no prueba que la firma sea anterior al retiro |
| 5 | Paquetes ya instalados | Registro de procedencia por paquete instalado: SHA-256 del ZIP, `package_id`, `content_digest`, `producer_id`, `key_id`, versión y hash del almacén usado, fecha de verificación, resultado y estado de confianza actual. Al aceptar un almacén nuevo: los paquetes de claves revocadas pasan a cuarentena; los de claves retiradas ya aceptados siguen activos; un almacén vencido bloquea nuevas importaciones, pero no necesariamente las bases instaladas. Toda cuarentena genera auditoría y una decisión operativa visible |
| 6 | Límites reales del antirretroceso | Estado protegido con: mayor versión aceptada, hash de esa versión, `issued_at`, último tiempo UTC observado e identificador de instalación. La especificación promete **solo** "detección de retroceso mientras se conserve el estado de seguridad de la instalación". Sin servidor, TPM o contador monotónico no hay solución absoluta. La recuperación de una instalación restaurada se hace con un paquete de recuperación firmado, nunca poniendo el contador a cero |
| 7 | El servicio productivo no firma digests a ciegas | El servicio de firma NEXOM recibe el ZIP candidato, calcula su SHA-256, lo valida, comprueba la aprobación de la liberación, construye él mismo la declaración canónica, la firma y registra la operación. El token local queda como contingencia para instalaciones completamente sin conexión |

## 2. Resoluciones recomendadas para F1-D1 a F1-D8

La sesión conjunta **ratifica** estas resoluciones o documenta cada excepción de forma explícita. No se mantienen abiertas más rondas.

| Decisión | Resolución recomendada por NEXOM |
|---|---|
| F1-D1 | Raíz fuera de línea, control dual real, respaldos cifrados con custodios separados y procedimiento formal de rotación |
| F1-D2 | Servicio de firma NEXOM en producción; firma local solo en DEMO/test; token como contingencia productiva sin conexión |
| F1-D3 | Una sola firma de productor en Trust Profile 1.0 |
| F1-D4 | Claves operativas de 12 meses, solapamiento de rotación de 30 días y almacén actualizado al menos cada 30 días |
| F1-D5 | Sin sellado de tiempo externo al principio |
| F1-D6 | Ancla raíz incluida con el Runtime; almacén inicial instalado y actualizaciones firmadas fuera de banda |
| F1-D7 | Firmar solo liberaciones aprobadas y ya validadas |
| F1-D8 | Revocación total, salvo futura evidencia de sellado de tiempo confiable |

## 3. Otros ajustes para la v0.2

- **Catálogo de errores** separado en:

  | Código | Código | Código |
  |---|---|---|
  | `ROOT_UNTRUSTED` | `TRUST_STORE_EXPIRED` | `TRUST_STORE_ROLLBACK` |
  | `TRUST_STATE_UNAVAILABLE` | `CLOCK_ROLLBACK_DETECTED` | `PRODUCER_NOT_AUTHORIZED` |
  | `KEY_RETIRED` | `KEY_REVOKED` | `ARCHIVE_DIGEST_MISMATCH` |
  | `PACKAGE_TRUST_REVOKED` | | |

- **Solo ZIP en producción.** La entrega como directorio queda para desarrollo y validación. Volver a comprimir produce otro SHA-256 y exige un sobre nuevo.

## 4. Notas de RAG Studio para la sesión (verificadas en el código actual)

Son aportes a la agenda, no decisiones.

- **Identificador de la liberación aprobada (corrección 3 y F1-D7).** RAG Studio ya modela liberaciones: `ReleaseRecord`, con estado `ReleaseStatus.APROBADA` (`domain/release/entities.py:33-85`). `ProjectSnapshot` ya tiene `source_release_id`, que es opcional (`domain/release/entities.py`, ver `ProjectSnapshot`). Hay que decidir dos cosas:
  - la forma portable del identificador, por ejemplo `urn:nexom:release:<uuid>`, porque el id de `ReleaseRecord` es local;
  - si "firmar solo liberaciones aprobadas" exige que la instantánea exportada tenga `source_release_id` apuntando a una liberación `APROBADA`. Hoy RAG-INC-01 exporta desde cualquier instantánea publicada, así que esa exigencia pertenecería al incremento de firma, no a RAG-INC-01.
- **Solapamiento de rotación (F1-D4) y regla de claves retiradas (corrección 4).** Durante los 30 días de solapamiento, la clave saliente debe seguir en estado `active`. Pasa a `retired` al terminar el solapamiento. Si no, un paquete firmado en ese periodo y presentado por primera vez después se rechazaría como `KEY_RETIRED`.
- **El servicio recibe el ZIP (corrección 7).** Requiere transportar al servicio paquetes que pueden ser grandes. Conviene fijar en la v0.2 un tamaño máximo y qué ocurre si una exportación lo supera.

## 5. Agenda de la sesión conjunta

1. Confirmar que F-1 es un perfil de confianza separado (Trust Profile 1.0) y que NKP sigue en `1.0.0`.
2. Ratificar F1-D1 a F1-D8 con las resoluciones de la sección 2, o documentar las excepciones.
3. Cerrar el formato del sobre y la lista exacta de campos de `statement`, incluidos el hash del ZIP y el identificador de liberación.
4. Definir el payload firmado del almacén de confianza, el ancla raíz de la instalación y la rotación de la raíz.
5. Adoptar la revocación total y la regla estricta para claves retiradas.
6. Definir el registro de procedencia y la política de cuarentena de paquetes instalados.
7. Definir el estado antirretroceso, el reloj y la recuperación mediante un paquete firmado.
8. Asignar responsables y fecha de la v0.2.

## 6. Entregables de la v0.2

- especificación cerrada, sin alternativas abiertas;
- schema del sobre de firma;
- schema del almacén de confianza;
- estado persistente del Runtime;
- máquina de estados de claves y de paquetes instalados;
- catálogo de errores;
- matriz de pruebas positivas y negativas;
- procedimientos de ceremonia, rotación, revocación y recuperación.

La v0.2 se somete a revisión conjunta y se congela antes de implementar. Después se abren incrementos independientes para el servicio de firma y liberación, el verificador del Runtime y la prueba de interoperabilidad de F-1. RAG-INC-01 sigue separado de todo esto.
