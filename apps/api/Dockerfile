FROM python:3.12-slim
WORKDIR /app

RUN apt-get update -o Acquire::Retries=5 && apt-get install -y --no-install-recommends \
        ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --retries 10 --timeout 120 --no-cache-dir -r requirements.txt
COPY requirements-rag.txt .
RUN pip install --retries 10 --timeout 120 --no-cache-dir -r requirements-rag.txt

# CPU torch first so speech extras do not pull CUDA wheels.
RUN pip install --retries 10 --timeout 180 --no-cache-dir \
        torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements-speech.txt .
RUN pip install --retries 10 --timeout 180 --no-cache-dir -r requirements-speech.txt

COPY packages/contracts/knowledge ./packages/contracts/knowledge
COPY packages/rag ./packages/rag
RUN pip install --retries 10 --timeout 60 --no-cache-dir --no-deps ./packages/contracts/knowledge ./packages/rag

# Persist hub caches in the image layer (do not use cache mounts here).
ENV HF_HOME=/app/.cache/huggingface \
    HUGGINGFACE_HUB_CACHE=/app/.cache/huggingface/hub \
    TORCH_HOME=/app/.cache/torch \
    XDG_CACHE_HOME=/app/.cache \
    HOME=/app \
    ASR_MODEL=t-tech/t-one \
    ASR_DEVICE=cpu \
    TTS_MODEL_PATH=/app/models/tts/v5_cis_base_nostress.pt \
    TTS_VOICE=ru_bogdan \
    TTS_SAMPLE_RATE=24000 \
    VOICE_ASR_MODE=live \
    VOICE_TTS_MODE=real

COPY scripts/fetch_models.py scripts/prefetch_runtime_weights.py ./scripts/
RUN python scripts/fetch_models.py silero-tts-v5_cis_base_nostress --output-dir models/tts \
    && python scripts/fetch_models.py bge-m3-onnx --output-dir models/rag \
    && python scripts/fetch_models.py bge-m3-onnx-data --output-dir models/rag \
    && python scripts/fetch_models.py bge-m3-onnx-tokenizer --output-dir models/rag \
    && python scripts/prefetch_runtime_weights.py

COPY alembic.ini .
COPY migrations/ ./migrations/
COPY app/ ./app/
COPY speech/ ./speech/

EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
