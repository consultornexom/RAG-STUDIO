"""Lógica pura (sin Qt) para interpretar los campos de texto libre del
panel de Diseño conversacional (Etapa 5): listas separadas por comas,
listas por línea, pares "código: valor" y condiciones "campo operador
valor".

Separado de `ui/conversational/panel.py` a propósito -- mismo criterio
que `ui/ingestion/search_highlighting.py`: son funciones sin efectos
secundarios ni dependencia de PySide6, así que se pueden probar con
pytest normal en cualquier entorno, incluso uno sin las bibliotecas
nativas de Qt (libEGL/libGL) donde `panel.py` no se puede ni importar.

Se prefirió texto libre con un formato simple (una línea por elemento,
"campo operador valor", "código: pregunta") en vez de tablas editables
widget por widget -- consistente con el resto de la UI de esta
aplicación (p. ej. `document_type_code` como campo de texto en
Ingesta): más rápido de construir y de leer para una primera versión,
aunque menos "amigable" que un editor de tabla dedicado. Ver README,
"Limitaciones conocidas".

Regla de capa (ADR-001, sección 4): este módulo no importa domain ni
application -- devuelve dicts/listas de texto plano. Es
`ConversationalService.create_guardrail_rule` (application) quien
construye los `RuleCondition` de dominio a partir de esos dicts; aquí
solo se decide CÓMO separar el texto escrito en el formulario."""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# Se revisan en este orden (más largos primero) para no confundir "<="
# con "<" seguido de "=" -- y "contiene" al final, porque es la única
# palabra (no un símbolo) entre los operadores soportados.
_OPERATOR_TOKENS = ["<=", ">=", "!=", "=", "<", ">", "contiene"]


def parse_lines(text: str) -> list[str]:
    """Una línea por elemento; líneas vacías o solo espacios se
    ignoran."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_csv(text: str) -> list[str]:
    """Lista separada por comas en una sola línea (p. ej. "programa,
    plantel, modalidad")."""
    return [item.strip() for item in text.split(",") if item.strip()]


def parse_key_value_lines(text: str, separator: str = ":") -> dict[str, str]:
    """Una línea por par "clave: valor" (p. ej. preguntas aclaratorias:
    "plantel: ¿En qué plantel estudias?"). Líneas sin el separador se
    ignoran en vez de fallar -- se prefiere una entrada de menos a
    reventar todo el formulario por una línea mal escrita."""
    result: dict[str, str] = {}
    for line in parse_lines(text):
        if separator not in line:
            continue
        key, _, value = line.partition(separator)
        key = key.strip()
        value = value.strip()
        if key and value:
            result[key] = value
    return result


def parse_provided_variables(text: str) -> dict[str, str]:
    """Variables que la persona que simula ya "proporcionó", en
    formato "codigo=valor, codigo2=valor2" (una sola línea, separadas
    por comas -- para el simulador, donde el formulario es más
    pequeño que el de crear una intención)."""
    result: dict[str, str] = {}
    for item in parse_csv(text):
        if "=" not in item:
            continue
        key, _, value = item.partition("=")
        key = key.strip()
        value = value.strip()
        if key and value:
            result[key] = value
    return result


_SYMBOLIC_OPERATOR = re.compile(r"<=|>=|!=|=|<|>")
_WORD_OPERATOR = re.compile(r"\s+contiene\s+", re.IGNORECASE)


def _split_condition(line: str) -> Optional[dict[str, str]]:
    """Separa UNA línea "campo operador valor" usando el PRIMER operador
    que aparece en la línea (Ronda 87). Antes se buscaba cada operador
    en un orden fijo en toda la línea, así que en "intencion contiene
    a=b" ganaba el "=" del valor y el campo quedaba como "intencion
    contiene a". Devuelve None si la línea no tiene operador, campo o
    valor."""
    candidates: list[tuple[int, int, str]] = []
    symbolic = _SYMBOLIC_OPERATOR.search(line)
    if symbolic:
        candidates.append((symbolic.start(), symbolic.end(), symbolic.group(0)))
    word = _WORD_OPERATOR.search(line)
    if word:
        candidates.append((word.start(), word.end(), "contiene"))
    if not candidates:
        return None
    start, end, operator = min(candidates)
    field = line[:start].strip()
    value = line[end:].strip()
    if not field or not value:
        return None
    return {"field": field, "operator": operator, "value": value}


def parse_conditions_detailed(text: str) -> tuple[list[dict[str, str]], list[str]]:
    """Como parse_conditions, pero devuelve además las líneas que NO se
    pudieron interpretar (Ronda 87). La interfaz las usa para no guardar
    una regla con condiciones mal escritas: antes se ignoraban en
    silencio y, si ninguna línea era válida, la regla quedaba SIN
    condiciones, es decir, incondicional -- se disparaba en todas las
    consultas."""
    conditions: list[dict[str, str]] = []
    unrecognized: list[str] = []
    for line in parse_lines(text):
        parsed = _split_condition(line)
        if parsed is None:
            unrecognized.append(line)
        else:
            conditions.append(parsed)
    return conditions, unrecognized


def parse_conditions(text: str) -> list[dict[str, str]]:
    """Una condición por línea, formato "campo operador valor" (p. ej.
    "confianza < 0.45", "intencion = Solicitar asesor humano"). Líneas
    que no contienen ningún operador reconocido se ignoran aquí; para
    detectarlas, usar parse_conditions_detailed.

    Devuelve dicts {"field", "operator", "value"} en vez de
    `domain.conversational.entities.RuleCondition` a propósito (ADR-001,
    sección 4: la UI nunca importa domain) -- es
    ConversationalService.create_guardrail_rule quien construye el
    RuleCondition real a partir de este dict."""
    return parse_conditions_detailed(text)[0]


def _canonical_field(name: str) -> str:
    # Misma forma canónica que domain.conversational.text_normalization.
    # normalize_field_name (esta capa no importa domain, ADR-001).
    text = unicodedata.normalize("NFKD", name.strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[\s\-]+", "_", text)


def describe_condition_problems(text: str, known_fields: dict[str, str]) -> tuple[list[str], list[str]]:
    """Revisa el texto de condiciones de una regla ANTES de guardarla
    (Ronda 87). Devuelve (errores, advertencias):

    - errores: líneas que no siguen "campo operador valor". Bloquean el
      guardado, porque una línea ignorada cambia el significado de la
      regla (y si se ignoran todas, la regla queda incondicional).
    - advertencias: campos que el motor no conoce (p. ej. "plantel"):
      la condición nunca se cumplirá. No bloquean, pero se pide
      confirmación.
    """
    conditions, unrecognized = parse_conditions_detailed(text)
    errors = [f'"{line}" no sigue el formato campo operador valor' for line in unrecognized]
    warnings = []
    for condition in conditions:
        canonical = _canonical_field(condition["field"])
        if canonical not in known_fields:
            warnings.append(
                f'"{condition["field"]}" no es un campo que el motor conozca; esa condición nunca se cumplirá'
            )
    return errors, warnings


def condition_syntax_help(known_fields: dict[str, str]) -> str:
    """Texto de ayuda con la sintaxis y los campos válidos, para
    mostrarlo junto a los errores y en la información sobre herramientas."""
    fields = "\n".join(f"  • {name}: {description}" for name, description in known_fields.items())
    return (
        "Formato: una condición por línea, campo operador valor. Todas deben cumplirse (Y).\n"
        "Operadores: =  !=  <  <=  >  >=  contiene\n"
        f"Campos válidos:\n{fields}\n"
        "Ejemplos:\n"
        "  intencion = Solicitar asesor humano\n"
        "  confianza < 0.45\n"
        "  nivel_riesgo = alto\n"
        "  variables_faltantes = 1\n"
        "Sin condiciones = la regla se aplica a todas las consultas."
    )


def format_key_value_lines(pairs: dict[str, str], separator: str = ":") -> str:
    """Inverso de parse_key_value_lines, para precargar en el
    formulario de edición un dict ya guardado (p. ej.
    Intent.clarifying_questions) en el mismo formato de texto que se
    usa para capturarlo -- mismo criterio que format_conditions para
    parse_conditions. Ajuste funcional del 2026-09-03 (hallazgo real de
    usuario, ver bitácora): edición completa de intenciones."""
    return "\n".join(f"{key}{separator} {value}" for key, value in pairs.items())


def format_conditions(conditions) -> str:
    """Inverso aproximado de parse_conditions, para mostrar
    condiciones ya guardadas (objetos RuleCondition devueltos por
    ConversationalService, leídos aquí solo por sus atributos -- mismo
    criterio que el resto de la UI, p. ej. `chunk.chunk_type.value` en
    ui/ingestion/panel.py) en el mismo formato de texto que se usa para
    crearlas."""
    return "\n".join(f"{c.field} {c.operator.value} {c.value}" for c in conditions)
