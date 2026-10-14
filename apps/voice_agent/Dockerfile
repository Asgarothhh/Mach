FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --retries 10 --timeout 60 --no-cache-dir -r requirements.txt

COPY packages/contracts/knowledge ./packages/contracts/knowledge
COPY packages/rag ./packages/rag
RUN pip install --retries 10 --timeout 60 --no-cache-dir --no-deps ./packages/contracts/knowledge ./packages/rag

COPY app/ ./app/
COPY speech/ ./speech/

ENV VOICE_ASR_MODE=mock \
    VOICE_TTS_MODE=mock \
    VOICE_AGENT_PORT=8100

EXPOSE 8100
CMD ["python", "-m", "app.voice_agent.worker"]
