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

## 5. Knowledge glue (Stage 0)

* **Knowledge admin endpoints and `knowledge_*` tables are BLOCKED.** Do not add `/admin/knowledge/*` or PostgreSQL knowledge/ingestion schema in this track. In-memory `mts_rag.InMemoryKnowledgeRetriever` is the only retrieval path.
* **`retrieval_events` is owned by Backend** (session-side SSOT §8.3). It stores revision, filters, candidate IDs/ranks/scores, cited IDs, duration and a SHA-256 of the *redacted* query. Raw query text and `query_variants` must never be logged or persisted.
* **Readiness:** `/health/ready` is 200 only when every demo tenant probe succeeds (`retriever=ok`). Postgres is reported (`ok`/`unavailable`) and does **not** block ready. OpenRouter is never checked. If retrieval fails at runtime the orchestrator returns `handoff` / `retrieval_unavailable`, never a grounded fact.
* **Text endpoint:** `POST /api/v1/sessions/{id}/turns/text` is Stage 0 text I/O justified by SSOT §15 (mock LLM, sources in the JSON body). `tenant_id` is bound at `POST /sessions` and rejected (422) if sent on the turn body.
* **Persistence is best-effort.** A store failure is logged with `error_class` only; the answer is still returned.
* **Switching demo tenants:** `POST /api/v1/sessions` with `tenant_id=acme-it-demo` (synthetic `.example` FAQ) or `tenant_id=mts-public-demo` (legacy `https://www.mts.by/help/` fixtures). Unknown tenants return 404 `tenant_not_available` without listing ids.