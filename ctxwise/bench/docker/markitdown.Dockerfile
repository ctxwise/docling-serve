# MarkItDown with its OCR plugin (LLM-based)
FROM python:3.12-slim
RUN pip install --no-cache-dir "markitdown[all]==0.1.8" markitdown-ocr==0.1.1 openai pymupdf==1.28.2
