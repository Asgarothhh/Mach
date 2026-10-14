# Показ жюри: развёртывание и эксплуатация

Одностраничник для стенда в день демо. Нормативный SSOT — [`SPEC_MTS_VOICE_AGENT_TRACK1.md`](SPEC_MTS_VOICE_AGENT_TRACK1.md). Полный runbook — [`runbook.md`](runbook.md). Сценарий речи — [`TECHNICAL_PITCH_PLAN.md`](TECHNICAL_PITCH_PLAN.md).

Это **Stage 1: browser/test-channel**. Не SIP, не транк МТС, не production-админка.

## 1. Что именно показываем

| Слой | Что работает на стенде | Чего нет |
|---|---|---|
| Речь | Локальный каскад VAD → ASR → TTS; barge-in | Телефония, LiveKit |
| Знания | Tenant-scoped RAG (Qdrant hybrid или sparse-only) по **5 demo-чанкам** | Crawler `mts.by` |
| Ответ | LLM только при `EvidenceStatus.SUFFICIENT`; иначе уточнение / отказ | «Ответ любой ценой» |
| LLM | OpenRouter `google/gemma-4-26b-a4b-it` или mock без ключа | Локальная LLM |
| Безопасность | Маскирование PII до LLM/БД, изоляция тенантов | Полноценный login в админку |
| UI | Текст, голос в браузере, сессии двух demo-tenant | Сценарии и мастер «Подключение» не меняют ассистента |

Два тенанта в шапке:

- **MTS public (demo)** → `mts-public-demo` (роуминг Турция, USSD баланс)
- **Acme IT (demo)** → `acme-it-demo` (график, прайс, почта поддержки)

## 2. Развёртывание перед показом

Нужны Docker Compose v2 и `.env` из `.env.example`. Обязательно: `ENVIRONMENT=demo`, пароль Postgres совпадает с `DATABASE_URL`. Для живых ответов Gemma — `OPENROUTER_API_KEY` (только в `.env`, не в git).

### 2.1. Стенд Compose (локально или на демо-машине)

После обновления кода **пересоберите web** — флаги Vite зашиваются на сборке:

```bash
cp .env.example .env   # если файла ещё нет; не затирайте рабочий ключ
docker compose --profile demo up --build -d
```

Сервисы: `postgres`, `redis`, `qdrant`, `prometheus`, `api`, `voice_agent`, `web`, `ingestion`.

`ingestion` не обходит сайт. Речь в compose по умолчанию **mock**. Живой голос — host-процессы, §2.3.

Остановка без удаления данных: `docker compose --profile demo down`. `down -v` стирает БД и индекс — только с явного разрешения.

### 2.2. Проверки (обязательно)

```bash
curl -sS http://localhost:8000/health/live
curl -sS http://localhost:8000/health/ready
# retriever=ok, knowledge.backend=qdrant, seed=ok для обоих tenant
# llm.provider = openrouter | mock; llm.model_id = google/gemma-4-26b-a4b-it

curl -sS http://localhost:8100/health/ready
# compose: asr/tts = mock; livekit = not_configured
```

Smoke-текст:

```bash
SID=$(curl -sS -X POST http://localhost:8000/api/v1/sessions \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"mts-public-demo","channel":"text","language":"ru"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')
curl -sS -X POST "http://localhost:8000/api/v1/sessions/$SID/turns/text" \
  -H 'Content-Type: application/json' \
  -d '{"text":"входящие звонки турции"}'
```

Ожидание: ответ про 1,50 руб. за входящие, есть источники. Если `retriever=unavailable` или `seed=failed` — не начинайте показ, см. §6.

UI: [http://localhost:3000](http://localhost:3000)  
Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)

Публичный стенд (VPS → Tailscale): UI `https://app.194-146-38-78.sslip.io`, голос `https://voice.194-146-38-78.sslip.io`. API живой речи на хосте `:8123`, не compose `:8000`. Перезапуск host: `systemctl --user restart voice-api voice-console`. После git pull пересоберите `web`:

```bash
docker compose --profile demo up -d --build web
```

За прокси uvicorn нужен `--proxy-headers --forwarded-allow-ips=<адрес Caddy>`. Иначе лимит 10/60 запросов в минуту общий на IP прокси.

### 2.3. Живой голос (opt-in, не compose)

Compose `api`/`voice_agent` занимают `:8000`/`:8100`. Для live: `docker compose --profile demo stop api voice_agent` (**не** `down -v`), Postgres/Qdrant/Redis оставить. Дальше — [`runbook.md`](runbook.md) §5–§6 (conda `mach`, T-one + Silero `ru_bogdan`).

Проверка: `:8000/health/ready` → `voice=live`; `:8100/health/ready` → `asr=ok`, `tts=ok`. Баннер «не телефония» про SIP, не про mock ASR.

Dense RAG (не обязателен для показа): `scripts/fetch_models.py bge-m3-onnx`. Без весов стенд остаётся sparse-only — для demo-чанков этого достаточно.

## 3. За 10 минут до жюри

1. Health live/ready зелёные, seed `ok`.
2. Открыть UI, выбрать **MTS**, спросить «сколько стоят входящие в Турции» — есть ответ и источник.
3. Переключить на **Acme**, спросить «график работы офиса» — ответ про Пн–Пт 9–18, **без** Турции.
4. Микрофон разрешён в браузере заранее. Наушники, не колонки (иначе barge-in ловит TTS).
5. Закрыть лишние вкладки. Не открывать «Сценарии» и «Подключение» как рабочий контур.
6. Если ключа OpenRouter нет — ответы mock, короче и шаблоннее. Сказать жюри заранее: «на этом стенде LLM-mock».

## 4. Сценарий показа (3–4 минуты)

Держать UI на **MTS**. Текст надёжнее голоса, если зал шумный; голос — если каскад live.

1. **Входящий контакт, не «бот на всё».** Шапка: тенант MTS. «Первый контакт, ответ только по базе компании».
2. **Есть факт → ответ с источником.** «Сколько стоят входящие звонки в Турции?» → 1,50 руб./мин, исходящие 3 руб. Показать блок источников, не example.com.
3. **Нет факта → не выдумывает.** «А в Египте?» или «какой у меня баланс на номере?» → уточнение / нет в данных, не тариф.
4. **Изоляция компаний.** Переключить шапку на **Acme**. «График работы офиса?» → Пн–Пт 9–18. «А исходящие в Турции?» не должно отвечать про МТС.
5. **Безопасность.** В Acme: «позвоните мне на 8 029 123-45-67, почта ivan@mail.ru» — в ответе и в админке `[PHONE_REDACTED]` / `[EMAIL_REDACTED]`, не сырой номер. *100# не маскируется (это USSD из базы).
6. **Barge-in** (если live-голос). Начать ответ, перебить голосом. Агент замолкает, слушает снова. Не колонки.
7. **Админка.** `/admin` → «Сессии» / «Обзор»: видна только что созданная сессия выбранного тенанта, статус не вечный `CREATED` после «Завершить».

Текстовый режим: [http://localhost:3000/text](http://localhost:3000/text), Enter отправляет. «Очистить диалог» сбрасывает серверный контекст.

### Рабочие реплики

| Тенант | Спрашивать | Ожидание |
|---|---|---|
| MTS | входящие в Турции / роуминг Турция | 1,50 / 3 руб., источник help/roaming |
| MTS | как проверить баланс | USSD `*100#` |
| MTS | роуминг в Египте | нет в данных / уточнение |
| Acme | график работы офиса | Пн–Пт 9–18 |
| Acme | сколько стоит лицензия | 99 руб./мес |
| Acme | как связаться с поддержкой | `support@acme-it.example` |
| Acme | нет, я имел в виду телефон поддержки | нет телефона в данных, предложить почту |

Не спрашивать: личные тарифы абонента, паспорт, карты, «подключите мне услугу».

## 5. Что говорить и чего не говорить

Говорить:

- каскад речи локально; ответ evidence-first;
- нет подтверждения — нет уверенного ответа;
- данные компании изолированы; PII маскируется до внешней модели;
- это Stage 1, browser test channel.

Не говорить:

- «полностью локальная LLM»;
- «RAG без ошибок» / «весь mts.by в индексе»;
- «уже SIP / телефония МТС»;
- «гарантированные 300–400 мс»;
- «все персональные данные удаляются» (маскируются детерминированные шаблоны; сказанные словами номера — известный пробел).

Если спросят про LLM: «Gemma через OpenRouter; аудио и ASR/TTS локально; во внешнюю модель уходит уже маскированный текст».

## 6. Если сломалось во время показа

| Симптом | Что сделать |
|---|---|
| `health/ready` 503, retriever unavailable | Qdrant: `docker compose --profile demo ps qdrant`. Не «переключаемся на stub» — при заданном `QDRANT_URL` stub запрещён |
| seed failed / пустые ответы | `docker compose --profile demo logs api --tail=80`. Перезапуск `api` (seed с backoff) |
| UI есть, API 401 на админке | В `.env` нет `ENVIRONMENT=demo`. Не чинить при жюри — показать текст |
| 429 в чате | Подождать ~1 мин или «Очистить диалог» (новый session_id). За прокси проверить proxy-headers |
| Смешались тенанты | Переключить шапку ещё раз; очистить диалог. Не продолжать в старой сессии |
| Голос «распознаётся» / тишина | Вернуться в `/text`. Сказать: текстовый канал тот же оркестратор и RAG |
| Gemma/OpenRouter 5xx | Показ на mock или заранее заготовленный скрин. Не обещать «сейчас починим ключ» |
| Жюри про сценарии / SIP / Подключение | «На стенде это UI-контур; ассистент их не исполняет. SIP — следующий интеграционный шаг» |

Не делать при жюри: `docker compose down -v`, `git reset`, качать 2 ГБ BGE-M3, править `.env` с ключом на проекторе.

## 7. После показа

```bash
docker compose --profile demo down          # данные volumes сохраняются
# docker compose --profile demo down -v    # только если можно стереть демо-БД
```

Host-стенд: `systemctl --user stop voice-api voice-console` при необходимости. Ключ OpenRouter не светить в логах, записи экрана и админке.
