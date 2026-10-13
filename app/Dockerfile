FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей для сборки драйверов БД (если нужно)
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Копируем requirements (предполагается, что он у тебя есть)
# Если requirements.txt нет, создай его и добавь туда fastapi, uvicorn, sqlalchemy, alembic, psycopg2-binary, asyncpg
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код проекта, включая папку alembic и файлы миграций
COPY . .

# Команду CMD мы задали в docker-compose.yml, поэтому здесь ее можно опустить
# или оставить дефолтную для запуска без compose:
# CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]