# Empaquetado (PyInstaller)

Ítem 7 de la segunda evaluación de madurez post-8-etapas (ver bitácora
en el README principal de la raíz del repo). Punto de partida para un
instalador multiplataforma real -- **no es todavía un instalador
terminado**; ver "Qué falta" más abajo.

## Cómo generar el ejecutable

Desde la raíz del repo, con el entorno normal de desarrollo instalado
más las dependencias de UI:

```bash
pip install -e .
pip install -r requirements.txt   # incluye UI, pyinstaller y lo demás en un solo paso
pyinstaller packaging/ragstudio.spec --noconfirm --clean
```

Produce `dist/RAGStudio/` (modo *onedir*: una carpeta con el ejecutable
y sus bibliotecas, no un solo archivo *onefile* -- arranca más rápido y
es mucho más fácil de depurar si algo falta). El resultado solo sirve
para el sistema operativo donde se corrió `pyinstaller`: **PyInstaller
nunca compila para otro sistema operativo distinto al que lo ejecuta**.
Para tener un ejecutable de Windows hay que correr esto en Windows,
para macOS en macOS.

## Qué se verificó y qué no (léase con honestidad)

Este `.spec` se construyó y se ejecutó parcialmente en el entorno
Linux de construcción de este proyecto:

- La fase de *Analysis* (resolución de imports: PySide6, SQLAlchemy,
  Alembic, `qdrant-client`, las dependencias transitivas de
  `fastembed` -- incluyendo `onnxruntime`, `tokenizers`,
  `huggingface_hub`, `pandas` --, `keyring`, y los submódulos plugin de
  `tiktoken_ext` que hay que declarar a mano porque `tiktoken` los
  descubre en caliente con `pkgutil.iter_modules`) corrió sin ningún
  error ni advertencia durante los primeros ~40 segundos reales,
  procesando decenas de *hooks* estándar de PyInstaller para cada
  dependencia pesada del proyecto.
- **No se completó una compilación real de punta a punta en este
  entorno.** El entorno de construcción de este proyecto ejecuta cada
  comando de shell en un proceso aislado con un límite de ~45
  segundos, y cualquier proceso en segundo plano se pierde entre un
  comando y el siguiente (se confirmó empíricamente: un `pyinstaller`
  lanzado con `setsid`+`disown` ya no existía en la siguiente llamada).
  Una compilación completa de un árbol de dependencias así de pesado
  (PySide6 + onnxruntime + qdrant-client) tarda varios minutos y copia
  cientos de megabytes de bibliotecas compartidas -- no cabe en ese
  límite. Por eso este `.spec` está bien fundamentado (basado en
  gotchas documentados reales de PyInstaller con estas librerías), pero
  **su ejecutable final nunca se generó ni se corrió de verdad, ni
  aquí ni en Windows/macOS.**
- Desde la tercera ronda de madurez post-8-etapas (ver bitácora en el
  README principal, 2026-07-28), el directorio de datos por defecto
  (`app.configuration.default_base_dir`) ya no es una carpeta de perfil
  del sistema operativo: es una subcarpeta `data/` junto al ejecutable
  real (`Path(sys.executable).resolve().parent`, no `sys._MEIPASS`),
  para que `dist/RAGStudio/` quede autocontenida. Esto se cubrió con
  pruebas unitarias simulando `sys.frozen`/`sys.executable` con
  `monkeypatch` (ver `tests/unit/app/test_configuration.py`), pero
  --igual que el resto de este ítem-- falta confirmarlo corriendo el
  ejecutable real: verificar que `dist/RAGStudio/data/` se crea sola en
  el primer arranque, en el mismo lugar que el propio ejecutable.
- Antes de confiar en este `.spec` para distribuir la app, hay que:
  1. Correr `pyinstaller packaging/ragstudio.spec --noconfirm --clean`
     de verdad en cada sistema operativo objetivo.
  2. Abrir el ejecutable resultante y probar el ciclo completo (crear
     proyecto, registrar fuente, extraer, fragmentar, indexar, buscar)
     -- sobre todo confirmar que las migraciones Alembic corren bien
     empaquetadas (`infrastructure.database.migrations` ya se corrigió
     en este mismo ítem para buscar `migrations/` dentro de
     `sys._MEIPASS` cuando la app corre congelada, ver bitácora, pero
     eso nunca se probó contra un ejecutable real, solo con una prueba
     que simula `sys._MEIPASS` con `monkeypatch`).
  3. Confirmar que `fastembed`/`qdrant-client` funcionan empaquetados
     (descargan y cargan el modelo de embeddings igual que sin
     empaquetar).

## Qué falta para un instalador real (fuera de alcance de este ítem)

- **Icono de la aplicación**: no se agregó ninguno (`icon=` en el
  `.spec` sigue vacío). Un `.ico`/`.icns` real es trabajo de diseño,
  no de este ítem.
- **Firma de código**: sin firmar en ningún sistema operativo --
  Windows/macOS van a mostrar advertencias de "editor no verificado" o
  bloquear la ejecución directamente (macOS con Gatekeeper). Firmar
  requiere un certificado real (de pago) que no es parte de este
  ítem.
- **Empaquetado final por sistema operativo** (`.msi`/`.exe` con
  Inno Setup o WiX en Windows, `.dmg` en macOS, `.deb`/`.AppImage` en
  Linux): PyInstaller solo produce la carpeta `dist/RAGStudio/` con el
  ejecutable adentro, no un instalador de doble clic con accesos
  directos, desinstalador, etc. -- cada uno de esos formatos necesita
  una herramienta adicional específica del sistema operativo.
- **Almacén seguro de credenciales validado en los 3 sistemas
  operativos** (ADR-001, sección 15, "Próximos pasos"): `keyring` (ver
  ítem 2 de esta misma evaluación de madurez) se declaró como
  `hiddenimport` con sus backends, pero cuál backend real usa cada
  sistema operativo (Credential Locker en Windows, Keychain en macOS,
  Secret Service en Linux) solo se puede confirmar corriendo el
  ejecutable de verdad en cada uno.
