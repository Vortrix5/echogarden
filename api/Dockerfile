FROM python:3.11-slim

WORKDIR /app

# System dependencies: tesseract for OCR, ffmpeg for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=300 --retries=5 -r requirements.txt

# Pre-create model cache directory
RUN mkdir -p /data/models/whisper /data/models/openclip /data/models/sentence_transformers

COPY app/ app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
