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
RUN mkdir -p /data/models/whisper /data/models/openclip /data/models/sentence_transformers /data/models/blip

# Pre-download sentence-transformers model so it's cached in the image
# This avoids HuggingFace network calls at runtime
ENV SENTENCE_TRANSFORMERS_HOME=/data/models/sentence_transformers
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2', cache_folder='/data/models/sentence_transformers')" \
    || echo "WARN: pre-download failed — model will be loaded from bind mount at runtime"

# Pre-download BLIP captioning model
RUN python -c "from transformers import BlipProcessor, BlipForConditionalGeneration; BlipProcessor.from_pretrained('Salesforce/blip-image-captioning-base', cache_dir='/data/models/blip'); BlipForConditionalGeneration.from_pretrained('Salesforce/blip-image-captioning-base', cache_dir='/data/models/blip')" \
    || echo "WARN: BLIP pre-download failed — model will download at first use"

COPY app/ app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
