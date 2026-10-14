"""Runtime de producción (ADR-002, Fase 2:
docs proyecto/RAG_STUDIO_ADR-002_Runtime_Produccion.docx) -- expone el
motor conversacional ya construido en application/ a través de una API
HTTP mínima, en vez de solo al Simulador de la app de escritorio.

Regla de capa (misma que ui/, ADR-001 sección 4): este paquete solo
llama a application/ (a través de RuntimeContext, que construye esos
servicios apuntados a una instantánea publicada). Nunca importa domain
ni infrastructure fuera de RuntimeContext -- las rutas HTTP
(app.py) traducen entre los esquemas de la API (schemas.py) y los
objetos que ya devuelve application/, igual que ui/release/panel.py
traduce ReleaseChecklist/ReleaseRecord a HTML sin reimplementar nada.

No se instala por defecto: requiere el extra `api`
(`pip install -e .[api]`, ver pyproject.toml) porque es un servicio de
ejecución continua con su propio despliegue, no parte de la app de
escritorio."""
