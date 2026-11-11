"""Panel de Diseño conversacional (Etapa 5): intenciones, variables
conversacionales, guardrails, esquemas de canalización y el simulador
que los conecta con el motor RAG de Etapa 4.

Regla de capa: solo llama a application (conversational_service,
metadata_service, document_service, jobs). Nunca importa domain ni
infrastructure directamente (ADR-001, sección 4) -- los vocabularios de
enums (tipos de regla, niveles de riesgo, acciones, medios de
canalización) vienen de application.conversational.options, igual que
FRAGMENTATION_STRATEGY_OPTIONS en la pestaña Ingesta. Los objetos que
devuelve conversational_service (Intent, GuardrailRule...) se leen solo
por sus atributos, sin importarlos -- mismo criterio que
`chunk.chunk_type.value` en ui/ingestion/panel.py.

Como en Ingesta (ver bitácora 2026-07-27, reorganización en
sub-pestañas), esta pestaña nace ya dividida en sub-pestañas por
proceso: Intenciones, Variables, Guardrails, Canalización y Simulador.

Alcance deliberado (ver README, "Limitaciones conocidas"): todos los
catálogos de esta pestaña admiten Crear + Activar/Desactivar + Editar +
listar (parcial en variables -- `code` no es editable, es clave de
otras entidades; completo en el resto, desde el ajuste funcional del
2026-09-03 descrito abajo). Intenciones y guardrails, desde el ajuste
funcional del 2026-09-04, también tienen Eliminar (esquemas de
canalización no -- ver delete_intent.py y delete_guardrail_rule.py
sobre por qué ahí sí es seguro sin ningún chequeo de "en uso").

Ronda 3 (punto 13 de Validacion_observaciones_RAG_STUDIO.md): antes de
esto, intenciones/variables/reglas eran la variante más extrema del
mismo problema ya corregido en Metadatos y Catálogos -- ni siquiera
había edición parcial, solo Activar/Desactivar; un error de escritura
al crear una de estas entidades no tenía ninguna vía de corrección. Se
agregó edición básica (nombre/descripción en intenciones, etiqueta/
descripción en variables, solo nombre en reglas).

Ajuste funcional del 2026-09-03 (hallazgo real de usuario, ver
bitácora): el Manual del Usuario documentaba "eliminar y crear
nuevamente" para cambiar la lógica de una regla de guardrail (tipo,
condiciones, acción, prioridad), pero la interfaz nunca ofreció ningún
botón "Eliminar" -- y el mismo problema, sin ninguna vía documentada
de solución, existía para el resto de la configuración de una
intención (ejemplos, prioridad, riesgo, datos mínimos/opcionales,
preguntas aclaratorias, regla de respuesta, canalización alternativa).
Se agrega edición completa a ambos catálogos (`_EditGuardrailRuleDialog`,
`_EditIntentDialog`, mismo patrón que `_EditChannelingSchemeDialog`) y
Eliminar a guardrails. También se corrige que la Compuerta de
Liberación (Diseño conversacional) no se refrescaba de inmediato tras
crear una intención, crear una regla, o activar/desactivar una regla
(el mismo refresco ya ocurría, de forma asimétrica, al
activar/desactivar una intención) -- ver cada método `_on_*` para el
detalle.

Ajuste funcional del 2026-09-04 (hallazgo real de usuario, ver
bitácora): tras recibir el ajuste anterior, el usuario reportó que
Guardrails "sí permite tanto editar como eliminar y eso ayuda mucho en
la operación" y preguntó si convenía integrar lo mismo para
intenciones. Se agrega "Eliminar intención" (`_on_delete_intent`),
reutilizando el mismo aviso de reglas de guardrail afectadas ya usado
por el renombrado en `_on_edit_intent` (ver `delete_intent.py` sobre
por qué eliminar tiene exactamente la misma consecuencia -- y solo
esa -- que renombrar)."""
from __future__ import annotations

from html import escape as html_escape
from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QTimer

from application.conversational.options import (
    CHANNELING_MEDIUM_OPTIONS, CONDITION_FIELDS, INTENT_RISK_LEVEL_OPTIONS, RESOLUTION_MODE_OPTIONS,
    RULE_ACTION_OPTIONS, RULE_TYPE_OPTIONS,
)

from ui.release.gate_status import GateStatusLabel

from .parsing import (
    condition_syntax_help, describe_condition_problems, format_conditions, format_key_value_lines,
    parse_conditions, parse_csv, parse_key_value_lines, parse_lines, parse_provided_variables,
)
from ui.errors import describe_error

# Ronda 87 (2026-10-02, hallazgo real de usuario: "en la documentación no
# especifica la sintaxis o ejemplos del campo Condición"): textos de
# ayuda compartidos por los formularios de Guardrails y Canalización.
_CONDITIONS_PLACEHOLDER = (
    "Condiciones, una por línea: campo operador valor. Campos: intencion, confianza, nivel_riesgo, "
    "variables_faltantes. Ej.: intencion = Solicitar asesor humano | confianza < 0.45. "
    "Sin condiciones = se aplica a todas las consultas."
)
_SCHEME_CONDITION_PLACEHOLDER = "Condición (texto descriptivo; no se evalúa, ver ayuda)"
_SCHEME_CONDITION_TOOLTIP = (
    "Campo DESCRIPTIVO: documenta en palabras cuándo se usa este esquema (p. ej. \"La persona pide "
    "hablar con un asesor humano\"). RAG STUDIO no lo evalúa y acepta cualquier texto.\n\n"
    "Lo que hace que una consulta se canalice con este esquema son dos cosas:\n"
    "1) una regla de Guardrails activa con Acción si dispara = canalizar cuyas condiciones se cumplan "
    "(p. ej. intencion = Solicitar asesor humano), y\n"
    "2) que la intención reconocida tenga el CÓDIGO de este esquema en \"Canalización alternativa\"."
)
_CHANNELING_HOW_TO = (
    "¿Cuándo se usa un esquema? Cuando (1) una regla de Guardrails activa con acción \"canalizar\" cumple "
    "sus condiciones y (2) la intención reconocida tiene el código de este esquema en \"Canalización "
    "alternativa\". El campo Condición de aquí es solo descriptivo (no se evalúa)."
)


def _validate_conditions_before_save(parent: QWidget, text: str) -> bool:
    """Ronda 87: antes, las líneas mal escritas se descartaban en silencio
    y, si se descartaban todas, la regla quedaba incondicional (se
    disparaba en TODAS las consultas). Ahora una línea inválida impide
    guardar, y un campo desconocido (que nunca se cumplirá) pide
    confirmación. Devuelve True si se puede guardar."""
    errors, warnings = describe_condition_problems(text, CONDITION_FIELDS)
    help_text = condition_syntax_help(CONDITION_FIELDS)
    if errors:
        QMessageBox.warning(
            parent, "Condiciones con formato incorrecto",
            "No se guardó la regla. Estas líneas no se pudieron interpretar:\n- " + "\n- ".join(errors)
            + "\n\n" + help_text,
        )
        return False
    if warnings:
        answer = QMessageBox.question(
            parent, "Campos que el motor no conoce",
            "- " + "\n- ".join(warnings) + "\n\n" + help_text + "\n\n¿Guardar la regla de todos modos?",
            QMessageBox.Yes | QMessageBox.Cancel,
        )
        return answer == QMessageBox.Yes
    return True


class _EditChannelingSchemeDialog(QDialog):
    """Ronda 4 (punto 1): antes Canalización solo tenía Crear +
    Activar/Desactivar -- el único de los cuatro catálogos de
    Conversacional sin edición básica, ver update_channeling_scheme.py.
    `code` no se muestra aquí porque no es editable (lo referencia
    Intent.fallback_channeling_code)."""

    def __init__(self, scheme, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"Editar esquema de canalización ({scheme.code!r})")

        self._name = QLineEdit(scheme.name, self)
        self._reason = QLineEdit(scheme.reason, self)
        self._condition = QLineEdit(scheme.condition, self)
        self._condition.setPlaceholderText(_SCHEME_CONDITION_PLACEHOLDER)
        self._condition.setToolTip(_SCHEME_CONDITION_TOOLTIP)
        self._target_area = QLineEdit(scheme.target_area, self)
        self._priority = QSpinBox(self)
        self._priority.setRange(0, 100)
        self._priority.setValue(scheme.priority)
        self._medium = QComboBox(self)
        self._medium.addItems(CHANNELING_MEDIUM_OPTIONS)
        self._medium.setCurrentText(scheme.medium.value)
        self._required_data = QLineEdit(", ".join(scheme.required_data), self)
        self._allowed_data = QLineEdit(", ".join(scheme.allowed_data), self)
        self._forbidden_data = QLineEdit(", ".join(scheme.forbidden_data), self)
        self._summary = QTextEdit(self)
        self._summary.setPlainText(scheme.summary_template)
        self._user_message = QTextEdit(self)
        self._user_message.setPlainText(scheme.user_message)
        self._alternative_action = QLineEdit(scheme.alternative_action, self)

        form = QFormLayout()
        form.addRow("Nombre:", self._name)
        form.addRow("Motivo:", self._reason)
        form.addRow("Condición (descriptiva):", self._condition)
        form.addRow("Área destino:", self._target_area)
        form.addRow("Prioridad:", self._priority)
        form.addRow("Medio:", self._medium)
        form.addRow("Datos obligatorios:", self._required_data)
        form.addRow("Datos permitidos:", self._allowed_data)
        form.addRow("Datos prohibidos:", self._forbidden_data)
        form.addRow("Resumen (plantilla):", self._summary)
        form.addRow("Mensaje al usuario:", self._user_message)
        form.addRow("Acción alternativa:", self._alternative_action)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "reason": self._reason.text().strip(),
            "condition": self._condition.text().strip(),
            "target_area": self._target_area.text().strip(),
            "priority": self._priority.value(),
            "medium": self._medium.currentText(),
            "required_data": parse_csv(self._required_data.text()),
            "allowed_data": parse_csv(self._allowed_data.text()),
            "forbidden_data": parse_csv(self._forbidden_data.text()),
            "summary_template": self._summary.toPlainText().strip(),
            "user_message": self._user_message.toPlainText().strip(),
            "alternative_action": self._alternative_action.text().strip(),
        }


class _EditGuardrailRuleDialog(QDialog):
    """Ajuste funcional del 2026-09-03 (hallazgo real de usuario, ver
    bitácora): el Manual del Usuario documentaba "eliminar y crear
    nuevamente" para cambiar tipo, condiciones, acción o prioridad de
    una regla -- pero la interfaz solo dejaba editar el nombre y no
    ofrecía ningún "Eliminar", así que esa vía documentada no existía
    en la práctica. Se reemplaza por edición completa (mismo criterio
    que _EditChannelingSchemeDialog); Eliminar se agrega aparte, ver
    _on_delete_rule."""

    def __init__(self, rule, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Editar regla de guardrail")

        self._name = QLineEdit(rule.name, self)
        self._rule_type = QComboBox(self)
        self._rule_type.addItems(RULE_TYPE_OPTIONS)
        self._rule_type.setCurrentText(rule.rule_type.value)
        self._conditions = QTextEdit(self)
        self._conditions.setPlainText(format_conditions(rule.conditions))
        self._conditions.setPlaceholderText(_CONDITIONS_PLACEHOLDER)
        self._conditions.setToolTip(condition_syntax_help(CONDITION_FIELDS))
        self._action = QComboBox(self)
        self._action.addItems(RULE_ACTION_OPTIONS)
        self._action.setCurrentText(rule.action.value)
        self._priority = QSpinBox(self)
        self._priority.setRange(0, 100)
        self._priority.setValue(rule.priority)

        form = QFormLayout()
        form.addRow("Nombre:", self._name)
        form.addRow("Tipo:", self._rule_type)
        form.addRow("Condiciones:", self._conditions)
        form.addRow("Acción si dispara:", self._action)
        form.addRow("Prioridad:", self._priority)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "rule_type": self._rule_type.currentText(),
            "conditions": parse_conditions(self._conditions.toPlainText()),
            "action": self._action.currentText(),
            "priority": self._priority.value(),
        }

    def conditions_text(self) -> str:
        """Texto tal cual lo escribió la persona, para validarlo antes de
        guardar (ver _validate_conditions_before_save)."""
        return self._conditions.toPlainText()


class _EditIntentDialog(QDialog):
    """Ajuste funcional del 2026-09-03 (hallazgo real de usuario, ver
    bitácora): antes de esto, "Editar nombre/descripción…" era una
    cadena de QInputDialog que solo tocaba nombre, descripción y vía de
    resolución -- ejemplos positivos/negativos, prioridad, riesgo,
    datos mínimos/opcionales, preguntas aclaratorias, regla de
    respuesta y canalización alternativa quedaban bloqueados desde la
    interfaz una vez creada la intención, obligando a desactivarla y
    crear otra para cualquier ajuste. Mismos campos y mismos widgets
    que "Nueva intención" (_build_intents_tab), precargados con los
    valores actuales -- mismo criterio que _EditChannelingSchemeDialog.

    El aviso de reglas de guardrail afectadas por un renombrado (ver
    find_rules_referencing_intent) se evalúa aparte, en
    _on_edit_intent, comparando el name devuelto por values() contra el
    nombre original -- no es responsabilidad de este diálogo."""

    def __init__(self, intent, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"Editar intención ({intent.name!r})")

        self._name = QLineEdit(intent.name, self)
        self._description = QLineEdit(intent.description, self)
        self._positive = QTextEdit(self)
        self._positive.setPlainText("\n".join(intent.positive_examples))
        self._positive.setPlaceholderText("Ejemplos positivos (uno por línea)")
        self._negative = QTextEdit(self)
        self._negative.setPlainText("\n".join(intent.negative_examples))
        self._negative.setPlaceholderText("Ejemplos negativos (uno por línea)")
        self._priority = QSpinBox(self)
        self._priority.setRange(0, 100)
        self._priority.setValue(intent.priority)
        self._risk = QComboBox(self)
        self._risk.addItems(INTENT_RISK_LEVEL_OPTIONS)
        self._risk.setCurrentText(intent.risk_level.value)
        self._resolution_mode = QComboBox(self)
        self._resolution_mode.addItems(RESOLUTION_MODE_OPTIONS)
        self._resolution_mode.setCurrentText(intent.resolution_mode.value)
        self._required = QLineEdit(", ".join(intent.required_variables), self)
        self._required.setPlaceholderText("Datos mínimos (códigos separados por coma)")
        self._optional = QLineEdit(", ".join(intent.optional_variables), self)
        self._optional.setPlaceholderText("Datos opcionales (códigos separados por coma)")
        self._questions = QTextEdit(self)
        self._questions.setPlainText(format_key_value_lines(intent.clarifying_questions))
        self._questions.setPlaceholderText(
            "Preguntas aclaratorias, una por línea: código: pregunta (p. ej. plantel: ¿En qué plantel?)"
        )
        self._response_rule = QLineEdit(intent.response_rule, self)
        self._response_rule.setPlaceholderText("Regla de respuesta (descripción libre)")
        self._fallback = QLineEdit(intent.fallback_channeling_code or "", self)
        self._fallback.setPlaceholderText("Canalización alternativa (código de esquema, opcional)")

        form = QFormLayout()
        form.addRow("Nombre:", self._name)
        form.addRow("Descripción:", self._description)
        form.addRow("Ejemplos positivos:", self._positive)
        form.addRow("Ejemplos negativos:", self._negative)
        form.addRow("Prioridad:", self._priority)
        form.addRow("Nivel de riesgo:", self._risk)
        form.addRow("Vía de resolución:", self._resolution_mode)
        form.addRow("Datos mínimos:", self._required)
        form.addRow("Datos opcionales:", self._optional)
        form.addRow("Preguntas aclaratorias:", self._questions)
        form.addRow("Regla de respuesta:", self._response_rule)
        form.addRow("Canalización alternativa:", self._fallback)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "description": self._description.text().strip(),
            "positive_examples": parse_lines(self._positive.toPlainText()),
            "negative_examples": parse_lines(self._negative.toPlainText()),
            "priority": self._priority.value(),
            "risk_level": self._risk.currentText(),
            "resolution_mode": self._resolution_mode.currentText(),
            "required_variables": parse_csv(self._required.text()),
            "optional_variables": parse_csv(self._optional.text()),
            "clarifying_questions": parse_key_value_lines(self._questions.toPlainText()),
            "response_rule": self._response_rule.text().strip(),
            # Cadena vacía a propósito (no `or None` aquí): es
            # UpdateIntent quien decide cómo colapsar "" a "sin
            # canalización alternativa" -- ver su docstring sobre el
            # doble uso de None en este campo puntual.
            "fallback_channeling_code": self._fallback.text().strip(),
        }


class ConversationalPanel(QWidget):
    def __init__(self, app_context, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context = app_context
        self._project_id: Optional[str] = None

        self._intents_cache: list = []
        self._variables_cache: list = []
        self._rules_cache: list = []
        self._schemes_cache: list = []

        self._active_job = None
        self._pending_trace = None

        layout = QVBoxLayout(self)

        # Aviso temprano (no bloqueante) de la compuerta de Liberación
        # "Diseño conversacional" -- ver ui/release/gate_status.py.
        self._gate_status_label = GateStatusLabel("Diseño conversacional", self)
        layout.addWidget(self._gate_status_label)

        self._tabs = QTabWidget(self)
        layout.addWidget(self._tabs)

        self._tabs.addTab(self._build_intents_tab(), "Intenciones")
        self._tabs.addTab(self._build_variables_tab(), "Variables")
        self._tabs.addTab(self._build_guardrails_tab(), "Guardrails")
        self._tabs.addTab(self._build_channeling_tab(), "Canalización")
        self._tabs.addTab(self._build_simulator_tab(), "Simulador")

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(150)
        self._poll_timer.timeout.connect(self._poll_active_job)

        self._apply_button_states()

    # ---------- wiring de proyecto activo ----------
    def set_active_project(self, project_id: str) -> None:
        self._project_id = project_id or None
        self._sim_report.setHtml("")
        self._populate_metadata_fields()
        self._refresh_intents()
        self._refresh_variables()
        self._refresh_rules()
        self._refresh_schemes()
        self._load_agent_reranking()
        self._apply_button_states()
        if self._project_id:
            self._gate_status_label.refresh(self._context.release_service, self._project_id)
        else:
            self._gate_status_label.clear_status()

    def _report_error(self, exc: Exception) -> None:
        QMessageBox.critical(self, "Error", describe_error(exc))

    def _warn_if_unknown_variables(self, codes: list[str]) -> None:
        """Ronda 90 (auditoría con el proyecto real del usuario): los datos
        mínimos/opcionales de una intención se escriben como códigos libres.
        Un código que no existe en la pestaña Variables (p. ej.
        "modalidad" sin haber creado esa variable) se ignoraba en silencio:
        nunca se detecta ni filtra, y si es mínimo el agente lo pide
        siempre. No se bloquea, solo se avisa."""
        if not codes or not self._project_id:
            return
        try:
            existentes = {v.code for v in self._context.conversational_service.list_variables(self._project_id)}
        except Exception:  # noqa: BLE001 - es solo un aviso
            return
        faltantes = sorted({c for c in codes if c not in existentes})
        if faltantes:
            QMessageBox.warning(
                self, "Datos sin variable definida",
                "La intención se guardó, pero estos códigos no existen en la pestaña Variables: "
                f"{', '.join(faltantes)}.\n\nMientras no se creen (con el mismo código), el agente no "
                "puede detectarlos en la consulta ni filtrar por ellos; si son datos mínimos, los "
                "pedirá siempre.",
            )

    def _warn_if_unknown_channeling_code(self, code: str) -> None:
        """Ronda 87: la canalización alternativa de una intención se guarda
        como texto libre. Un código mal escrito no daba ningún aviso y la
        canalización nunca ocurría. No se bloquea (el esquema puede
        crearse después), solo se advierte."""
        if not code or not self._project_id:
            return
        try:
            schemes = self._context.conversational_service.list_channeling_schemes(self._project_id)
        except Exception:  # noqa: BLE001 - es solo un aviso, nunca debe impedir el guardado
            return
        codes = [scheme.code for scheme in schemes]
        if code not in codes:
            disponibles = ", ".join(codes) if codes else "(todavía no hay esquemas)"
            QMessageBox.warning(
                self, "Canalización alternativa sin esquema",
                f"La intención se guardó, pero no existe ningún esquema de canalización con el código "
                f"{code!r}. Mientras no exista, esta intención no podrá canalizarse.\n\n"
                f"Códigos disponibles: {disponibles}\n\n"
                "El código debe escribirse exactamente igual (distingue mayúsculas y minúsculas).",
            )

    def _source_title(self, project_id: str, source_id: str) -> str:
        try:
            return self._context.document_service.get_source(project_id, source_id).title
        except Exception:
            return source_id

    def _apply_button_states(self) -> None:
        ready = self._project_id is not None
        busy = self._active_job is not None
        for widget in (
            self._btn_create_intent, self._btn_toggle_intent, self._intent_list,
            self._intent_name, self._intent_description, self._intent_positive, self._intent_negative,
            self._intent_priority, self._intent_risk, self._intent_required, self._intent_optional,
            self._intent_questions, self._intent_response_rule, self._intent_fallback,
        ):
            widget.setEnabled(ready)
        for widget in (
            self._btn_create_variable, self._variable_list, self._variable_code, self._variable_label,
            self._variable_description, self._variable_metadata_field,
        ):
            widget.setEnabled(ready)
        for widget in (
            self._btn_create_rule, self._btn_toggle_rule, self._rule_list, self._rule_name, self._rule_type,
            self._rule_conditions, self._rule_action, self._rule_priority,
        ):
            widget.setEnabled(ready)
        for widget in (
            self._btn_create_scheme, self._btn_toggle_scheme, self._scheme_list, self._scheme_code,
            self._scheme_name, self._scheme_reason, self._scheme_condition, self._scheme_target_area,
            self._scheme_priority, self._scheme_required_data, self._scheme_allowed_data,
            self._scheme_forbidden_data, self._scheme_summary, self._scheme_medium, self._scheme_user_message,
            self._scheme_alternative_action,
        ):
            widget.setEnabled(ready)
        self._btn_simulate.setEnabled(ready and not busy)
        self._sim_cancel.setEnabled(busy)
        for widget in (self._sim_query, self._sim_variables, self._sim_source_id, self._sim_reranking):
            widget.setEnabled(ready and not busy)

    def refresh_metadata_fields(self) -> None:
        """Wrapper público, conectado a MetadataPanel.schema_changed en
        main_window.py. Auditoría posterior a la Ronda 78 (hallazgo
        real de usuario, ver bitácora): el selector "Campo de
        metadatos ligado (opcional)" de la pestaña Variables solo se
        poblaba una vez, al seleccionar el proyecto activo
        (set_active_project) -- si el esquema de metadatos se creaba o
        se le agregaban campos DESPUÉS, en la misma sesión, este
        selector se quedaba mostrando solo "— ninguno —" hasta salir y
        volver a entrar al proyecto. Mismo patrón ya corregido para
        sources_changed -> refresh_document_type_options /
        refresh_value_source_selector (Ronda 4, punto 4b)."""
        self._populate_metadata_fields()

    def _populate_metadata_fields(self) -> None:
        """Llena el selector de campo de metadatos de la pestaña
        Variables -- puente documentado "Dato conversacional → Campo
        de metadatos → Filtro de recuperación". Si el proyecto todavía
        no tiene esquema activo (Etapa 2 sin configurar), el selector
        se queda solo con "— ninguno —", sin error visible: una
        variable conversacional puede existir sin estar ligada a un
        campo de metadatos."""
        self._variable_metadata_field.clear()
        self._variable_metadata_field.addItem("— ninguno —", None)
        if not self._project_id:
            return
        try:
            _schema, fields = self._context.metadata_service.get_schema(self._project_id)
        except Exception:
            return
        for field in fields:
            self._variable_metadata_field.addItem(f"{field.display_name} ({field.field_id})", field.field_id)

    # ================= Intenciones =================
    def _build_intents_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        form = QGroupBox("Nueva intención", tab)
        form_layout = QVBoxLayout(form)

        self._intent_name = QLineEdit(form)
        self._intent_description = QLineEdit(form)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Nombre:", form))
        row1.addWidget(self._intent_name)
        row1.addWidget(QLabel("Descripción:", form))
        row1.addWidget(self._intent_description)
        form_layout.addLayout(row1)

        self._intent_positive = QTextEdit(form)
        self._intent_positive.setPlaceholderText("Ejemplos positivos (uno por línea)")
        self._intent_negative = QTextEdit(form)
        self._intent_negative.setPlaceholderText("Ejemplos negativos (uno por línea)")
        row2 = QHBoxLayout()
        row2.addWidget(self._intent_positive)
        row2.addWidget(self._intent_negative)
        form_layout.addLayout(row2)

        self._intent_priority = QSpinBox(form)
        self._intent_priority.setRange(0, 100)
        self._intent_risk = QComboBox(form)
        self._intent_risk.addItems(INTENT_RISK_LEVEL_OPTIONS)
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Prioridad:", form))
        row3.addWidget(self._intent_priority)
        row3.addWidget(QLabel("Nivel de riesgo:", form))
        row3.addWidget(self._intent_risk)
        form_layout.addLayout(row3)

        # Pista B.4 del ADR-003 (enrutamiento multi-índice determinista):
        # de qué vía se resuelve esta intención cuando responde --
        # semántica (vector+BM25, de siempre) o estructurada (filtros
        # sobre un bloque XLSX/CSV, ver domain.rag.structured_query).
        # Default "semantico" -- ninguna intención existente cambia de
        # comportamiento hasta que alguien la reclasifique a mano.
        self._intent_resolution_mode = QComboBox(form)
        self._intent_resolution_mode.addItems(RESOLUTION_MODE_OPTIONS)
        row3b = QHBoxLayout()
        row3b.addWidget(QLabel("Vía de resolución:", form))
        row3b.addWidget(self._intent_resolution_mode)
        form_layout.addLayout(row3b)

        self._intent_required = QLineEdit(form)
        self._intent_required.setPlaceholderText("Datos mínimos (códigos separados por coma)")
        self._intent_optional = QLineEdit(form)
        self._intent_optional.setPlaceholderText("Datos opcionales (códigos separados por coma)")
        row4 = QHBoxLayout()
        row4.addWidget(self._intent_required)
        row4.addWidget(self._intent_optional)
        form_layout.addLayout(row4)

        self._intent_questions = QTextEdit(form)
        self._intent_questions.setPlaceholderText(
            "Preguntas aclaratorias, una por línea: código: pregunta (p. ej. plantel: ¿En qué plantel?)"
        )
        form_layout.addWidget(self._intent_questions)

        self._intent_response_rule = QLineEdit(form)
        self._intent_response_rule.setPlaceholderText("Regla de respuesta (descripción libre)")
        self._intent_fallback = QLineEdit(form)
        self._intent_fallback.setPlaceholderText("Canalización alternativa (código de esquema, opcional)")
        row5 = QHBoxLayout()
        row5.addWidget(self._intent_response_rule)
        row5.addWidget(self._intent_fallback)
        form_layout.addLayout(row5)

        self._btn_create_intent = QPushButton("Crear intención", form)
        self._btn_create_intent.clicked.connect(self._on_create_intent)
        form_layout.addWidget(self._btn_create_intent)
        layout.addWidget(form)

        list_row = QHBoxLayout()
        self._btn_toggle_intent = QPushButton("Activar/Desactivar seleccionada", tab)
        self._btn_toggle_intent.clicked.connect(self._on_toggle_intent)
        list_row.addWidget(self._btn_toggle_intent)
        self._btn_edit_intent = QPushButton("Editar intención…", tab)
        self._btn_edit_intent.clicked.connect(self._on_edit_intent)
        list_row.addWidget(self._btn_edit_intent)
        # Ajuste funcional del 2026-09-04 (hallazgo real de usuario, ver
        # bitácora): "en Guardrails sí permite tanto editar como
        # eliminar y eso ayuda mucho en la operación" -- se agrega el
        # mismo par de acciones aquí, reutilizando el aviso ya existente
        # de reglas de guardrail afectadas (ver _on_delete_intent).
        self._btn_delete_intent = QPushButton("Eliminar intención", tab)
        self._btn_delete_intent.clicked.connect(self._on_delete_intent)
        list_row.addWidget(self._btn_delete_intent)
        layout.addLayout(list_row)
        self._intent_list = QListWidget(tab)
        layout.addWidget(self._intent_list)
        return tab

    def _refresh_intents(self) -> None:
        self._intent_list.clear()
        self._intents_cache = []
        if not self._project_id:
            return
        self._intents_cache = self._context.conversational_service.list_intents(self._project_id)
        for intent in self._intents_cache:
            estado = "activa" if intent.active else "inactiva"
            via = " — vía: estructurada" if intent.resolution_mode.value == "estructurado" else ""
            self._intent_list.addItem(
                f"[{estado}] {intent.name} — riesgo: {intent.risk_level.value} — "
                f"prioridad: {intent.priority}{via}"
            )

    def _on_create_intent(self) -> None:
        if not self._project_id:
            return
        name = self._intent_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Falta el nombre", "La intención necesita un nombre.")
            return
        fallback_code = self._intent_fallback.text().strip()
        variable_codes = parse_csv(self._intent_required.text()) + parse_csv(self._intent_optional.text())
        try:
            self._context.conversational_service.create_intent(
                self._project_id, name,
                description=self._intent_description.text().strip(),
                positive_examples=parse_lines(self._intent_positive.toPlainText()),
                negative_examples=parse_lines(self._intent_negative.toPlainText()),
                priority=self._intent_priority.value(),
                risk_level=self._intent_risk.currentText(),
                required_variables=parse_csv(self._intent_required.text()),
                optional_variables=parse_csv(self._intent_optional.text()),
                clarifying_questions=parse_key_value_lines(self._intent_questions.toPlainText()),
                response_rule=self._intent_response_rule.text().strip(),
                fallback_channeling_code=self._intent_fallback.text().strip() or None,
                resolution_mode=self._intent_resolution_mode.currentText(),
            )
        except Exception as exc:  # noqa: BLE001 - incluye parámetros incoherentes
            self._report_error(exc)
            return
        for field in (
            self._intent_name, self._intent_description, self._intent_required, self._intent_optional,
            self._intent_response_rule, self._intent_fallback,
        ):
            field.clear()
        self._intent_positive.clear()
        self._intent_negative.clear()
        self._intent_questions.clear()
        self._intent_priority.setValue(0)
        self._intent_risk.setCurrentIndex(0)
        self._intent_resolution_mode.setCurrentIndex(0)
        self._refresh_intents()
        self._warn_if_unknown_channeling_code(fallback_code)
        self._warn_if_unknown_variables(variable_codes)
        # Ajuste funcional del 2026-09-03 (hallazgo real de usuario, ver
        # bitácora): una intención nueva siempre nace activa
        # (Intent.active por defecto), así que puede ser justo la que
        # completa el mínimo de la compuerta -- antes esto no se
        # reflejaba hasta reiniciar la aplicación.
        self._gate_status_label.refresh(self._context.release_service, self._project_id)

    def _on_toggle_intent(self) -> None:
        row = self._intent_list.currentRow()
        if row < 0 or row >= len(self._intents_cache) or not self._project_id:
            return
        intent = self._intents_cache[row]
        try:
            self._context.conversational_service.set_intent_active(self._project_id, intent.id, not intent.active)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._refresh_intents()
        self._gate_status_label.refresh(self._context.release_service, self._project_id)

    def _on_edit_intent(self) -> None:
        # Ronda 3 (punto 13): edición básica (nombre/descripción/vía de
        # resolución). Ampliado en el ajuste funcional del 2026-09-03
        # (hallazgo real de usuario, ver bitácora) a la ficha completa
        # -- ver _EditIntentDialog. El resto del identificador (id) y
        # el estado activo/inactivo nunca se tocan aquí: la intención
        # conserva su identificador e historial, y su estado
        # activo/inactivo se maneja aparte con "Activar/Desactivar
        # seleccionada" (_on_toggle_intent).
        row = self._intent_list.currentRow()
        if row < 0 or row >= len(self._intents_cache) or not self._project_id:
            return
        intent = self._intents_cache[row]
        dialog = _EditIntentDialog(intent, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        if not values["name"]:
            QMessageBox.warning(self, "Falta el nombre", "La intención necesita un nombre.")
            return
        # Ronda 4 (re-análisis de la mejora anterior): una regla de
        # guardrail puede tener una condición de texto libre como
        # "intencion = <nombre>" (ver simulate_conversation.py) -- si se
        # renombra la intención, esa condición deja de cumplirse en
        # silencio, sin ningún error. Se avisa antes de confirmar
        # (no se bloquea: el renombrado sigue siendo válido, solo hay
        # que revisar esas reglas a mano). Sigue siendo el único campo
        # de esta edición completa que necesita este aviso -- ver
        # docstring de _EditIntentDialog y el hallazgo del subagente de
        # investigación: ningún otro campo de Intent se referencia por
        # valor desde otra entidad de este dominio.
        if values["name"] != intent.name:
            affected = self._context.conversational_service.find_rules_referencing_intent(
                self._project_id, intent.name,
            )
            if affected:
                nombres = ", ".join(r.name for r in affected)
                proceed = QMessageBox.warning(
                    self, "Reglas de guardrail afectadas",
                    f"Las siguientes reglas de guardrail tienen una condición que compara con el nombre "
                    f"actual de esta intención ({intent.name!r}) y dejarán de cumplirse si la renombras: "
                    f"{nombres}. Revísalas y actualiza esa condición manualmente después de renombrar.\n\n"
                    "¿Continuar con el renombrado de todos modos?",
                    QMessageBox.Yes | QMessageBox.Cancel,
                )
                if proceed != QMessageBox.Yes:
                    return
        try:
            self._context.conversational_service.update_intent(self._project_id, intent.id, **values)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._refresh_intents()
        self._warn_if_unknown_channeling_code(values.get("fallback_channeling_code") or "")
        self._warn_if_unknown_variables(
            list(values.get("required_variables") or []) + list(values.get("optional_variables") or [])
        )
        self._gate_status_label.refresh(self._context.release_service, self._project_id)

    def _on_delete_intent(self) -> None:
        # Ajuste funcional del 2026-09-04 (hallazgo real de usuario, ver
        # bitácora): "en Guardrails sí permite tanto editar como
        # eliminar y eso ayuda mucho en la operación... valide si en
        # esta sección [Intenciones] es conveniente integrar la
        # funcionalidad de Eliminar intención". Ver
        # domain.conversational.ports.IntentRepository.delete sobre por
        # qué no hace falta ningún chequeo de "en uso".
        row = self._intent_list.currentRow()
        if row < 0 or row >= len(self._intents_cache) or not self._project_id:
            return
        intent = self._intents_cache[row]
        # Mismo aviso ya usado al renombrar (Ronda 4): eliminar una
        # intención tiene la misma consecuencia -- y solo esa -- que
        # renombrarla: una condición de guardrail "intencion = <nombre>"
        # deja de cumplirse en silencio. Se avisa antes de confirmar, no
        # se bloquea (la eliminación sigue siendo válida).
        affected = self._context.conversational_service.find_rules_referencing_intent(
            self._project_id, intent.name,
        )
        if affected:
            nombres = ", ".join(r.name for r in affected)
            proceed = QMessageBox.warning(
                self, "Reglas de guardrail afectadas",
                f"Las siguientes reglas de guardrail tienen una condición que compara con el nombre "
                f"de esta intención ({intent.name!r}) y dejarán de cumplirse si la eliminas: "
                f"{nombres}. Revísalas y actualiza esa condición manualmente después de eliminarla.\n\n"
                "¿Continuar con la eliminación de todos modos?",
                QMessageBox.Yes | QMessageBox.Cancel,
            )
            if proceed != QMessageBox.Yes:
                return
        confirm = QMessageBox.question(
            self, "Eliminar intención",
            f"¿Eliminar la intención {intent.name!r}? Esta acción no se puede deshacer.",
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self._context.conversational_service.delete_intent(self._project_id, intent.id)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._refresh_intents()
        # Eliminar la última intención activa (o la única, sea cual sea
        # su estado) sí puede tumbar el mínimo de la compuerta -- mismo
        # criterio ya aplicado a _on_delete_rule.
        self._gate_status_label.refresh(self._context.release_service, self._project_id)

    # ================= Variables conversacionales =================
    def _build_variables_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        form = QGroupBox("Nueva variable conversacional", tab)
        form_layout = QVBoxLayout(form)

        self._variable_code = QLineEdit(form)
        self._variable_label = QLineEdit(form)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Código:", form))
        row1.addWidget(self._variable_code)
        row1.addWidget(QLabel("Etiqueta:", form))
        row1.addWidget(self._variable_label)
        form_layout.addLayout(row1)

        self._variable_description = QLineEdit(form)
        self._variable_description.setPlaceholderText("Descripción (opcional)")
        form_layout.addWidget(self._variable_description)

        self._variable_metadata_field = QComboBox(form)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Campo de metadatos ligado (opcional):", form))
        row2.addWidget(self._variable_metadata_field)
        form_layout.addLayout(row2)

        # Pista B.4 del ADR-003: puente análogo al de arriba, pero hacia
        # una columna de un bloque de datos estructurados (XLSX/CSV, ver
        # domain.rag.structured_query) en vez de un campo de metadatos --
        # texto libre porque las columnas estructuradas no tienen
        # catálogo/registro propio (a diferencia de los campos de
        # metadatos, que sí).
        self._variable_structured_column = QLineEdit(form)
        self._variable_structured_column.setPlaceholderText(
            "Columna de datos estructurados ligada (opcional, p. ej. 'plantel')"
        )
        row2b = QHBoxLayout()
        row2b.addWidget(QLabel("Columna estructurada ligada (opcional):", form))
        row2b.addWidget(self._variable_structured_column)
        form_layout.addLayout(row2b)

        self._btn_create_variable = QPushButton("Crear variable", form)
        self._btn_create_variable.clicked.connect(self._on_create_variable)
        form_layout.addWidget(self._btn_create_variable)
        layout.addWidget(form)

        variable_buttons = QHBoxLayout()
        self._btn_edit_variable = QPushButton("Editar etiqueta/descripción…", tab)
        self._btn_edit_variable.clicked.connect(self._on_edit_variable)
        variable_buttons.addWidget(self._btn_edit_variable)
        layout.addLayout(variable_buttons)

        self._variable_list = QListWidget(tab)
        layout.addWidget(self._variable_list)
        return tab

    def _refresh_variables(self) -> None:
        self._variable_list.clear()
        self._variables_cache = []
        if not self._project_id:
            return
        self._variables_cache = self._context.conversational_service.list_variables(self._project_id)
        for variable in self._variables_cache:
            campo = f" — campo de metadatos: {variable.metadata_field_id}" if variable.metadata_field_id else ""
            columna = (
                f" — columna estructurada: {variable.structured_column}"
                if variable.structured_column else ""
            )
            self._variable_list.addItem(f"{variable.code} ({variable.label}){campo}{columna}")

    def _on_create_variable(self) -> None:
        if not self._project_id:
            return
        code = self._variable_code.text().strip()
        label = self._variable_label.text().strip()
        if not code or not label:
            QMessageBox.warning(self, "Faltan datos", "La variable necesita código y etiqueta.")
            return
        try:
            self._context.conversational_service.create_variable(
                self._project_id, code, label,
                description=self._variable_description.text().strip(),
                metadata_field_id=self._variable_metadata_field.currentData(),
                structured_column=self._variable_structured_column.text().strip() or None,
            )
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._variable_code.clear()
        self._variable_label.clear()
        self._variable_description.clear()
        self._variable_metadata_field.setCurrentIndex(0)
        self._variable_structured_column.clear()
        self._refresh_variables()

    def _on_edit_variable(self) -> None:
        # Ronda 3 (punto 13): mismo motivo que _on_edit_intent. El
        # código (`code`) no es editable aquí -- ver
        # UpdateConversationalVariable.
        row = self._variable_list.currentRow()
        if row < 0 or row >= len(self._variables_cache) or not self._project_id:
            return
        variable = self._variables_cache[row]
        label, ok = QInputDialog.getText(self, "Editar variable", "Etiqueta:", text=variable.label)
        if not ok or not label.strip():
            return
        description, ok = QInputDialog.getText(
            self, "Editar variable", "Descripción:", text=variable.description,
        )
        if not ok:
            return
        try:
            self._context.conversational_service.update_variable(
                self._project_id, variable.id, label.strip(), description=description.strip(),
            )
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._refresh_variables()

    # ================= Guardrails =================
    def _build_guardrails_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        form = QGroupBox("Nueva regla de guardrail", tab)
        form_layout = QVBoxLayout(form)

        self._rule_name = QLineEdit(form)
        self._rule_type = QComboBox(form)
        self._rule_type.addItems(RULE_TYPE_OPTIONS)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Nombre:", form))
        row1.addWidget(self._rule_name)
        row1.addWidget(QLabel("Tipo:", form))
        row1.addWidget(self._rule_type)
        form_layout.addLayout(row1)

        self._rule_conditions = QTextEdit(form)
        self._rule_conditions.setPlaceholderText(_CONDITIONS_PLACEHOLDER)
        self._rule_conditions.setToolTip(condition_syntax_help(CONDITION_FIELDS))
        form_layout.addWidget(self._rule_conditions)

        self._rule_action = QComboBox(form)
        self._rule_action.addItems(RULE_ACTION_OPTIONS)
        self._rule_priority = QSpinBox(form)
        self._rule_priority.setRange(0, 100)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Acción si dispara:", form))
        row2.addWidget(self._rule_action)
        row2.addWidget(QLabel("Prioridad:", form))
        row2.addWidget(self._rule_priority)
        form_layout.addLayout(row2)

        self._btn_create_rule = QPushButton("Crear regla", form)
        self._btn_create_rule.clicked.connect(self._on_create_rule)
        form_layout.addWidget(self._btn_create_rule)
        layout.addWidget(form)

        list_row = QHBoxLayout()
        self._btn_toggle_rule = QPushButton("Activar/Desactivar seleccionada", tab)
        self._btn_toggle_rule.clicked.connect(self._on_toggle_rule)
        list_row.addWidget(self._btn_toggle_rule)
        self._btn_edit_rule = QPushButton("Editar regla…", tab)
        self._btn_edit_rule.clicked.connect(self._on_edit_rule)
        list_row.addWidget(self._btn_edit_rule)
        # Ajuste funcional del 2026-09-03 (hallazgo real de usuario, ver
        # bitácora): el Manual del Usuario documentaba "eliminar y crear
        # nuevamente" como la vía para cambiar tipo, condiciones, acción
        # o prioridad, pero este botón nunca existió -- el usuario
        # reportó tener que desactivar la regla como solución temporal
        # porque no encontraba ninguna forma de eliminarla. Ahora que
        # "Editar regla…" cubre la ficha completa (ver
        # _EditGuardrailRuleDialog), Eliminar deja de ser la única
        # salida para una regla mal configurada, pero se agrega de
        # todos modos porque el manual siempre la documentó como
        # disponible.
        self._btn_delete_rule = QPushButton("Eliminar regla", tab)
        self._btn_delete_rule.clicked.connect(self._on_delete_rule)
        list_row.addWidget(self._btn_delete_rule)
        layout.addLayout(list_row)
        self._rule_list = QListWidget(tab)
        layout.addWidget(self._rule_list)
        return tab

    def _refresh_rules(self) -> None:
        self._rule_list.clear()
        self._rules_cache = []
        if not self._project_id:
            return
        self._rules_cache = self._context.conversational_service.list_guardrail_rules(self._project_id)
        for rule in self._rules_cache:
            estado = "activa" if rule.active else "inactiva"
            # Ronda 87: se muestran las condiciones tal como se evaluarán
            # (ya normalizadas), no solo cuántas son.
            condiciones = (
                "si " + " Y ".join(format_conditions([c]) for c in rule.conditions)
                if rule.conditions else "incondicional (todas las consultas)"
            )
            self._rule_list.addItem(
                f"[{estado}] {rule.name} — tipo: {rule.rule_type.value} — acción: {rule.action.value} "
                f"— {condiciones} — prioridad: {rule.priority}"
            )

    def _on_create_rule(self) -> None:
        if not self._project_id:
            return
        name = self._rule_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Falta el nombre", "La regla necesita un nombre.")
            return
        if not _validate_conditions_before_save(self, self._rule_conditions.toPlainText()):
            return
        try:
            self._context.conversational_service.create_guardrail_rule(
                self._project_id, name, self._rule_type.currentText(),
                conditions=parse_conditions(self._rule_conditions.toPlainText()),
                action=self._rule_action.currentText(), priority=self._rule_priority.value(),
            )
        except Exception as exc:  # noqa: BLE001 - incluye condiciones mal escritas
            self._report_error(exc)
            return
        self._rule_name.clear()
        self._rule_conditions.clear()
        self._rule_priority.setValue(0)
        self._refresh_rules()
        # Ajuste funcional del 2026-09-03 (hallazgo real de usuario, ver
        # bitácora): una regla nueva siempre nace activa
        # (GuardrailRule.active por defecto), así que puede ser justo
        # la que completa el mínimo de la compuerta.
        self._gate_status_label.refresh(self._context.release_service, self._project_id)

    def _on_toggle_rule(self) -> None:
        row = self._rule_list.currentRow()
        if row < 0 or row >= len(self._rules_cache) or not self._project_id:
            return
        rule = self._rules_cache[row]
        try:
            self._context.conversational_service.set_guardrail_rule_active(
                self._project_id, rule.id, not rule.active
            )
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._refresh_rules()
        # Ajuste funcional del 2026-09-03 (hallazgo real de usuario, ver
        # bitácora): este era el hallazgo reportado -- activar/desactivar
        # una intención SÍ refrescaba la compuerta (_on_toggle_intent),
        # pero el mismo cambio en un guardrail no, dejando el mensaje
        # superior desactualizado hasta reiniciar la aplicación.
        self._gate_status_label.refresh(self._context.release_service, self._project_id)

    def _on_edit_rule(self) -> None:
        # Ronda 3 (punto 13): solo el nombre. Ampliado en el ajuste
        # funcional del 2026-09-03 (hallazgo real de usuario, ver
        # bitácora) a la ficha completa -- ver _EditGuardrailRuleDialog.
        # El estado activo/inactivo nunca se toca aquí -- se maneja
        # aparte con "Activar/Desactivar seleccionada".
        row = self._rule_list.currentRow()
        if row < 0 or row >= len(self._rules_cache) or not self._project_id:
            return
        rule = self._rules_cache[row]
        dialog = _EditGuardrailRuleDialog(rule, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        if not values["name"]:
            QMessageBox.warning(self, "Falta el nombre", "La regla necesita un nombre.")
            return
        if not _validate_conditions_before_save(self, dialog.conditions_text()):
            return
        try:
            self._context.conversational_service.update_guardrail_rule(self._project_id, rule.id, **values)
        except Exception as exc:  # noqa: BLE001 - incluye condiciones mal escritas
            self._report_error(exc)
            return
        self._refresh_rules()
        self._gate_status_label.refresh(self._context.release_service, self._project_id)

    def _on_delete_rule(self) -> None:
        # Ajuste funcional del 2026-09-03 (hallazgo real de usuario, ver
        # bitácora): "para que lo considere, de igual manera lo resolví
        # temporalmente desactivando la regla pero el manual indica que
        # se puede eliminar y crear nuevamente pero la interfaz no
        # tiene la opción para elimina[r]." Ver
        # domain.conversational.ports.GuardrailRuleRepository.delete
        # sobre por qué no hace falta ningún chequeo de "en uso" aquí.
        row = self._rule_list.currentRow()
        if row < 0 or row >= len(self._rules_cache) or not self._project_id:
            return
        rule = self._rules_cache[row]
        confirm = QMessageBox.question(
            self, "Eliminar regla", f"¿Eliminar la regla de guardrail {rule.name!r}? Esta acción no se puede deshacer.",
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self._context.conversational_service.delete_guardrail_rule(self._project_id, rule.id)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._refresh_rules()
        # Eliminar la última regla activa (o la única, sea cual sea su
        # estado) sí puede tumbar el mínimo de la compuerta -- a
        # diferencia de editar nombre/lógica, aquí el refresco no es
        # opcional.
        self._gate_status_label.refresh(self._context.release_service, self._project_id)

    # ================= Canalización =================
    def _build_channeling_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        how_to = QLabel(_CHANNELING_HOW_TO, tab)
        how_to.setWordWrap(True)
        layout.addWidget(how_to)

        form = QGroupBox("Nuevo esquema de canalización", tab)
        form_layout = QVBoxLayout(form)

        self._scheme_code = QLineEdit(form)
        self._scheme_name = QLineEdit(form)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Código:", form))
        row1.addWidget(self._scheme_code)
        row1.addWidget(QLabel("Nombre:", form))
        row1.addWidget(self._scheme_name)
        form_layout.addLayout(row1)

        self._scheme_reason = QLineEdit(form)
        self._scheme_reason.setPlaceholderText("Motivo")
        self._scheme_condition = QLineEdit(form)
        self._scheme_condition.setPlaceholderText(_SCHEME_CONDITION_PLACEHOLDER)
        self._scheme_condition.setToolTip(_SCHEME_CONDITION_TOOLTIP)
        row2 = QHBoxLayout()
        row2.addWidget(self._scheme_reason)
        row2.addWidget(self._scheme_condition)
        form_layout.addLayout(row2)

        self._scheme_target_area = QLineEdit(form)
        self._scheme_target_area.setPlaceholderText("Área destino")
        self._scheme_priority = QSpinBox(form)
        self._scheme_priority.setRange(0, 100)
        self._scheme_medium = QComboBox(form)
        self._scheme_medium.addItems(CHANNELING_MEDIUM_OPTIONS)
        row3 = QHBoxLayout()
        row3.addWidget(self._scheme_target_area)
        row3.addWidget(QLabel("Prioridad:", form))
        row3.addWidget(self._scheme_priority)
        row3.addWidget(QLabel("Medio:", form))
        row3.addWidget(self._scheme_medium)
        form_layout.addLayout(row3)

        self._scheme_required_data = QLineEdit(form)
        self._scheme_required_data.setPlaceholderText("Datos obligatorios (separados por coma)")
        self._scheme_allowed_data = QLineEdit(form)
        self._scheme_allowed_data.setPlaceholderText("Datos permitidos (separados por coma)")
        self._scheme_forbidden_data = QLineEdit(form)
        self._scheme_forbidden_data.setPlaceholderText("Datos prohibidos (separados por coma)")
        row4 = QHBoxLayout()
        row4.addWidget(self._scheme_required_data)
        row4.addWidget(self._scheme_allowed_data)
        row4.addWidget(self._scheme_forbidden_data)
        form_layout.addLayout(row4)

        self._scheme_summary = QTextEdit(form)
        self._scheme_summary.setPlaceholderText("Resumen (plantilla)")
        self._scheme_user_message = QTextEdit(form)
        self._scheme_user_message.setPlaceholderText("Mensaje al usuario")
        row5 = QHBoxLayout()
        row5.addWidget(self._scheme_summary)
        row5.addWidget(self._scheme_user_message)
        form_layout.addLayout(row5)

        self._scheme_alternative_action = QLineEdit(form)
        self._scheme_alternative_action.setPlaceholderText("Acción alternativa")
        form_layout.addWidget(self._scheme_alternative_action)

        self._btn_create_scheme = QPushButton("Crear esquema", form)
        self._btn_create_scheme.clicked.connect(self._on_create_scheme)
        form_layout.addWidget(self._btn_create_scheme)
        layout.addWidget(form)

        list_row = QHBoxLayout()
        self._btn_toggle_scheme = QPushButton("Activar/Desactivar seleccionado", tab)
        self._btn_toggle_scheme.clicked.connect(self._on_toggle_scheme)
        list_row.addWidget(self._btn_toggle_scheme)
        self._btn_edit_scheme = QPushButton("Editar…", tab)
        self._btn_edit_scheme.clicked.connect(self._on_edit_scheme)
        list_row.addWidget(self._btn_edit_scheme)
        layout.addLayout(list_row)
        self._scheme_list = QListWidget(tab)
        layout.addWidget(self._scheme_list)
        return tab

    def _refresh_schemes(self) -> None:
        self._scheme_list.clear()
        self._schemes_cache = []
        if not self._project_id:
            return
        self._schemes_cache = self._context.conversational_service.list_channeling_schemes(self._project_id)
        for scheme in self._schemes_cache:
            estado = "activo" if scheme.active else "inactivo"
            self._scheme_list.addItem(
                f"[{estado}] {scheme.code} — {scheme.name} — medio: {scheme.medium.value} "
                f"— área destino: {scheme.target_area or '(sin definir)'}"
            )

    def _on_create_scheme(self) -> None:
        if not self._project_id:
            return
        code = self._scheme_code.text().strip()
        name = self._scheme_name.text().strip()
        if not code or not name:
            QMessageBox.warning(self, "Faltan datos", "El esquema necesita código y nombre.")
            return
        try:
            self._context.conversational_service.create_channeling_scheme(
                self._project_id, code, name,
                reason=self._scheme_reason.text().strip(), condition=self._scheme_condition.text().strip(),
                target_area=self._scheme_target_area.text().strip(), priority=self._scheme_priority.value(),
                required_data=parse_csv(self._scheme_required_data.text()),
                allowed_data=parse_csv(self._scheme_allowed_data.text()),
                forbidden_data=parse_csv(self._scheme_forbidden_data.text()),
                summary_template=self._scheme_summary.toPlainText().strip(),
                medium=self._scheme_medium.currentText(),
                user_message=self._scheme_user_message.toPlainText().strip(),
                alternative_action=self._scheme_alternative_action.text().strip(),
            )
        except Exception as exc:  # noqa: BLE001 - incluye código duplicado
            self._report_error(exc)
            return
        for field in (
            self._scheme_code, self._scheme_name, self._scheme_reason, self._scheme_condition,
            self._scheme_target_area, self._scheme_required_data, self._scheme_allowed_data,
            self._scheme_forbidden_data, self._scheme_alternative_action,
        ):
            field.clear()
        self._scheme_summary.clear()
        self._scheme_user_message.clear()
        self._scheme_priority.setValue(0)
        self._refresh_schemes()

    def _on_toggle_scheme(self) -> None:
        row = self._scheme_list.currentRow()
        if row < 0 or row >= len(self._schemes_cache) or not self._project_id:
            return
        scheme = self._schemes_cache[row]
        try:
            self._context.conversational_service.set_channeling_scheme_active(
                self._project_id, scheme.id, not scheme.active
            )
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._refresh_schemes()

    def _on_edit_scheme(self) -> None:
        row = self._scheme_list.currentRow()
        if row < 0 or row >= len(self._schemes_cache) or not self._project_id:
            return
        scheme = self._schemes_cache[row]
        dialog = _EditChannelingSchemeDialog(scheme, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        if not values["name"]:
            QMessageBox.warning(self, "Falta el nombre", "El esquema necesita un nombre.")
            return
        try:
            self._context.conversational_service.update_channeling_scheme(
                self._project_id, scheme.id, **values,
            )
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)
            return
        self._refresh_schemes()

    # ================= Simulador =================
    def _build_simulator_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        form = QGroupBox("Simular una consulta", tab)
        form_layout = QVBoxLayout(form)

        self._sim_query = QLineEdit(form)
        self._sim_query.setPlaceholderText("Consulta (lo que escribiría la persona usuaria)")
        form_layout.addWidget(self._sim_query)

        self._sim_variables = QLineEdit(form)
        self._sim_variables.setPlaceholderText(
            "Variables ya proporcionadas (opcional): codigo=valor, codigo2=valor2"
        )
        form_layout.addWidget(self._sim_variables)

        self._sim_source_id = QLineEdit(form)
        self._sim_source_id.setPlaceholderText("Restringir a una fuente (opcional, ID de fuente)")
        form_layout.addWidget(self._sim_source_id)

        # Ronda 102 (C4, autorizado por NEXOM): el Simulador y el canal de
        # mensajes aplicaban siempre el reranking si había modelo, aunque
        # en Búsqueda RAG se desactivara. Ajuste propio del proyecto; el
        # predeterminado conserva el comportamiento anterior.
        rerank_row = QHBoxLayout()
        rerank_row.addWidget(QLabel("Reranking en el agente:", form))
        self._sim_reranking = QComboBox(form)
        for etiqueta, valor in (
            ("Automático (predeterminado): si hay modelo instalado", None),
            ("Activado", True),
            ("Desactivado", False),
        ):
            self._sim_reranking.addItem(etiqueta, valor)
        self._sim_reranking.setToolTip(
            "Se guarda en el proyecto y lo usan el Simulador y el canal de mensajes de la versión publicada. "
            "Es independiente de la casilla Reranking de Búsqueda RAG (Laboratorio)."
        )
        self._sim_reranking.activated.connect(self._on_agent_reranking_changed)
        rerank_row.addWidget(self._sim_reranking, 1)
        form_layout.addLayout(rerank_row)

        action_row = QHBoxLayout()
        self._btn_simulate = QPushButton("Simular", form)
        self._btn_simulate.clicked.connect(self._on_simulate)
        self._sim_cancel = QPushButton("Cancelar", form)
        self._sim_cancel.clicked.connect(self._on_cancel_simulation)
        action_row.addWidget(self._btn_simulate)
        action_row.addWidget(self._sim_cancel)
        form_layout.addLayout(action_row)

        self._sim_progress = QProgressBar(form)
        self._sim_progress.setRange(0, 100)
        form_layout.addWidget(self._sim_progress)
        self._sim_status = QLabel("", form)
        form_layout.addWidget(self._sim_status)
        layout.addWidget(form)

        self._sim_report = QTextBrowser(tab)
        self._sim_report.setReadOnly(True)
        layout.addWidget(self._sim_report)
        return tab

    def _load_agent_reranking(self) -> None:
        """Ronda 102 (C4): muestra el ajuste guardado del proyecto activo."""
        valor = None
        if self._project_id:
            try:
                valor = self._context.project_service.get_project(self._project_id).agent_reranking
            except Exception:  # noqa: BLE001 - solo es la vista del ajuste
                valor = None
        indice = self._sim_reranking.findData(valor)
        self._sim_reranking.setCurrentIndex(indice if indice >= 0 else 0)

    def _on_agent_reranking_changed(self, _index: int = 0) -> None:
        if not self._project_id:
            return
        try:
            self._context.project_service.update_agent_reranking(self._project_id, self._sim_reranking.currentData())
        except Exception as exc:  # noqa: BLE001 - mismo criterio que el resto del panel
            self._report_error(exc)
            self._load_agent_reranking()
            return
        self._sim_status.setText(f"Reranking en el agente: {self._sim_reranking.currentText()} (guardado).")

    def _on_simulate(self) -> None:
        if self._active_job is not None or not self._project_id:
            return
        query_text = self._sim_query.text().strip()
        if not query_text:
            # Auditoría posterior a la Ronda 77 (hallazgo real de usuario):
            # el mismo síntoma ya corregido en ui/ingestion/panel.py
            # (Ronda 8, punto 27) para "Buscar"/"Comparar modelos" --
            # antes "Simular" con la consulta vacía retornaba en silencio,
            # sin ningún job ni aviso, y quien lo probara no tenía forma
            # de saber si el botón no hacía nada o si la simulación seguía
            # en curso. Este panel no tenía la misma corrección.
            QMessageBox.information(self, "Falta la consulta", "Escribe una consulta antes de simular.")
            return
        project_id = self._project_id
        provided_variables = parse_provided_variables(self._sim_variables.text())
        source_id = self._sim_source_id.text().strip() or None

        self._sim_status.setText("Simulando en segundo plano…")
        self._pending_trace = None

        def _run(handle) -> None:
            self._pending_trace = self._context.conversational_service.simulate(
                project_id, query_text, provided_variables=provided_variables, source_id=source_id, limit=5,
            )

        # Auditoría profunda (ronda posterior a la 76, ver bitácora):
        # a diferencia de ui/ingestion/panel.py (que envuelve cada
        # submit_task() con el helper _submit_job()), aquí se llamaba
        # directamente, sin ningún try/except -- una excepción real al
        # enviar el trabajo se habría propagado sin capturar, dejando
        # _sim_status diciendo "en segundo plano" con _active_job
        # nunca asignado.
        try:
            self._active_job = self._context.jobs.submit_task(_run)
        except Exception as exc:  # noqa: BLE001 - mismo criterio que _report_error en otros métodos de este panel
            self._report_error(exc)
            return
        self._sim_progress.setValue(0)
        self._apply_button_states()
        self._poll_timer.start()

    def _on_cancel_simulation(self) -> None:
        if self._active_job is None:
            return
        # El simulador (SimulateConversation/RagService.search_hybrid) no
        # revisa is_cancelled a medio camino -- igual que indexación/
        # búsqueda en la pestaña Ingesta, la cancelación se registra pero
        # el cálculo ya en curso termina de todas formas.
        self._active_job.cancel()
        self._sim_status.setText("Cancelación solicitada…")

    def _poll_active_job(self) -> None:
        if self._active_job is None:
            return
        self._sim_progress.setValue(int(self._active_job.progress * 100))
        if self._active_job.status.value not in ("completado", "fallido", "cancelado"):
            return

        self._poll_timer.stop()
        status = self._active_job.status.value
        error = self._active_job.error
        self._active_job = None
        self._apply_button_states()

        if status == "fallido":
            self._sim_status.setText("La simulación falló.")
            QMessageBox.critical(self, "Error", error or "Error desconocido.")
            return
        if status == "cancelado":
            self._sim_status.setText("Cancelación registrada, pero la simulación ya había terminado de calcularse.")
        else:
            self._sim_status.setText("Listo.")
        self._refresh_simulation_report()

        # Aviso emergente al terminar con éxito (ver mismo cambio en
        # ui/ingestion/panel.py y ui/quality/panel.py): antes, solo
        # cambiaba _sim_status, invisible si el usuario ya no estaba
        # parado en esta sub-pestaña.
        if status == "completado":
            QMessageBox.information(self, "Listo", "La simulación terminó.")

    def _refresh_simulation_report(self) -> None:
        trace = self._pending_trace
        self._pending_trace = None
        if trace is None:
            return

        action_labels = {
            "responder": "Responder",
            "aclarar": "Pedir aclaración",
            "abstenerse": "Abstenerse",
            "canalizar": "Canalizar",
        }
        parts = [f"<p><b>Consulta:</b> {html_escape(trace.query_text)}</p>"]
        if trace.matched_intent_name:
            parts.append(
                f"<p><b>Intención emparejada:</b> {html_escape(trace.matched_intent_name)} "
                f"— <b>confianza:</b> {trace.confidence:.3f}</p>"
            )
        else:
            parts.append("<p><b>Intención emparejada:</b> ninguna</p>")
        # Ronda 90 (hallazgo real de usuario): mostrar por qué ganó una
        # intención y no otra. Gana el mayor margen (positivo - negativo);
        # a igual margen, la mayor prioridad. "Confianza" es el positivo de
        # la ganadora.
        if trace.intent_scores:
            filas = "<br>".join(
                f"{html_escape(s.intent_name)} — margen {s.margin:.3f} "
                f"(positivo {s.positive:.3f} − negativo {s.negative:.3f}), prioridad {s.priority}"
                for s in trace.intent_scores[:3]
            )
            parts.append(f"<p><b>Puntuación de intenciones (las 3 mejores):</b><br>{filas}</p>")

        if trace.required_variables:
            parts.append(f"<p><b>Datos mínimos:</b> {html_escape(', '.join(trace.required_variables))}</p>")
        # Ronda 89: datos reconocidos en el texto de la consulta (con los
        # catálogos/valores de metadatos del proyecto), para que quien
        # prueba vea de dónde salió cada filtro.
        if trace.detected_variables:
            detectados = ", ".join(f"{k}={v}" for k, v in trace.detected_variables.items())
            parts.append(f"<p><b>Datos detectados en la consulta:</b> {html_escape(detectados)}</p>")
        if trace.ambiguous_variables:
            ambiguos = "; ".join(f"{k}: {' / '.join(v)}" for k, v in trace.ambiguous_variables.items())
            parts.append(
                f"<p><b>Datos ambiguos (no se llenaron):</b> {html_escape(ambiguos)} -- la consulta menciona "
                "más de un valor igual de específico.</p>"
            )
        if trace.missing_variables:
            parts.append(f"<p><b>Datos faltantes:</b> {html_escape(', '.join(trace.missing_variables))}</p>")
        if trace.clarifying_question:
            parts.append(f"<p><b>Pregunta aclaratoria:</b> {html_escape(trace.clarifying_question)}</p>")

        if trace.applied_metadata_filters:
            filtros = ", ".join(f"{k}={v}" for k, v in trace.applied_metadata_filters.items())
            # Ronda 89: el filtro ahora se aplica ANTES de buscar, así que
            # el número es de fuentes descartadas, no de resultados.
            parts.append(
                f"<p><b>Filtros aplicados:</b> {html_escape(filtros)} "
                f"({trace.excluded_by_metadata_filter} fuente(s) descartada(s) por no coincidir)</p>"
            )
        if trace.section_ordering:
            # Ronda 91 / Ronda 102 (C1): el ORDEN combina el puesto en la
            # búsqueda con la afinidad del título con la intención.
            parts.append(
                "<p><b>Orden de fragmentos:</b> combina el puesto en la búsqueda con la afinidad del título "
                "con la intención reconocida (nombre, descripción y ejemplos), en partes iguales (RRF); a igual "
                "resultado, el orden de la búsqueda. Junto a cada fragmento se indica su puesto en la "
                "búsqueda y su afinidad. Por eso los puntajes entre corchetes pueden no ir de mayor a menor.</p>"
            )
        # Ronda 102 (C4): si se aplicó reranking y con qué modelo.
        ajustes = {"automatico": "automático", "activado": "activado", "desactivado": "desactivado"}
        if trace.action.value == "responder" or trace.search_results:
            if trace.reranking_applied:
                rerank_txt = f"aplicado — modelo {html_escape(trace.reranking_model or '(sin nombre)')}"
            else:
                rerank_txt = "no aplicado"
            parts.append(
                f"<p><b>Reranking:</b> {rerank_txt} "
                f"(ajuste del proyecto: {ajustes.get(trace.reranking_setting, trace.reranking_setting)})</p>"
            )
        if trace.reranking_note:
            parts.append(f"<p><i>{html_escape(trace.reranking_note)}</i></p>")
        if trace.retrieval_query:
            parts.append(
                f"<p><b>Texto usado para buscar:</b> {html_escape(trace.retrieval_query)} "
                "(sin las menciones de los valores ya filtrados)</p>"
            )

        parts.append(
            f"<p><b>Reglas activadas:</b> "
            f"{html_escape(', '.join(trace.fired_rules)) if trace.fired_rules else 'ninguna'}</p>"
        )
        parts.append(f"<p><b>Decisión tomada:</b> {action_labels.get(trace.action.value, trace.action.value)}</p>")

        if trace.abstention_reason:
            parts.append(f"<p><i>{html_escape(trace.abstention_reason)}</i></p>")

        if trace.channeling is not None:
            scheme = trace.channeling
            parts.append(
                "<p><b>Paquete de canalización:</b><br>"
                f"Código: {html_escape(scheme.code)}<br>"
                f"Área destino: {html_escape(scheme.target_area or '(sin definir)')}<br>"
                f"Medio: {html_escape(scheme.medium.value)}<br>"
                f"Mensaje al usuario: {html_escape(scheme.user_message or '(sin definir)')}</p>"
            )
        elif trace.action.value == "canalizar":
            # Ronda 87: la causa concreta (sin código, código inexistente
            # o esquema inactivo), calculada por SimulateConversation.
            parts.append(
                "<p><i>"
                + html_escape(
                    trace.channeling_note
                    or "Se decidió canalizar, pero no hay paquete de canalización que generar."
                )
                + "</i></p>"
            )

        if trace.structured_result is not None and trace.structured_result.rows:
            # Pista B.4 del ADR-003: resuelto por la vía estructurada --
            # nunca aparece junto con search_results (ver
            # SimulateConversation.execute, Opción B: un único camino
            # ganador por respuesta).
            rows = trace.structured_result.rows
            parts.append(f"<p><b>Filas de datos estructurados ({len(rows)}):</b></p>")
            for row in rows:
                source_title = (
                    self._source_title(self._project_id, row.source_id)
                    if self._project_id else row.source_id
                )
                valores = ", ".join(f"{k}={v}" for k, v in row.values.items())
                parts.append(
                    f"<p>{html_escape(source_title)}"
                    f"{' — ' + html_escape(row.section_title) if row.section_title else ''} — "
                    f"{html_escape(valores)}</p>"
                )
        elif trace.search_results:
            parts.append(f"<p><b>Fuentes y fragmentos ({len(trace.search_results)}):</b></p>")
            orden = trace.result_ordering if len(trace.result_ordering) == len(trace.search_results) else []
            for posicion, result in enumerate(trace.search_results):
                source_title = (
                    self._source_title(self._project_id, result.chunk.source_id)
                    if self._project_id else result.chunk.source_id
                )
                preview = result.chunk.text[:160].replace("\n", " ")
                detalle = ""
                if orden:
                    o = orden[posicion]
                    detalle = (
                        f" <small>(búsqueda #{o.retrieval_rank}; afinidad {o.affinity:.2f} con "
                        f"«{html_escape(o.affinity_title[:60])}»)</small>"
                    )
                parts.append(
                    f"<p>[{result.score:.3f}] {html_escape(source_title)}{detalle} — {html_escape(preview)}…</p>"
                )

        # Fase 3/4 de multimodalidad nativa (RAG 3): tercer canal de
        # evidencia, independiente del if/elif de arriba -- nunca se
        # fusiona con datos estructurados ni con fragmentos de texto
        # (ver SimulationTrace.image_results), así que se muestra
        # aparte, no como otra rama del mismo elif.
        if trace.image_results:
            parts.append(f"<p><b>Imágenes relacionadas ({len(trace.image_results)}):</b></p>")
            for result in trace.image_results:
                source_title = (
                    self._source_title(self._project_id, result.chunk.source_id)
                    if self._project_id else result.chunk.source_id
                )
                parts.append(
                    f"<p>[{result.score:.3f}] {html_escape(source_title)} — "
                    f"{html_escape(result.chunk.image_relative_path or '(sin ruta)')}</p>"
                )

        self._sim_report.setHtml("".join(parts))
