FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем общие пакеты и код воркера
COPY app/ ./app/

# Воркер не слушает HTTP порты, он подключается к брокеру/LiveKit
CMD ["python", "-m", "app.voice_agent.worker"]