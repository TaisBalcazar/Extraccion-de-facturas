FROM python:3.12-slim

# ── Imagen de despliegue (Render) — Producto 1 (CarbonTrack UTPL) ──────────
# Este Dockerfile solo se usa para el build de Render, no para desarrollo
# local (local se corre directo desde .venv con requirements.txt completo).
#
# Usa requirements-deploy.txt, que excluye el fallback OCR (easyocr, cv2,
# pytesseract, torch...) porque EERSSA/Municipio de Loja emiten PDFs
# digitales, no escaneados. Debe desplegarse junto con DISABLE_OCR=true
# (variable de entorno en Render) — ver app/core/config.py y
# app/services/ocr_extractor.py.
#
# Para reactivar OCR en esta imagen (ej. si se retoman categorías con PDFs
# escaneados): cambiar requirements-deploy.txt → requirements.txt abajo, y
# restaurar los paquetes de sistema comentados.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    # tesseract-ocr tesseract-ocr-spa libgl1 libglib2.0-0  ← reactivar junto con OCR
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-deploy.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
