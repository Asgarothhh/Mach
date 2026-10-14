# MTS Voice Agent — Руководство по эксплуатации (Runbook)

Нормативный SSOT: [`SPEC_MTS_VOICE_AGENT_TRACK1.md`](SPEC_MTS_VOICE_AGENT_TRACK1.md) v1.1.
Речевой каскад (WS PCM): [`STAGE1_SPEECH_E2E.md`](STAGE1_SPEECH_E2E.md).

Инфраструктура ниже — **демо-стенд Этапа 1**, не доказательство SIP/МТС-транка.

## 1. Подготовка

Нужны Docker Compose v2, Python 3.12 (conda env `mach`) и Node.js 22+ для локальной сборки frontend.

```bash
cp .env.example .env
# Заполните POSTGRES_PASSWORD (совпадает с DATABASE_URL) и при желании OPENROUTER_API_KEY.
```

Существующий volume `pg_data` применяет пароль Postgres **только при первом создании**. Смена пароля без `docker compose down -v` не сработает; `down -v` удаляет демо-данные и требует явного разрешения.

## 2. Запуск стенда (CPU, mock ASR/TTS)

```bash
docker compose --profile demo up --build -d
```

Сервисы: `postgres`, `redis`, `qdrant`, `prometheus`, `api`, `voice_agent`, `web`, `ingestion`.
Compose задаёт `QDRANT_URL=http://qdrant:6333` для `api` — после seed RAG работает как hybrid
(или sparse-only без весов BGE-M3). Юнит-тесты снимают `QDRANT_URL` и остаются на lexical stub.
`ingestion` **не** обходит mts.by.

Переменные речи по умолчанию: `VOICE_ASR_MODE=mock`, `VOICE_TTS_MODE=mock`. Веса моделей **не** скачиваются при `up`.

Остановка без удаления данных:

```bash
docker compose --profile demo down
```

## 3. Проверки

```bash
curl -sS http://localhost:8000/health/live
curl -sS http://localhost:8000/health/ready   # retriever обязателен; OpenRouter нет
curl -sS http://localhost:8100/health/live
curl -sS http://localhost:8100/health/ready   # asr/tts = mock; livekit = not_configured
```

Текстовый путь (оба demo-tenant):

```bash
# acme-it-demo
SID=$(curl -sS -X POST http://localhost:8000/api/v1/sessions \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"acme-it-demo","channel":"text","language":"ru"}' | python -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')
curl -sS -X POST "http://localhost:8000/api/v1/sessions/$SID/turns/text" \
  -H 'Content-Type: application/json' \
  -d '{"text":"график работы офис acme"}'

# mts-public-demo
SID=$(curl -sS -X POST http://localhost:8000/api/v1/sessions \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"mts-public-demo","channel":"text","language":"ru"}' | python -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')
curl -sS -X POST "http://localhost:8000/api/v1/sessions/$SID/turns/text" \
  -H 'Content-Type: application/json' \
  -d '{"text":"входящие звонки турции"}'
```

Локальные тесты:

```bash
conda run -n mach python -m pytest tests/ -m "not integration"
conda run -n mach pytest -q packages/rag
conda run -n mach pytest -q apps/ingestion
cd apps/web && npm ci && npm run check
```

Smoke API: `python scripts/smoke_test.py` (нужен поднятый API).

## 4. UI

Показ жюри (чеклист, сценарий, что не заявлять): [`JURY_DEMO.md`](JURY_DEMO.md).

* Frontend compose: [http://localhost:3000](http://localhost:3000) (`VITE_DEMO_MODE=false`, текстовый режим ходит в `/turns/text`).
* Локальный Vite: `cd apps/web && cp .env.example .env &&` выставьте `VITE_DEMO_MODE=false`, `VITE_BACKEND_TEXT_TEST=true`, затем `npm run dev` → [http://localhost:5173](http://localhost:5173).
* Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)
* Voice-agent health: [http://localhost:8100/health/ready](http://localhost:8100/health/ready)

### Demo UI vs live API

| Режим | Как включить | Что видно |
|---|---|---|
| Demo fixtures | `VITE_DEMO_MODE=true` | Баннер «Демо», синтетические звонки/знания |
| Live API | `VITE_DEMO_MODE=false` (+ `VITE_BACKEND_TEXT_TEST=true` для compose-сборки) | Реальные `POST /sessions` и `/turns/text` |

Переключатель tenant в шапке: **Acme IT (demo)** = `acme-it-demo`, **MTS public (demo)** = `mts-public-demo`. Это UI-выбор, не авторизация.

Голос: баннер **«Browser test channel / mock — не телефония»**. PCM16 идёт на `WS /api/v1/ws/sessions/{id}`. LiveKit не поднят (`VITE_LIVEKIT_URL` пуст).

### Публичный демо-стенд (VPS Caddy → Tailscale → демо-машина)

Вычисления идут на демо-машине (Tailscale `100.64.0.4`), VPS (`kametera`, `194.146.38.78`) только проксирует; сертификаты — Let's Encrypt (sslip.io). Caddyfile — `/etc/caddy/Caddyfile` (бэкапы рядом).

| Домен | Куда проксируется | Что это |
|---|---|---|
| `app.194-146-38-78.sslip.io` | `/api/*`, `/health/*`, `/openapi.json` → `:8123`; остальное → `:3000` | UI из compose-стека (`mach-web-1`), API — host-стенд с живой речью |
| `voice.194-146-38-78.sslip.io` | `/api/*` → `:8123`; остальное → `:8124` | Тестовый голосовой канал (PC PCM16 → WS) |
| `tts.194-146-38-78.sslip.io` | → `:8077` | TTS-полигон |
| `mach.194-146-38-78.sslip.io` | статика `/srv/mach-demo` | ML-страницы (A/B, ASR-бенчмарк, маскот-эмоции) |

Host-процессы — systemd user-юниты: `voice-api` (`:8123`, live overrides в `~/.config/mach/host-stand.env` через drop-in), `voice-console` (`:8124`), `tts-playground` (`:8077`). БД — контейнер `mach-e2e-postgres` (host `:55432`). Перезапуск: `systemctl --user restart voice-api voice-console`.

UI на домене — контейнер `web` из compose-стека (`:3000`), публичный API-base задан в `docker-compose.override.yml` (локальный файл, в main его нет):

```bash
docker compose --profile demo up -d --build web
```

Тот же override добавляет рабочий healthcheck для qdrant: в образе `qdrant/qdrant` нет `wget`, поэтому проверка из main (`wget -qO- .../healthz`) не может пройти, и контейнер вечно «unhealthy». Override проверяет тот же эндпоинт через `bash` + `/dev/tcp`.

## 5. Модели (opt-in, не при compose up)

Compose demo profile остаётся **mock** для речи. Live ASR/TTS — только host-процессы в conda env `mach` + extras. Веса **не** скачиваются при `compose up`. RAG: Qdrant v1.7.4 + seed demo-чанков; dense BGE-M3 только если `models/rag/bge-m3-onnx` смонтирован. LiveKit/SIP не настроены. T-one и Silero VAD качаются при **первой live-загрузке**, не при старте compose.

```bash
# CPU torch first so extras do not pull CUDA
conda run -n mach pip install torch --index-url https://download.pytorch.org/whl/cpu
conda run -n mach pip install -e ".[vad,asr,tts,tts-stress]"
conda run -n mach pip install soxr soundfile
conda run -n mach python scripts/fetch_models.py silero-tts-v5_cis_base_nostress --output-dir models/tts
conda run -n mach python scripts/fetch_asr_testset.py --synthetic-only --out artifacts/asr_benchmark
```

Default live TTS — MIT shortlist Silero `v5_cis_base_nostress` / `ru_bogdan`. Голоса Silero `v5_5_ru` (CC BY-NC-SA) **не** default demo.

## 6. Live каскад на хосте (conda `mach`)

Compose `api`/`voice_agent` занимают `:8000`/`:8100` — остановите их (`docker compose --profile demo stop api voice_agent`), **не** `down -v`. Postgres (и redis) оставьте.

Миграции с хоста (override, чтобы `load_dotenv` не подставил hostname `postgres`):

```bash
SYNC_DATABASE_URL=postgresql+psycopg2://admin:123789@127.0.0.1:5433/voice_agent \
  conda run -n mach alembic upgrade head
```

Затем два процесса с live overlay (не меняйте compose defaults; `DATABASE_URL` в `.env` для compose остаётся `@postgres`):

```bash
LIVE_ENV="VOICE_ASR_MODE=live VOICE_TTS_MODE=real ASR_MODEL=t-tech/t-one ASR_DEVICE=cpu \
TTS_MODEL_PATH=models/tts/v5_cis_base_nostress.pt TTS_VOICE=ru_bogdan TTS_SAMPLE_RATE=24000 \
DATABASE_URL=postgresql+asyncpg://admin:123789@127.0.0.1:5433/voice_agent \
SYNC_DATABASE_URL=postgresql+psycopg2://admin:123789@127.0.0.1:5433/voice_agent"

conda run -n mach env $LIVE_ENV uvicorn app.api.main:app --host 127.0.0.1 --port 8000
conda run -n mach env $LIVE_ENV VOICE_AGENT_HOST=127.0.0.1 VOICE_AGENT_PORT=8100 python -m app.voice_agent.worker
```

Проверки: `:8000/health/ready` → `voice=live`, retriever/postgres `ok`; `:8100/health/ready` → `asr=ok`, `tts=ok` (не mock), `livekit=not_configured`.

PCM smoke (wav не должны совпадать с `VOICE_MOCK_ASR_TEXT`):

```bash
DATABASE_URL=postgresql+asyncpg://admin:123789@127.0.0.1:5433/voice_agent \
  conda run -n mach python scripts/stage1_e2e_smoke.py --api http://127.0.0.1:8000
```

Frontend (Vite): `VITE_DEMO_MODE=false VITE_BACKEND_TEXT_TEST=true VITE_API_BASE_URL=http://localhost:8000/api/v1 VITE_LIVEKIT_URL= npm run dev`. Баннер «Browser test channel / mock — не телефония» означает отсутствие SIP, не mock ASR.

## 7. Qdrant hybrid RAG

По умолчанию compose поднимает Qdrant `v1.7.4` на `127.0.0.1:6333` и передаёт в `api`:

* `QDRANT_URL=${QDRANT_URL:-http://qdrant:6333}`
* `EMBEDDING_MODEL_ID=${EMBEDDING_MODEL_ID:-bge-m3-onnx}`
* `RERANKER_MODEL_ID=${RERANKER_MODEL_ID:-none}`

Без `QDRANT_URL` (локальный uvicorn / pytest) остаётся lexical stub.

```bash
docker compose --profile demo up -d qdrant
curl -sS http://127.0.0.1:6333/   # version >= 1.7.0
docker compose --profile demo up --build -d api
curl -sS http://localhost:8000/health/ready
# checks.knowledge.backend=qdrant; seed=ok|pending|failed; retriever=ok только если
# у обоих demo-tenant alias резолвится и count>0. Embedding на /health не вызывается.
```

Seed (фон, backoff 1s→30s) публикует `acme-it-demo` и `mts-public-demo` в коллекции
`kb__{tenant}__{DEMO_INDEX_REVISION}.{fp12}` и атомарно ставит alias `…__active`.
Повторный старт с тем же fingerprint — upsert тех же point id, без delete.

Веса BGE-M3 **не** скачиваются. Чтобы включить dense:

```bash
# записи есть в scripts/fetch_models.py — запускайте явно, не из compose up
conda run -n mach python scripts/fetch_models.py bge-m3-onnx --output-dir models/rag
conda run -n mach python scripts/fetch_models.py bge-m3-onnx-tokenizer --output-dir models/rag
```

Нужны `models/rag/bge-m3-onnx/model.onnx` и `tokenizer.json`. Иначе retrieve деградирует в
`SPARSE_ONLY` + `EMBEDDER_UNAVAILABLE`. Если Qdrant недоступен при заданном `QDRANT_URL`,
stub **не** подключается: `RetrievalUnavailable`, ready 503.

Кэш retrieve: при `REDIS_URL` — Redis, иначе in-memory; ключ — hash запроса, в значении нет
сырого query. `excluded_counts` считается по scroll коллекции. Старые ревизии сверх
`keep_revisions=2` удаляются. Пороги demo: `config/eval_thresholds.yaml`. Crawler по-прежнему
нет: seed только demo-фикстур. Если Qdrant недоступен при заданном `QDRANT_URL`, stub не
подключается.

Подробности: `packages/rag/README.md`, `docs/adr/ADR-0002-qdrant-hybrid-retrieval.md`.

## 8. BLOCKED на этом стенде

* LiveKit и media token в `POST /sessions` (SSOT §9 / §15).
* SIP / МТС-транк — **BLOCKED**. Нет credentials; мастер подключения не предлагает живой SIP и не создаёт SIP-сессию.
* Crawler live URL (ingestion worker всё ещё stub). Production-калибровка порогов RAG.
* Полная аутентификация админки — нет. При `ENVIRONMENT=demo` (см. `.env.example`) `GET /api/v1/admin/sessions*` выдаёт demo-principal, ограниченный `acme-it-demo` и `mts-public-demo`. Иначе 401. Caddyfile живёт вне репозитория (`/etc/caddy/Caddyfile` на VPS); в репозиторий его не добавляем.
* `/admin/knowledge/*`, `/tenants`, `/calls`, scenarios, analytics — UI в demo/disabled. В публичной сборке (`VITE_DEMO_MODE=false`) экраны «Подключение» и «Сценарии» при 404 на `/tenants*` деградируют на локальные фикстуры (`src/shared/api/stage1Fallback.ts`). Профили мастера и сценарии сохраняются **только в браузере** и не влияют на ответы помощника. Созданные так тенанты не попадают в переключатель; живые сессии всегда идут с бэкенд-тенантом (`acme-it-demo` / `mts-public-demo`, `resolveSessionTenantId`).
* Админ-мониторинг сессий работает для двух demo-tenant при `ENVIRONMENT=demo`. Tenant isolation — FR-09; чужой `tenant_id` в query → 403, чужая сессия в detail → 404.
* Rate limit (`text_turn` 20/мин на сессию и 60/мин на IP, `create_session` 10/мин на IP) использует `X-Forwarded-For`. За прокси запускайте `uvicorn --proxy-headers --forwarded-allow-ips=<адрес Caddy или 127.0.0.1>`. Без этих флагов лимит привязывается к адресу прокси, а не клиента.
* Chatterbox / Kokoro / Piper / Whisper как default cascade.
* Synthetic-demo LLM: `google/gemma-4-26b-a4b-it` via OpenRouter (allowlist always includes Gemma). `OPENROUTER_REQUIRE_ZDR` does not attach `zdr` for Gemma (no ZDR route). EXTERNAL_LLM_ALLOWED for real telephony remains false.

## 9. Следующий шаг

Self-hosted LiveKit в Compose, короткий media token, voice-agent как LiveKit worker. Не имитировать «телефонный продукт» до SIP credentials.
