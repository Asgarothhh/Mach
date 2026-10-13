FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY packages/contracts/knowledge ./packages/contracts/knowledge
COPY packages/rag ./packages/rag
RUN pip install --no-cache-dir --no-deps ./packages/contracts/knowledge ./packages/rag

# Копируем конфигурацию и скрипты миграций
COPY alembic.ini .
COPY migrations/ ./migrations/

# Копируем код приложения
COPY app/ ./app/

EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
