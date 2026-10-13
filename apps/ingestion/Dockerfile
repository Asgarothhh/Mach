FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код ingestion
COPY apps/ingestion/ ./apps/ingestion/

CMD ["python", "-m", "apps.ingestion.main"]