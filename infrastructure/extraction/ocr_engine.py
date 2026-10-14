"""Adaptador de `domain.ingestion.ports.OcrEngine` hacia Tesseract
real, vía `pytesseract` (ADR-001, sección 4: infrastructure implementa
los puertos de domain). Dependencia opcional (extra "ocr" en
pyproject.toml, ya incluida en requirements.txt): si las librerías
Python (pytesseract, Pillow) no están instaladas, `bootstrap.py` no
construye este adaptador y `PdfTextExtractor` sigue funcionando
exactamente igual que antes de Módulo 4 (sin OCR, solo advertencias
por página) -- ningún comportamiento existente cambia para quien no
instale el extra.

pytesseract es solo un envoltorio: requiere el binario `tesseract`
instalado en el sistema operativo, con el paquete de idioma que se use
(por defecto español + inglés).
    - Ubuntu/Debian: sudo apt install tesseract-ocr tesseract-ocr-spa
    - Windows: instalador de UB-Mannheim (ver manual de usuario,
      capítulo 2) -- a diferencia de Linux, ese instalador NO agrega
      automáticamente el binario al PATH del sistema, así que
      pytesseract no lo encuentra solo (de ahí `_ubicar_tesseract_windows`
      abajo: agregado 2026-08-01, auditoría de madurez ronda 5, tras
      confirmar con el consultor que hay un usuario probando la
      herramienta en Windows).
"""
from __future__ import annotations

import importlib.util
import io
import os
import platform
from pathlib import Path
from typing import Optional

from domain.ingestion.exceptions import OcrEngineUnavailableError
from domain.ingestion.ports import OcrEngine

try:
    import pytesseract
    from PIL import Image, ImageChops, ImageFilter
    _OCR_LIBS_AVAILABLE = True
except ImportError:
    _OCR_LIBS_AVAILABLE = False

# Variable de entorno opcional para indicar dónde quedó instalado el
# binario de Tesseract, útil sobre todo en Windows (ver docstring del
# módulo) cuando no quedó en el PATH. Si no está definida, se prueban
# las rutas de instalación por defecto del instalador de UB-Mannheim
# antes de rendirse.
_ENV_VAR_RUTA_TESSERACT = "RAGSTUDIO_TESSERACT_PATH"

# Rutas donde el instalador oficial de Windows (UB-Mannheim) deja el
# binario por defecto, según se instale para todos los usuarios o solo
# para el usuario actual. Confirmadas contra la documentación del
# instalador -- no se puede probar en este entorno (Linux), por lo que
# el consultor debe confirmar en una máquina Windows real (ver
# checklist_validacion_visual.md).
_RUTAS_WINDOWS_POR_DEFECTO = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def _ubicar_tesseract_windows() -> Optional[str]:
    """Busca el binario de Tesseract en las ubicaciones típicas de
    Windows cuando no está en el PATH. Devuelve la ruta si la
    encuentra, o None si no (en cuyo caso se sigue intentando el PATH
    normal, y si tampoco está ahí, `image_to_text` lanza el error de
    siempre con instrucciones)."""
    ruta_explicita = os.environ.get(_ENV_VAR_RUTA_TESSERACT)
    if ruta_explicita and Path(ruta_explicita).is_file():
        return ruta_explicita
    for ruta in _RUTAS_WINDOWS_POR_DEFECTO:
        if Path(ruta).is_file():
            return ruta
    return None

# PyMuPDF (fitz) rasteriza páginas de PDF a imagen, sin depender de un
# binario externo adicional (poppler) más allá del propio paquete pip.
# Solo se necesita saber si está instalado aquí -- el import real y su
# uso (fitz.open(...)) vive en infrastructure.extraction.text_extractors,
# que lo importa de forma perezosa cuando de verdad hace falta rasterizar.
_FITZ_AVAILABLE = importlib.util.find_spec("fitz") is not None

_DEFAULT_LANG = "spa+eng"

# Ronda 22 (hallazgo real con ingcom.pdf, ver Ronda 21 punto 63):
# Tesseract, al reconocer una página completa, suele clasificar una
# banda horizontal con fondo de color saturado (un encabezado de
# sección en un color de marca, p. ej. "1er. Cuatrimestre" sobre fondo
# turquesa) como "no es texto" y la omite por completo -- no aparece
# en ningún lado del resultado, sin ninguna advertencia. Recortar esa
# banda por separado y reconocerla con --psm 6 sí recupera texto, al
# menos parcialmente (confirmado con el documento real: "2do.
# Cuatrimestre", "5to. Cuatrimestre", "7mo. Cuatrimestre", "9no.
# Cuatrimestre", "12vo. Cuatrimestre" y una URL de pie de página se
# recuperaron limpios; el resto de cada banda, con varias etiquetas
# lado a lado, sale con ruido de reconocimiento). Los umbrales de abajo
# se calibraron contra ese documento real -- ver
# `_detect_color_bands`/`_recover_color_band_text`.
_MIN_BAND_COLOR_SATURATION = 40
_BAND_COLOR_VALUE_RANGE = (100, 250)
_MIN_BAND_COLOR_ROW_FRACTION = 0.10
_MIN_COLOR_BAND_HEIGHT_PX = 12
_MAX_COLOR_BAND_HEIGHT_PX = 100
_MAX_COLOR_BANDS_PER_PAGE = 10
"""Límite de seguridad: una página con más bandas de color detectadas
que esto probablemente no sigue el patrón "encabezado de sección en un
color de marca" (ruido, una plantilla con fondo de color en general, o
una fotografía) -- se descarta por completo en vez de lanzar decenas de
reconocimientos de OCR adicionales de bajo valor por página."""
_COLOR_BAND_PADDING_PX = 8
_COLOR_BAND_PSM_CONFIG = "--psm 6"

# Tarea diferida durante la Fase -1 de RAG 4 (ver bitácora, punto 241:
# el mismo tipo de defecto de layout complejo que ya se había detectado
# parcialmente en la Ronda 22) -- preprocesamiento ligero de imagen
# antes de pasarla a Tesseract, usando únicamente PIL (mismo criterio
# ya establecido en este módulo: sin numpy/OpenCV). Validado de forma
# empírica contra el mismo documento real que motivó la Ronda 22
# (Licenciatura/ingcom.pdf): sin este preprocesamiento, Tesseract
# reconocía 1 de 14 encabezados de cuatrimestre (bandas de color); con
# escala de grises + un filtro de medianas (ruido de escaneo/rasterizado)
# + binarización con el umbral de Otsu (adaptado a cada imagen, no un
# número fijo que no generalizaría entre documentos con distinta
# iluminación/contraste de escaneo), se recuperaron 8-9 de 14, sin
# perder contenido del resto de la página -- el mismo texto de los
# cursos aparece en ambos casos, solo que agrupado en un orden de
# lectura más coherente con la cuadrícula visual real.
_DENOISE_MEDIAN_FILTER_SIZE = 3


def _otsu_threshold(histogram: list[int]) -> int:
    """Umbral óptimo de binarización (método de Otsu) a partir del
    histograma de 256 niveles de una imagen en escala de grises
    (`Image.histogram()`). Implementación en Python puro -- sin numpy,
    ver nota del módulo -- viable porque el histograma ya resume la
    imagen completa a 256 valores; el costo de las sumas acumuladas es
    insignificante frente al propio reconocimiento de Tesseract.
    Adaptativo por imagen (a diferencia de un umbral fijo) porque el
    contraste real de un documento escaneado/rasterizado varía de una
    fuente a otra -- un umbral fijo calibrado contra un solo documento
    no generalizaría de forma confiable a otros."""
    total = sum(histogram)
    if total == 0:
        return 128
    sum_all = sum(level * count for level, count in enumerate(histogram))
    sum_below = 0
    weight_below = 0
    best_variance = -1.0
    # Cuando varios niveles consecutivos empatan en la varianza máxima
    # (típico de un histograma bimodal con un valle plano de densidad
    # cero entre los dos picos -- un caso sintético, poco común en una
    # imagen real ya suavizada por el filtro de medianas), el punto
    # medio del tramo empatado es un umbral más razonable que el primer
    # nivel del tramo (que cae pegado al pico oscuro, no "entre" los
    # dos picos).
    best_range_start = 0
    best_range_end = 0
    for level, count in enumerate(histogram):
        weight_below += count
        if weight_below == 0:
            continue
        weight_above = total - weight_below
        if weight_above == 0:
            break
        sum_below += level * count
        mean_below = sum_below / weight_below
        mean_above = (sum_all - sum_below) / weight_above
        variance_between = weight_below * weight_above * (mean_below - mean_above) ** 2
        if variance_between > best_variance:
            best_variance = variance_between
            best_range_start = best_range_end = level
        elif variance_between == best_variance:
            best_range_end = level
    return (best_range_start + best_range_end) // 2


def _preprocess_for_ocr(image: "Image.Image") -> "Image.Image":
    """Preprocesamiento ligero antes de Tesseract: escala de grises,
    reducción de ruido leve (filtro de medianas) y binarización con el
    umbral de Otsu -- ver la nota junto a `_DENOISE_MEDIAN_FILTER_SIZE`
    para la validación empírica. Recibe y devuelve una imagen PIL
    nueva; nunca modifica `image` en el lugar, porque quien llama (
    `image_to_text`) todavía necesita la imagen ORIGINAL a color para
    `_detect_color_bands` (que depende de saturación/valor HSV -- una
    imagen ya binarizada no tiene esa información)."""
    grayscale = image.convert("L")
    denoised = grayscale.filter(ImageFilter.MedianFilter(size=_DENOISE_MEDIAN_FILTER_SIZE))
    threshold = _otsu_threshold(denoised.histogram())
    return denoised.point(lambda p: 255 if p > threshold else 0)


def _detect_color_bands(image: "Image.Image") -> list[tuple[int, int]]:
    """Devuelve los rangos verticales (y_inicio, y_fin) en píxeles de
    las bandas horizontales de `image` cuyo fondo es mayormente de
    color saturado (ni texto negro/gris sobre blanco, que tiene
    saturación baja, ni blanco puro) -- ver la nota de Ronda 22 arriba.
    Usa únicamente PIL (sin depender de numpy, que no es una
    dependencia propia del proyecto): el filtrado por saturación/valor
    se hace con `Image.point`, y el perfil de color por fila con un
    `resize` a una sola columna (`Image.BOX` promedia, en C, en vez de
    iterar píxel por píxel en Python).

    Ya filtra por una altura plausible de una sola banda de encabezado
    (`_MIN_COLOR_BAND_HEIGHT_PX`/`_MAX_COLOR_BAND_HEIGHT_PX`) -- un
    logotipo o una fotografía a color producen bandas mucho más altas
    o irregulares, que se descartan a propósito en vez de intentar
    reconocerlas como texto."""
    hsv = image.convert("RGB").convert("HSV")
    saturation, _, value = hsv.split()
    saturated_mask = saturation.point(lambda p: 255 if p > _MIN_BAND_COLOR_SATURATION else 0)
    value_lo, value_hi = _BAND_COLOR_VALUE_RANGE
    mid_value_mask = value.point(lambda p: 255 if value_lo < p < value_hi else 0)
    colored_mask = ImageChops.multiply(saturated_mask, mid_value_mask)

    _, height = image.size
    row_profile = colored_mask.resize((1, height), Image.BOX)
    row_fraction = [level / 255.0 for level in row_profile.getdata()]

    bands: list[tuple[int, int]] = []
    band_start: Optional[int] = None
    for y, fraction in enumerate(row_fraction):
        is_colored_row = fraction > _MIN_BAND_COLOR_ROW_FRACTION
        if is_colored_row and band_start is None:
            band_start = y
        elif not is_colored_row and band_start is not None:
            bands.append((band_start, y))
            band_start = None
    if band_start is not None:
        bands.append((band_start, height))

    plausible_bands = [
        (y0, y1) for y0, y1 in bands
        if _MIN_COLOR_BAND_HEIGHT_PX <= (y1 - y0) <= _MAX_COLOR_BAND_HEIGHT_PX
    ]
    return plausible_bands[:_MAX_COLOR_BANDS_PER_PAGE]


def ocr_dependencies_available() -> bool:
    """True si todo lo necesario para hacer OCR sobre páginas de PDF
    está instalado: pytesseract + Pillow (reconocimiento) y PyMuPDF
    (rasterizado de páginas). No confirma que el binario de `tesseract`
    en sí esté instalado -- eso solo se descubre en el primer uso real
    (ver `TesseractOcrEngine.image_to_text`)."""
    return _OCR_LIBS_AVAILABLE and _FITZ_AVAILABLE


class TesseractOcrEngine(OcrEngine):
    def __init__(self, lang: str = _DEFAULT_LANG, preprocess: bool = True):
        if not _OCR_LIBS_AVAILABLE:
            raise OcrEngineUnavailableError(
                "Las librerías de OCR (pytesseract, Pillow) no están instaladas. "
                "Instala el extra opcional: pip install ragstudio[ocr]"
            )
        self._lang = lang
        # Ver _preprocess_for_ocr: mejora validada empíricamente
        # (Licenciatura/ingcom.pdf, ver comentario junto a
        # _DENOISE_MEDIAN_FILTER_SIZE), activada por defecto. Se deja
        # como parámetro -- no como comportamiento incondicional -- por
        # si algún documento real regresionara con la binarización
        # (p. ej. un escaneo ya muy limpio donde el filtro de medianas
        # solo agregue costo sin beneficio): permite desactivarla sin
        # tocar código, no porque se haya observado una regresión real.
        self._preprocess = preprocess
        # En Windows, si el binario no está en el PATH, se busca en las
        # ubicaciones por defecto del instalador (o en la variable de
        # entorno RAGSTUDIO_TESSERACT_PATH) y se le indica a pytesseract
        # dónde está explícitamente -- en Linux/macOS no hace falta
        # (el binario instalado por el gestor de paquetes ya queda en
        # el PATH), así que no se toca `tesseract_cmd` ahí.
        if platform.system() == "Windows":
            ruta_encontrada = _ubicar_tesseract_windows()
            if ruta_encontrada is not None:
                pytesseract.pytesseract.tesseract_cmd = ruta_encontrada
        # Auditoría Ronda 21 (hallazgo real con un documento de prueba):
        # ni esta comprobación ni image_to_text detectaban que el binario
        # de Tesseract puede aceptar `lang="spa+eng"` SIN el paquete de
        # idioma "spa" instalado -- imprime "Failed loading language
        # 'spa'" en stderr, pero termina con código de salida 0 y sigue
        # reconociendo solo con "eng", en silencio. Sin verificar esto,
        # un documento en español pierde todos los acentos/eñes (un
        # modelo entrenado solo en inglés no los espera) sin que nada en
        # la aplicación se entere -- ni una excepción, ni una advertencia
        # en el resultado de extracción. Se verifica una sola vez (no en
        # cada página) y se cachea el resultado.
        self._verified_lang = False

    def _verify_language_available(self) -> None:
        if self._verified_lang:
            return
        requested = [code for code in self._lang.split("+") if code]
        try:
            installed = set(pytesseract.get_languages(config=""))
        except pytesseract.TesseractNotFoundError:
            # Se deja sin resolver a propósito -- image_to_text ya
            # captura este mismo error con un mensaje claro; repetirlo
            # aquí solo duplicaría el diagnóstico.
            self._verified_lang = True
            return
        missing = [code for code in requested if code not in installed]
        if missing:
            raise OcrEngineUnavailableError(
                f"Tesseract no tiene instalado el paquete de idioma {', '.join(missing)!r} "
                f"(idiomas configurados: {self._lang!r}; instalados en este sistema: "
                f"{', '.join(sorted(installed)) or 'ninguno'!r}). Sin él, Tesseract reconoce el "
                "texto solo con los idiomas que sí tiene instalados -- en español, esto "
                "produce texto sin acentos ni eñes, sin ningún aviso. Instala el paquete "
                "que falta (Ubuntu/Debian: 'sudo apt install tesseract-ocr-spa') antes de "
                "confiar en el resultado."
            )
        self._verified_lang = True

    def _recover_color_band_text(self, image: "Image.Image") -> list[str]:
        """Ronda 22: recorta cada banda de color detectada
        (`_detect_color_bands`) por separado y la reconoce con
        `--psm 6` -- ver la nota junto a `_detect_color_bands` para el
        hallazgo real que motiva esto. Es una recuperación de mejor
        esfuerzo, no una ruta crítica: cualquier fallo aquí (una
        imagen que PIL no puede procesar, un error puntual de
        Tesseract en una banda) se ignora en silencio para esa banda o
        para la página, sin afectar el resultado principal de
        `image_to_text` -- ya viene marcado como texto de confianza
        baja en quien lo llama, así que no vale la pena propagar un
        error por él."""
        try:
            bands = _detect_color_bands(image)
        except Exception:
            return []
        if not bands:
            return []
        width, height = image.size
        recovered: list[str] = []
        for y0, y1 in bands:
            top = max(0, y0 - _COLOR_BAND_PADDING_PX)
            bottom = min(height, y1 + _COLOR_BAND_PADDING_PX)
            try:
                crop = image.crop((0, top, width, bottom))
                # Ronda 74: a diferencia de la página completa, el
                # mismo preprocesamiento SÍ se probó aquí y se
                # descartó -- en un recorte chico (una sola banda,
                # unas pocas decenas de píxeles de alto) el filtro de
                # medianas borra los propios trazos delgados del texto
                # en vez de solo quitar ruido, y Tesseract termina sin
                # reconocer nada (confirmado con una imagen sintética:
                # "Section Header" reconocido sin preprocesar, recorte
                # completamente negro y vacío después de preprocesar).
                # Se deja este recorte tal cual, sin preprocesar.
                text = pytesseract.image_to_string(
                    crop, lang=self._lang, config=_COLOR_BAND_PSM_CONFIG
                ).strip()
            except Exception:
                continue
            if text:
                recovered.append(text)
        return recovered

    def image_to_text(self, image_bytes: bytes) -> str:
        self._verify_language_available()
        try:
            image = Image.open(io.BytesIO(image_bytes))
            # `_detect_color_bands` (llamado dentro de
            # _recover_color_band_text, abajo) necesita la imagen a
            # color ORIGINAL -- se preprocesa solo una copia para el
            # reconocimiento principal, nunca `image` en el lugar.
            ocr_target = _preprocess_for_ocr(image) if self._preprocess else image
            text = pytesseract.image_to_string(ocr_target, lang=self._lang)
            recovered = self._recover_color_band_text(image)
            if recovered:
                text += (
                    "\n\n[Texto adicional recuperado de bandas de color -- "
                    "reconocimiento OCR de confianza baja, puede contener ruido]\n"
                    + "\n".join(recovered)
                )
            return text
        except pytesseract.TesseractNotFoundError as exc:
            if platform.system() == "Windows":
                raise OcrEngineUnavailableError(
                    "El binario de Tesseract no está instalado o no se pudo encontrar. "
                    "pytesseract solo es un adaptador -- el motor OCR en sí se instala "
                    "aparte: descarga el instalador de Tesseract para Windows (UB-Mannheim, "
                    "ver manual de usuario, capítulo 2) y, si sigue sin encontrarse, define "
                    "la variable de entorno RAGSTUDIO_TESSERACT_PATH con la ruta completa a "
                    "tesseract.exe (por ejemplo 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe')."
                ) from exc
            raise OcrEngineUnavailableError(
                "El binario de Tesseract no está instalado o no está en el PATH del "
                "sistema. pytesseract solo es un adaptador -- el motor OCR en sí se "
                "instala aparte (Ubuntu/Debian: 'sudo apt install tesseract-ocr "
                "tesseract-ocr-spa')."
            ) from exc
