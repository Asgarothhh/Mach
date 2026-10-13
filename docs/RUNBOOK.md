# MTS Voice Agent - Operations Runbook[cite: 6]

## 1. Запуск и Остановка
* **Запуск демо-стенда:** `docker compose --profile demo up --build -d`
* **Остановка стенда:** `docker compose --profile demo down`
* **Просмотр логов API:** `docker compose logs -f api`

## 2. Восстановление БД
Если база данных повреждена, можно восстановить её из бэкапа:
1. Загрузите `.sql` файл на сервер.
2. Выполните восстановление: `cat backup.sql | docker exec -i mach-postgres-1 psql -U admin -d voice_agent`

## 3. Очистка данных
Для полной очистки демо-данных (ВНИМАНИЕ: удалит все volumes)[cite: 6]:
`docker compose --profile demo down -v`

## 4. Threat Model Summary (Угрозы и меры)[cite: 6]
* **Утечка PII в LLM:** Минимизируется через `guardrails.py` (маскирование) перед отправкой.
* **Prompt Injection (внедрение в базу знаний):** Предотвращается эвристикой в `check_retrieved_content`[cite: 6, 7].
* **DDoS / Спам запросами:** Смягчается с помощью Rate Limiting (SlowAPI).
* **Cross-Tenant утечки:** Исключаются благодаря жесткому фильтру `tenant_id` во всех ORM-запросах[cite: 7].