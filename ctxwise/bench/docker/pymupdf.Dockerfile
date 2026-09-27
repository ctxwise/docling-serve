# PyMuPDF4LLM with Tesseract (its default, English + Chinese installed) and RapidOCR
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pymupdf4llm==1.28.2 pymupdf==1.28.2 rapidocr==3.9.2 onnxruntime==1.30.0
