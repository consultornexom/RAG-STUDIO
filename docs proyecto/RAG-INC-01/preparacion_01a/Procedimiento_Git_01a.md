# Procedimiento de inicialización de Git para RAG-INC-01

**Estado:** PREPARADO, NO EJECUTADO. NEXOM recomendó inicializar Git antes de 01a (dictamen del 2026-09-24). Para respetar que 01a no ha comenzado, `git init` se ejecuta **después del PASS de humo**, como paso 3 de la secuencia de arranque de `Preparacion_Hito_01a.md`. Antes del PASS solo se dejan preparados este procedimiento y `gitignore_propuesto.txt`.

## 1. Situación actual (verificada 2026-09-24, solo lectura)

- La carpeta de RAG Studio **no es un repositorio Git**: no existe `.git/`.
- Existen `.gitignore`, `.github/workflows` y `.pre-commit-config.yaml`, restos de un repositorio anterior o preparados para uno.
- El `.gitignore` actual tiene la regla `.agentproj`, que solo excluye un archivo con ese nombre literal. La propuesta la corrige a `*.agentproj`.
- Búsqueda de secretos por nombre de archivo, excluyendo `data/`. Solo se encontraron:
  - certificados raíz públicos dentro de `.venv/` (excluido);
  - dos claves **públicas** DEMO en `docs proyecto/` (`*.pubkey_DEMO.pem`), que se conservan con una excepción explícita.

  No aparecieron `.env`, `*.key` ni claves privadas. Esta búsqueda es por nombre, no por contenido; el paso 4 añade una revisión de contenido.

El `.gitignore` propuesto se probó en un repositorio sintético en `/tmp`, nunca en RAG Studio. Ignora `data/`, `.env`, `*.pem`, `*.key`, `*.agentproj` y `*.db-wal`, y deja rastreable la excepción `docs proyecto/**/*.pubkey_DEMO.pem`.

## 2. Puntos que NEXOM debe decidir antes del primer commit

| Punto | Propuesta |
|---|---|
| `Licenciatura/` y `PRUEBAS_RAG_STUDIO_UDL_2026-08-20/` en la raíz | Contienen documentos o paquetes de prueba del cliente. Con `*.agentproj` quedan excluidos los paquetes de PRUEBAS, pero `Licenciatura/` entraría en el commit. Recomendación: excluir ambas carpetas si contienen datos del cliente |
| Bases de benchmark en `docs proyecto/RAG4_Fase-1_Benchmark/prototipo/trabajo/` (`project.db`, `storage.sqlite`) | Quedan excluidas por `*.db` y `*.sqlite`. Si se quieren como evidencia, van en un archivo aparte con hash, no en Git |
| Artefactos binarios de gobierno (`.zip` rc3.2, PDF firmados) | Se incluyen: son pequeños y son evidencia. Se registran tal cual, sin modificarlos |

## 3. Procedimiento (después del PASS de humo)

1. Crear un respaldo fechado del árbol actual, sin `data/` ni `.venv/`, y registrar su SHA-256.
2. Copiar `gitignore_propuesto.txt` a `.gitignore` en la raíz, con los ajustes que NEXOM decida en la sección 2.
3. Ejecutar `git status --ignored` y revisar que `data/`, los modelos, las bases y los secretos aparecen como ignorados.
4. Revisar el contenido de los archivos que entrarían en el commit en busca de credenciales o claves privadas (por ejemplo `BEGIN PRIVATE KEY`, tokens, contraseñas). No debe aparecer ninguna.
5. `git init`, en local y **sin configurar ningún remoto**.
6. Crear el commit de línea base con el árbol actual, **antes de cualquier cambio de 01a**.
7. Crear la etiqueta `rag-inc-01-baseline`.
8. Crear la rama `rag-inc-01/01a`. Todo el trabajo del hito 01a se hace en ella.
9. Registrar en el informe de puerta de 01a el hash del commit de línea base, la etiqueta y la rama.
