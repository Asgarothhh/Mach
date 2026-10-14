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
Qdrant поднимается, но RAG остаётся in-memory stub. `ingestion` **не** обходит mts.by.

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

## 5. Модели (opt-in, не при compose up)

Compose demo profile остаётся **mock**. Live ASR/TTS — только host-процессы в conda env `mach` + extras. Веса **не** скачиваются при `compose up`. RAG — in-memory fixtures (`acme-it-demo` / `mts-public-demo`), не BGE-M3 и не Qdrant. LiveKit/SIP не настроены. T-one и Silero VAD качаются при **первой live-загрузке**, не при старте compose.

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

## 7. BLOCKED на этом стенде

* LiveKit и media token в `POST /sessions` (SSOT §9 / §15).
* SIP / МТС-транк — нет credentials.
* Crawler, Qdrant hybrid, embeddings, reranker (BGE-M3).
* `/admin/knowledge/*`, `/tenants`, `/calls`, scenarios, analytics — UI в demo/disabled.
* Chatterbox / Kokoro / Piper / Whisper как default cascade.
* Synthetic-demo LLM: `google/gemma-4-26b-a4b-it` via OpenRouter (allowlist always includes Gemma). `OPENROUTER_REQUIRE_ZDR` does not attach `zdr` for Gemma (no ZDR route). EXTERNAL_LLM_ALLOWED for real telephony remains false.

## 8. Следующий шаг

Self-hosted LiveKit в Compose, короткий media token, voice-agent как LiveKit worker. Не имитировать «телефонный продукт» до SIP credentials.
