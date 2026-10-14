"""Pruebas de integración reales del adaptador de OCR
(`infrastructure/extraction/ocr_engine.py`, Módulo 4). Se omiten
automáticamente si el extra opcional "ocr" (pytesseract, Pillow) no
está instalado -- mismo patrón que `tests/smoke/test_ui_construction.py`
para PySide6."""
import io
import random

import pytest

from domain.ingestion.exceptions import OcrEngineUnavailableError
from infrastructure.extraction import ocr_engine as ocr_engine_module
from infrastructure.extraction.ocr_engine import TesseractOcrEngine, ocr_dependencies_available

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

_requires_ocr_libs = pytest.mark.skipif(
    not (_PIL_AVAILABLE and ocr_engine_module._OCR_LIBS_AVAILABLE),
    reason="pytesseract/Pillow (extra 'ocr') no instalados en este entorno",
)


def _test_font(size: int = 36):
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _text_image_bytes(text: str) -> bytes:
    image = Image.new("RGB", (600, 100), color="white")
    ImageDraw.Draw(image).text((10, 10), text, fill="black", font=_test_font())
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _image_with_colored_band(band_text: str) -> "Image.Image":
    # Simula el patrón real encontrado en ingcom.pdf (Ronda 21/22): un
    # documento con cuerpo normal (fondo blanco, texto negro) y una
    # banda horizontal de color saturado con texto encima -- el patrón
    # que Tesseract, sobre la página completa, clasifica como "no es
    # texto" y omite (ver `_detect_color_bands` en ocr_engine.py).
    image = Image.new("RGB", (600, 300), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 10), "Texto normal del cuerpo del documento", fill="black", font=_test_font(24))
    draw.rectangle((0, 100, 600, 135), fill=(138, 187, 193))  # mismo turquesa real
    draw.text((10, 105), band_text, fill="black", font=_test_font(24))
    draw.text((10, 200), "Mas texto normal despues de la banda", fill="black", font=_test_font(24))
    return image


def _image_bytes(image: "Image.Image") -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _noisy_low_contrast_text_image(text: str) -> "Image.Image":
    # Simula un escaneo de baja calidad: texto gris oscuro sobre fondo
    # gris claro (bajo contraste) más ruido "sal y pimienta" -- el tipo
    # de degradación que el preprocesamiento (escala de grises + filtro
    # de medianas + binarización Otsu) está pensado para corregir.
    # random.seed fijo: la prueba debe ser determinista, no depender de
    # qué ruido le tocó por azar en una corrida particular.
    rng = random.Random(42)
    image = Image.new("RGB", (600, 150), color=(210, 210, 210))
    ImageDraw.Draw(image).text((10, 40), text, fill=(90, 90, 90), font=_test_font(30))
    pixels = image.load()
    width, height = image.size
    for _ in range(9000):
        x = rng.randrange(width)
        y = rng.randrange(height)
        value = rng.randrange(256)
        pixels[x, y] = (value, value, value)
    return image


def test_ocr_dependencies_available_reflects_real_import_state():
    # No es una prueba de negocio, sino una confirmación honesta de
    # que la función refleja lo que de verdad hay instalado en este
    # entorno -- si algún día pytesseract/Pillow/PyMuPDF dejan de
    # instalarse aquí, esta prueba lo hace explícito en vez de que las
    # demás pruebas de OCR se salten en silencio sin razón aparente.
    assert ocr_dependencies_available() in (True, False)


@_requires_ocr_libs
def test_tesseract_ocr_engine_recognizes_real_rendered_text():
    # lang="eng": este entorno de construcción solo tiene el paquete de
    # idioma inglés de Tesseract instalado (ver el comentario de OCR en
    # requirements.txt para instalar también "spa" en una máquina real,
    # que es el idioma real de los documentos de RAG STUDIO).
    engine = TesseractOcrEngine(lang="eng")
    image_bytes = _text_image_bytes("Hello OCR World")

    result = engine.image_to_text(image_bytes)

    assert "Hello" in result
    assert "OCR" in result


@_requires_ocr_libs
def test_tesseract_ocr_engine_wraps_missing_binary_in_clear_domain_error(monkeypatch):
    def _raise_not_found(*args, **kwargs):
        raise ocr_engine_module.pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(ocr_engine_module.pytesseract, "image_to_string", _raise_not_found)
    engine = TesseractOcrEngine(lang="eng")

    with pytest.raises(OcrEngineUnavailableError) as exc_info:
        engine.image_to_text(_text_image_bytes("no importa el contenido"))
    assert "Tesseract" in str(exc_info.value)


def test_tesseract_ocr_engine_raises_clear_error_when_libs_missing(monkeypatch):
    monkeypatch.setattr(ocr_engine_module, "_OCR_LIBS_AVAILABLE", False)
    with pytest.raises(OcrEngineUnavailableError) as exc_info:
        TesseractOcrEngine()
    assert "ragstudio[ocr]" in str(exc_info.value)


# ---------- Auditoría Ronda 21: paquete de idioma configurado pero no
# instalado (hallazgo real, con un documento de prueba real: Tesseract
# acepta lang="spa+eng" sin tener "spa" instalado, imprime "Failed
# loading language 'spa'" en stderr pero sale con código 0 y reconoce
# solo con "eng" -- en silencio, sin que nada en la aplicación se
# enterara antes de esta ronda). ----------

@_requires_ocr_libs
def test_tesseract_ocr_engine_raises_clear_error_when_configured_language_is_not_installed(monkeypatch):
    monkeypatch.setattr(ocr_engine_module.pytesseract, "get_languages", lambda config="": ["eng", "osd"])
    engine = TesseractOcrEngine(lang="spa+eng")

    with pytest.raises(OcrEngineUnavailableError) as exc_info:
        engine.image_to_text(_text_image_bytes("no importa el contenido"))
    assert "spa" in str(exc_info.value)
    assert "tesseract-ocr-spa" in str(exc_info.value)


@_requires_ocr_libs
def test_tesseract_ocr_engine_language_check_runs_only_once(monkeypatch):
    calls = []

    def _fake_get_languages(config=""):
        calls.append(1)
        return ["eng", "osd"]

    monkeypatch.setattr(ocr_engine_module.pytesseract, "get_languages", _fake_get_languages)
    engine = TesseractOcrEngine(lang="eng")

    engine.image_to_text(_text_image_bytes("primera pagina"))
    engine.image_to_text(_text_image_bytes("segunda pagina"))

    assert len(calls) == 1  # se cachea -- no se repite la verificación por cada página


# ---------- Ronda 22 (hallazgo real con ingcom.pdf, ver Ronda 21 punto
# 63): recuperación de encabezados en banda de color, que Tesseract
# omite por completo al reconocer la página completa. ----------

def test_detect_color_bands_finds_a_plausible_header_band_and_ignores_a_tall_solid_block():
    from infrastructure.extraction.ocr_engine import _detect_color_bands

    image = Image.new("RGB", (600, 400), color="white")
    draw = ImageDraw.Draw(image)
    # Banda de encabezado plausible: 35px de alto, mismo turquesa real.
    draw.rectangle((0, 100, 600, 135), fill=(138, 187, 193))
    # Bloque alto (simula un logotipo o una fotografía a color) -- no
    # debe detectarse como candidato a "encabezado de sección", ver
    # _MAX_COLOR_BAND_HEIGHT_PX.
    draw.rectangle((0, 200, 600, 350), fill=(200, 100, 50))

    bands = _detect_color_bands(image)

    assert any(30 <= (y1 - y0) <= 40 and 90 <= y0 <= 110 for y0, y1 in bands)
    assert not any((y1 - y0) > 100 for y0, y1 in bands)


def test_detect_color_bands_returns_nothing_on_a_plain_black_and_white_page():
    from infrastructure.extraction.ocr_engine import _detect_color_bands

    image = Image.new("RGB", (600, 300), color="white")
    ImageDraw.Draw(image).text((10, 10), "Solo texto negro sobre blanco", fill="black", font=_test_font())

    assert _detect_color_bands(image) == []


@_requires_ocr_libs
def test_tesseract_ocr_engine_recovers_text_from_a_colored_header_band():
    engine = TesseractOcrEngine(lang="eng")
    image_bytes = _image_bytes(_image_with_colored_band("Section Header"))

    result = engine.image_to_text(image_bytes)

    assert "Texto adicional recuperado de bandas de color" in result
    # No se exige una coincidencia exacta del texto de la banda (el
    # propio hallazgo real documenta que la recuperación es parcial y
    # con ruido) -- solo que el mecanismo de recuperación se activó y
    # el cuerpo normal del documento sigue intacto antes del bloque.
    assert "Texto normal del cuerpo del documento" in result
    assert result.index("Texto adicional recuperado") > result.index("Texto normal del cuerpo")


@_requires_ocr_libs
def test_tesseract_ocr_engine_does_not_add_recovery_block_without_colored_bands():
    engine = TesseractOcrEngine(lang="eng")
    image_bytes = _text_image_bytes("Hello OCR World")

    result = engine.image_to_text(image_bytes)

    assert "Texto adicional recuperado de bandas de color" not in result


@_requires_ocr_libs
def test_tesseract_ocr_engine_color_band_recovery_never_breaks_main_result(monkeypatch):
    # Es una recuperación de mejor esfuerzo (ver el docstring de
    # _recover_color_band_text): si algo falla dentro de ella, el
    # resultado principal de image_to_text debe seguir devolviéndose
    # sin ningún bloque adicional, no propagar el error.
    def _raise(*args, **kwargs):
        raise RuntimeError("fallo simulado dentro de la recuperación")

    monkeypatch.setattr(ocr_engine_module, "_detect_color_bands", _raise)
    engine = TesseractOcrEngine(lang="eng")

    result = engine.image_to_text(_image_bytes(_image_with_colored_band("Section Header")))

    assert "Texto normal del cuerpo del documento" in result  # el OCR principal no se vio afectado
    assert "Texto adicional recuperado de bandas de color" not in result


@_requires_ocr_libs
def test_tesseract_ocr_engine_color_band_recovery_is_not_affected_by_preprocess_flag():
    # Ronda 74: el preprocesamiento (ver más abajo) mejora la página
    # completa pero se probó y se descartó explícitamente para los
    # recortes de banda de color -- un recorte tan chico pierde los
    # trazos delgados del texto con el filtro de medianas (confirmado
    # con una imagen sintética: la banda queda completamente negra).
    # Esta prueba fija ese comportamiento: preprocess=True/False deben
    # dar el mismo resultado de recuperación de banda, porque
    # _recover_color_band_text ya no depende de self._preprocess.
    image_bytes = _image_bytes(_image_with_colored_band("Section Header"))

    result_with = TesseractOcrEngine(lang="eng", preprocess=True).image_to_text(image_bytes)
    result_without = TesseractOcrEngine(lang="eng", preprocess=False).image_to_text(image_bytes)

    assert ("Texto adicional recuperado de bandas de color" in result_with) == (
        "Texto adicional recuperado de bandas de color" in result_without
    )


# ---------- Tarea diferida de la Fase -1 de RAG 4 (ver bitácora, punto
# 241 y Ronda 74): preprocesamiento ligero (escala de grises + filtro
# de medianas + binarización Otsu) antes de Tesseract. Validado de
# forma empírica contra Licenciatura/ingcom.pdf -- ver comentario junto
# a _DENOISE_MEDIAN_FILTER_SIZE en ocr_engine.py. ----------

def test_otsu_threshold_splits_a_clearly_bimodal_histogram_between_the_two_peaks():
    from infrastructure.extraction.ocr_engine import _otsu_threshold

    histogram = [0] * 256
    histogram[30] = 500   # pico oscuro (texto)
    histogram[220] = 500  # pico claro (fondo)

    threshold = _otsu_threshold(histogram)

    assert 30 < threshold < 220


def test_otsu_threshold_does_not_crash_on_an_empty_histogram():
    from infrastructure.extraction.ocr_engine import _otsu_threshold

    assert _otsu_threshold([0] * 256) == 128  # valor de respaldo documentado, no una excepción


@_requires_ocr_libs
def test_preprocess_for_ocr_returns_a_pure_black_and_white_grayscale_image():
    from infrastructure.extraction.ocr_engine import _preprocess_for_ocr

    image = _noisy_low_contrast_text_image("cualquier texto")

    preprocessed = _preprocess_for_ocr(image)

    assert preprocessed.mode == "L"
    assert set(preprocessed.getdata()) <= {0, 255}  # binarizada: solo dos niveles posibles


@_requires_ocr_libs
def test_preprocess_for_ocr_never_mutates_the_original_image_in_place():
    from infrastructure.extraction.ocr_engine import _preprocess_for_ocr

    image = _noisy_low_contrast_text_image("cualquier texto")
    original_bytes = image.tobytes()

    _preprocess_for_ocr(image)

    # _detect_color_bands (llamada aparte, sobre la imagen a color
    # original) depende de que este preprocesamiento nunca modifique
    # `image` en el lugar -- ver el docstring de _preprocess_for_ocr.
    assert image.tobytes() == original_bytes


@_requires_ocr_libs
def test_tesseract_ocr_engine_preprocessing_recovers_text_a_raw_call_misses():
    # Reproduce, con una imagen sintética determinista, el hallazgo real
    # validado contra Licenciatura/ingcom.pdf: un documento de bajo
    # contraste/con ruido que Tesseract no reconoce en absoluto sin
    # preprocesamiento, pero sí con él.
    image_bytes = _image_bytes(_noisy_low_contrast_text_image("Noisy Contrast Test"))

    engine_with_preprocessing = TesseractOcrEngine(lang="eng", preprocess=True)
    engine_without_preprocessing = TesseractOcrEngine(lang="eng", preprocess=False)

    result_with = engine_with_preprocessing.image_to_text(image_bytes)
    result_without = engine_without_preprocessing.image_to_text(image_bytes)

    assert "Noisy" in result_with and "Contrast" in result_with
    assert "Noisy" not in result_without  # confirma que la mejora es real, no un efecto placebo


def test_tesseract_ocr_engine_preprocessing_is_enabled_by_default():
    engine = TesseractOcrEngine(lang="eng")

    assert engine._preprocess is True


@_requires_ocr_libs
def test_tesseract_ocr_engine_still_recognizes_clean_text_with_preprocessing_enabled():
    # El preprocesamiento está activado por defecto (ver prueba
    # anterior) -- esta prueba confirma que no regresiona el caso ya
    # cubierto desde antes de esta ronda (texto limpio, alto contraste).
    engine = TesseractOcrEngine(lang="eng")
    image_bytes = _text_image_bytes("Hello OCR World")

    result = engine.image_to_text(image_bytes)

    assert "Hello" in result
    assert "OCR" in result
