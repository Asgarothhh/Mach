# Compose builds apps/api/Dockerfile for both api and voice_agent so speech
# weights are downloaded once. This file stays for standalone
# `docker build -f apps/voice_agent/Dockerfile` and stays in lockstep.
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update -o Acquire::Retries=5 && apt-get install -y --no-install-recommends \
        ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --retries 10 --timeout 120 --no-cache-dir -r requirements.txt
COPY requirements-rag.txt .
RUN pip install --retries 10 --timeout 120 --no-cache-dir -r requirements-rag.txt

RUN pip install --retries 10 --timeout 180 --no-cache-dir \
        torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements-speech.txt .
RUN pip install --retries 10 --timeout 180 --no-cache-dir -r requirements-speech.txt

COPY packages/contracts/knowledge ./packages/contracts/knowledge
COPY packages/rag ./packages/rag
RUN pip install --retries 10 --timeout 60 --no-cache-dir --no-deps ./packages/contracts/knowledge ./packages/rag

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
    VOICE_TTS_MODE=real \
    VOICE_AGENT_PORT=8100

COPY scripts/fetch_models.py scripts/prefetch_runtime_weights.py ./scripts/
RUN python scripts/fetch_models.py silero-tts-v5_cis_base_nostress --output-dir models/tts \
    && python scripts/fetch_models.py bge-m3-onnx --output-dir models/rag \
    && python scripts/fetch_models.py bge-m3-onnx-data --output-dir models/rag \
    && python scripts/fetch_models.py bge-m3-onnx-tokenizer --output-dir models/rag \
    && python scripts/prefetch_runtime_weights.py

COPY app/ ./app/
COPY speech/ ./speech/

EXPOSE 8100
CMD ["python", "-m", "app.voice_agent.worker"]
