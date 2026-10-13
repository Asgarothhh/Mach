# MTS Voice Agent — Руководство по эксплуатации (Runbook)

Этот документ описывает процедуры развертывания, тестирования и обслуживания ИИ-агента для обработки входящих звонков. Инфраструктура настроена для запуска в изолированном демо-режиме.

## 1. Подготовка окружения

Перед первым запуском убедитесь, что у вас установлены:
* **Docker** и плагин **Docker Compose** (v2).
* **Python 3.11+** (для запуска локальных проверок и тестов).

Создайте файл переменных окружения:
```bash
cp .env.example .env
```
Убедитесь, что в `.env` указан правильный пароль для PostgreSQL (совпадающий с `docker-compose.yml`) и валидный API-ключ для OpenRouter (если планируете тестировать реальную LLM).

## 2. Запуск стенда

Поднимите все сервисы, используя профиль `demo` (включает API, PostgreSQL, Redis, Qdrant и Prometheus):

```bash
docker compose --profile demo up --build -d
```

**Что происходит под капотом:**
1. Поднимаются базы данных и кеш.
2. Контейнер `api` дожидается готовности PostgreSQL.
3. Автоматически накатываются миграции Alembic (создаются схемы и таблицы).
4. Запускается FastAPI-сервер на порту `8000`.

## 3. Проверка работоспособности

Проверьте логи API, чтобы убедиться в успешном старте:
```bash
docker compose logs -f api
```
*(Ожидаемое сообщение: `Application startup complete`)*.

### Сквозное E2E тестирование
Для проверки каскада (Session -> WebSocket -> RAG -> LLM -> TTS) запустите smoke-тест:
```bash
# Активируйте виртуальное окружение и установите зависимости
pip install -r requirements.txt
python scripts/smoke_test.py
```

### Запуск Unit-тестов
Проверка логики машины состояний и контроля доступа (RBAC):
```bash
python -m pytest tests/
```

## 4. Доступ к интерфейсам

* **Swagger UI (Документация API):** [http://localhost:8000/docs](http://localhost:8000/docs)
* **Prometheus (Метрики задержек):** [http://localhost:9090](http://localhost:9090)

## 5. Остановка и очистка данных

Обычная остановка контейнеров (данные в БД сохраняются):
```bash
docker compose --profile demo down
```

**Полный сброс (Hard Reset):**
Если необходимо очистить базу данных, вектора Qdrant и логи, удалите контейнеры вместе с томами (volumes):
```bash
docker compose --profile demo down -v
```

## 6. Резервное копирование и восстановление БД

Создание дампа базы данных сессий и транскриптов:
```bash
docker exec -t mach-postgres-1 pg_dump -U admin -d voice_agent -F c -f /tmp/backup.dump
docker cp mach-postgres-1:/tmp/backup.dump ./backup.dump
```

Восстановление из дампа:
```bash
docker cp ./backup.dump mach-postgres-1:/tmp/backup.dump
docker exec -i mach-postgres-1 pg_restore -U admin -d voice_agent -1 /tmp/backup.dump
```