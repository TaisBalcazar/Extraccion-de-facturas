"""
OCR para PDFs escaneados usando EasyOCR + PyMuPDF.

Flujo: pdfplumber → PyMuPDF nativo → EasyOCR → pytesseract.
"""

import logging

import fitz  # PyMuPDF
import numpy as np

logger = logging.getLogger(__name__)

_MIN_CHARS = 80  # Mínimo de caracteres significativos para considerar extracción exitosa

_reader = None  # Singleton EasyOCR


def _get_reader():
    """Inicializa EasyOCR una sola vez (descarga modelos en el primer uso)."""
    global _reader
    if _reader is None:
        import easyocr
        print("🔄 [OCR] Inicializando EasyOCR...")
        _reader = easyocr.Reader(["es", "en"], gpu=False, verbose=False)
        print("✅ [OCR] EasyOCR listo.")
    return _reader


def _texto_insuficiente(text: str) -> bool:
    """True si el texto extraído no tiene contenido significativo."""
    significativo = text.replace(" ", "").replace("\n", "").replace("\t", "").replace("\r", "")
    return len(significativo) < _MIN_CHARS


def _extract_text_pymupdf(file_content: bytes) -> str:
    """Extrae texto con PyMuPDF, que a veces recupera texto que pdfplumber pierde."""
    try:
        doc = fitz.open(stream=file_content, filetype="pdf")
        paginas = []
        try:
            for page in doc:
                paginas.append(page.get_text("text") or "")
        finally:
            doc.close()
        return "\n".join(paginas)
    except Exception as e:
        logger.warning(f"PyMuPDF text extraction falló: {e}")
        return ""


def _preprocess_image(img_array: np.ndarray) -> np.ndarray:
    """
    Preprocesa la imagen para mejorar la calidad del OCR.
    Aplica conversión a escala de grises, realce de contraste y denoising.
    """
    try:
        import cv2
        # Convertir a escala de grises
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        # CLAHE: realce de contraste adaptativo por regiones
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        # Denoising ligero
        denoised = cv2.fastNlMeansDenoising(enhanced, h=10)
        # Volver a RGB (EasyOCR acepta ambos formatos)
        return cv2.cvtColor(denoised, cv2.COLOR_GRAY2RGB)
    except Exception:
        return img_array  # Si falla, usar imagen original


def extract_text_with_ocr(file_content: bytes, dpi: int = 300) -> str:
    """
    Convierte cada página del PDF a imagen y aplica EasyOCR.

    Args:
        file_content: Bytes del PDF
        dpi: Resolución de renderizado (300 para mejor calidad en scans)

    Returns:
        Texto extraído por OCR de todas las páginas
    """
    reader = _get_reader()
    paginas = []

    try:
        doc = fitz.open(stream=file_content, filetype="pdf")
    except Exception as e:
        logger.error(f"PyMuPDF no pudo abrir el PDF: {e}")
        raise

    try:
        scale = dpi / 72.0  # 72 DPI es la resolución base de PDF
        matrix = fitz.Matrix(scale, scale)

        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB)

            # Convertir pixmap a array numpy (H, W, 3); .copy() para array escribible
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, 3
            ).copy()

            # Preprocesamiento para mejorar calidad en scans de baja calidad
            img_array = _preprocess_image(img_array)

            results = reader.readtext(img_array, detail=1, paragraph=False)

            # Ordenar de arriba a abajo, izquierda a derecha
            results.sort(key=lambda r: (r[0][0][1], r[0][0][0]))

            page_text = "\n".join(text for _, text, _ in results)
            paginas.append(page_text)

            logger.debug(f"Página {page_num + 1}: {len(page_text)} chars por OCR")
    finally:
        doc.close()

    return "\n".join(paginas)


def _extract_text_tesseract(file_content: bytes, dpi: int = 200) -> str:
    """
    Fallback OCR usando pytesseract (más liviano que EasyOCR).
    Requiere: pip install pytesseract  +  instalación de Tesseract en el sistema.
    """
    import pytesseract
    from PIL import Image
    import io as _io

    doc = fitz.open(stream=file_content, filetype="pdf")
    paginas = []
    try:
        scale = dpi / 72.0
        matrix = fitz.Matrix(scale, scale)
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB)
            img = Image.open(_io.BytesIO(pix.tobytes("png")))
            texto = pytesseract.image_to_string(img, lang="spa+eng")
            paginas.append(texto)
    finally:
        doc.close()
    return "\n".join(paginas)


def extract_text_smart(file_content: bytes, pdfplumber_text: str) -> tuple[str, bool]:
    """
    Devuelve texto con el mejor motor disponible:
    1. pdfplumber (ya extraído por el caller)
    2. PyMuPDF nativo (sin OCR)
    3. EasyOCR
    4. pytesseract

    Returns:
        (texto_final, ocr_fue_usado)
    """
    if not _texto_insuficiente(pdfplumber_text):
        return pdfplumber_text, False

    # Paso 2: PyMuPDF nativo — sin dependencias extra, a veces recupera texto
    # que pdfplumber pierde (distinto parser interno).
    pymupdf_text = _extract_text_pymupdf(file_content)
    if not _texto_insuficiente(pymupdf_text):
        logger.info("Texto suficiente con PyMuPDF nativo.")
        return pymupdf_text, False

    print("🔍 [OCR] PDF parece escaneado — aplicando OCR...")

    # Paso 3: EasyOCR
    try:
        ocr_text = extract_text_with_ocr(file_content)
        if not _texto_insuficiente(ocr_text):
            return ocr_text, True
        print(f"⚠️ [OCR] EasyOCR devolvió texto insuficiente ({len(ocr_text)} chars)")
    except ImportError as e:
        print(f"❌ [OCR] EasyOCR ImportError: {e}")
    except Exception as e:
        import traceback
        print(f"❌ [OCR] EasyOCR falló: {type(e).__name__}: {e}")
        print(traceback.format_exc())

    # Paso 4: pytesseract como último recurso
    try:
        tess_text = _extract_text_tesseract(file_content)
        if not _texto_insuficiente(tess_text):
            print("✅ [OCR] Texto extraído con pytesseract.")
            return tess_text, True
        print("⚠️ [OCR] pytesseract también devolvió texto insuficiente.")
        return tess_text, True
    except ImportError as e:
        print(f"❌ [OCR] pytesseract ImportError: {e}")
    except Exception as e:
        print(f"❌ [OCR] pytesseract falló: {type(e).__name__}: {e}")

    print("❌ [OCR] Todos los motores OCR fallaron, devolviendo texto original.")
    return pdfplumber_text, False
