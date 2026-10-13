# Задача для агента: Этап 1 — живой речевой каскад по test-каналу (+ barge-in)

**Статус:** ✅ выполнено (ML-часть + стык), смоук зелёный
**Дата:** 2026-10-13
**SSOT:** `docs/SPEC_MTS_VOICE_AGENT_TRACK1.md`; план — `docs/DEV_PLAN_TRACK1.md` (§2, «Этап 1»)
**Ветки:** ML-стек + стык — `audio` (не влита в main); Backend — `main` (API/оркестратор/RAG-заготовки уже влиты); Frontend — отдельная ветка (не в main).

> Итог реализации и runbook — в §8–§9 в конце документа.

---

## 1. Цель (критерий этапа)

Живой речевой каскад end-to-end по **тестовому каналу**:

```
wav-«звонок» → аудио в WebSocket → наш VAD (Silero) → наш ASR (T-one)
→ их оркестратор (guardrails → mock-retrieval → mock-LLM)
→ наш TTS (Silero MIT) → аудио назад клиенту
```

Плюс **barge-in**: речь пользователя во время ответа отменяет текущую генерацию и прекращает отправку аудио.

Это ровно критерий этапа 1: «пользователь может непрерывно говорить с ботом; перебивание корректно прекращает старый ответ». Доказательство — E2E-смоук на wav-«звонке» с логом событий.

**Вне scope этой задачи:** SIP/LiveKit/TelephonyAdapter, фронтенд, реальный телефонный ingress (нет в main), финальные роуты/консент — отдельные задачи.

---

## 2. Что уже есть

### Ветка `audio` (ML, готова, тесты 78 зелёные)
- `speech/contracts.py` — `AudioFrame`, `VADEvent`, `ASREvent`, `TTSRequest`, `TTSChunk`, `CancellationToken`, типизированные ошибки
- `speech/vad/silero_vad.py` — streaming-VAD с endpointing-автоматом
- `speech/asr/onnx_asr_adapter.py` — `OnnxAsrAdapter` (сегментный режим) поверх onnx-asr: T-one/GigaAM/Vosk; `preload_cuda_libraries()` для GPU
- `speech/tts/silero_tts.py` — TTS (v5.5 demo + MIT CIS-base со stress), `speech/tts/kokoro_tts.py`, `speech/tts/chatterbox_tts.py`
- `speech/text_norm.py` + `speech/number_norm.py` — числа/телефоны/УССД → слова (обязательно: Silero молча удаляет цифры!)
- `speech/revisions.py` — поздний partial не перезаписывает final
- Модели: `models/tts/v5_5_ru.pt`, `models/tts/v5_cis_base_nostress.pt`; venv `.venv` (uv)
- Скрипты-примеры: `scripts/asr_benchmark.py`, `scripts/tts_ab_eval.py`, тест-наборы `artifacts/asr_benchmark/`

### main (Backend)
- WS `app/api/main.py` → `/api/v1/ws/sessions/{session_id}`: принимает **только JSON** (`ASREvent`, `VADEvent`, `InterruptionEvent`); бинарного аудио нет
- `app/orchestrator/dialog_flow.py` — guardrails → `MockKnowledgeRetriever` → OpenRouter (mock-режим без ключа) → **моковые** TTS-чанки (`_create_mock_tts_chunk`)
- `app/orchestrator/state_machine.py` — `SessionState`, `TurnContext`, `handle_barge_in()`
- `app/voice_agent/worker.py` — stub 5 строк
- `docker-compose.yml`: api/ingestion/web/postgres/redis/qdrant/prometheus (livekit/voice-agent отсутствуют)

---

## 3. План работ

### Шаг 0. Интеграция веток
1. Смерджить `main → audio` (или новая ветка `stage1-e2e` от main + вливаем `audio`).
2. Разрешить конфликт `.gitignore` — **объединить** оба списка (в ML нужны `models/`, `artifacts/`).
3. В `pytest.ini` из main добавить `addopts = -p no:hydra_pytest` (питоновский плагин hydra 1.0.x из зависимостей silero падает на Python 3.12 и роняет весь pytest).
4. Установить бэкенд-зависимости из `requirements.txt` (sqlalchemy, asyncpg и пр.); для E2E поднять `docker compose up -d postgres` (dialog_flow пишет `Turn` в БД).

### Шаг 1. Аудио-канал в WS
В `app/api/main.py` расширить `websocket_endpoint`:
- принимать `websocket.receive_bytes()` наравне с текстом;
- **на сессию** держать: `SileroVADAdapter` (16 kHz, окно 512), `OnnxAsrAdapter` (модель `t-tech/t-one`, segment-режим на первом шаге);
- PCM→`AudioFrame` (`session_id`, `seq`, `timestamp_ms`) и гнать через VAD; на `SPEECH_END` — ASR сегмента;
- сгенерированный `ASREvent` подавать в существующую логику (как будто пришёл JSON `ASREvent`) — не плодить второй путь обработки.
- Partial-гипотезы (следующий шаг, не блокирует приёмку): нативные чанки T-one 300 мс через пакет `tone`.

### Шаг 2. Живой TTS вместо мока
В `dialog_flow.py` заменить `_create_mock_tts_chunk` на реальный `SileroTTSAdapter`:
- модель `v5_cis_base_nostress` + `stress=True`, голос `ru_bogdan` (24 кГц) — лучший MOS в наших тестах (43 мс первый чанк, RTF ~0.017);
- стримить чанки по мере синтеза; поле `generation_id` обязательно;
- протокол: либо base64-PCM в `TTSChunkEvent` (совместимо с текущим JSON-UI), либо бинарные кадры (лучше для аудио) — выбрать одно и записать в контракт.

### Шаг 3. Barge-in с отменой
- VAD `SPEECH_START` в состоянии `SPEAKING` → `session_manager.handle_barge_in(session_id)` + `CancellationToken.cancel()` для текущей TTS-генерации;
- TTS-генератор проверяет токен между чанками (`synthesize_segments` уже это делает) — поздние чанки не отправляются, очередь сбрасывается;
- переход `INTERRUPTED → LISTENING`; лог события `interruption`.

### Шаг 4. E2E-смоук
`scripts/stage1_e2e_smoke.py`:
1. `POST /api/v1/sessions` → `session_id`; открыть WS.
2. Отправить wav (~4–6 с, можно из `artifacts/asr_benchmark/audio/synthetic-telephony/synth_00_8k.wav`) чанками по ~100 мс (bytes).
3. Собрать: `ASREvent(is_final)` → чанки TTS → склеить ответ в WAV (проверить, что звучит).
4. На середине ответа отправить второй wav (перебивание) → проверить: чанки старого `generation_id` после `InterruptionEvent` не приходят, состояние `INTERRUPTED→LISTENING`, на новый ввод снова есть ответ.
5. Сохранить JSONL-лог событий как доказательство (сессии/ходы/латентности).

---

## 4. Контракты (сверить перед работой!)

| ML (`speech/contracts.py`) | main (`app/schemas/events.py`) | Действие |
|---|---|---|
| `ASREvent(session_id, turn_id, revision, text, is_final, language, confidence, start_ms, end_ms)` | одноимённый, поля могут отличаться | привести к ML-контракту, app-схема — адаптер |
| `VADEvent(type: speech_start/end, timestamp_ms, duration_ms, confidence, reason)` | `is_speech: bool` | маппинг на границе адаптера |
| `TTSChunk(..., generation_id, pcm_s16le, sample_rate, is_first_chunk, is_last_chunk, first_chunk_ms)` | `TTSChunkEvent` (мок, base64) | заменить содержимое на реальные чанки |

Источник истины по контрактам — SSOT §5.4/§5.7 (и `speech/contracts.py`). Если расхождение принципиальное — ADR, не менять молча.

---

## 5. Грабли, на которые мы уже наступили (не повторять)

1. **Silero ставит `torch.set_num_threads(1)`** на импорте И на каждом вызове — в `speech/tts/silero_tts.py` есть фикс (`_PREFERRED_THREADS`, восстановление в `finally`) — не сломать при интеграции (иначе всё замедляется в 3–4 раза).
2. **Silero молча удаляет символы вне своего набора** (цифр в наборе НЕТ): числа/телефоны/УССД обязаны проходить `normalize_for_tts`/`number_norm` (уже в пайплайне адаптеров).
3. **`number_norm` должен идти до стрипа `*`** у голосов без вопросной интонации (иначе `*111*4#` ломается) — так уже сделано.
4. **onnxruntime-gpu**: нужен `onnxruntime-gpu==1.22.*` (CUDA 12; 1.31 требует CUDA 13 и тихо падает на CPU) + `preload_cuda_libraries()` + `cudnn_conv_algo_search=EXHAUSTIVE`. T-one на GPU всё равно не работает (depthwise-conv) — CPU, это нормально (~0.06 RTF).
5. **faster-whisper на GPU**: тот же прелоад cuBLAS/cuDNN из torch (`speech/asr/onnx_asr_adapter.preload_cuda_libraries`).
6. CORS в main — `allow_origins=["*"]`, для демо ок, для прода — TODO (не наша задача).

---

## 6. Приёмка (DoD задачи) — ✅ выполнено

- [x] непрерывная реплика (wav) → корректный ASR-текст → реальный аудио-ответ (собранный WAV звучит):
      `artifacts/stage1_e2e/answer_2_*.wav` (1.84 с, Silero `ru_bogdan`)
- [x] перебивание во время ответа → старая генерация отменена (нет чанков после `InterruptionEvent`), состояние возвращается в `LISTENING`, следующий ввод обрабатывается:
      `answer_1_*.wav` — обрезан на 0.96 с (отмена в середине фразы)
- [x] JSONL-лог: VAD start/end, ASR final, TTS-чанки с `generation_id`, interruption, метки времени:
      `artifacts/stage1_e2e/events.jsonl`
- [x] тесты: вся сюита (540) зелёная, включая 4 новых на каскад (`tests/speech/test_cascade_junction.py`); `ruff` чистый по нашим файлам
- [x] README/RUNBOOK дополнены (см. §9); ограничение «mock-канал / mock-LLM, не SIP» указано

## 7. Полезные команды

```bash
# тесты ML
.venv/bin/python -m pytest tests/speech -q

# TTS-смоук (быстрая проверка голоса)
.venv/bin/python scripts/tts_ab_eval.py --engines silero-mit-ru_bogdan --no-wer --no-mos

# ASR-смоук на одном файле (T-one)
.venv/bin/python -c "
import onnx_asr, soundfile as sf
m = onnx_asr.load_model('t-tech/t-one')
audio, sr = sf.read('artifacts/asr_benchmark/audio/synthetic-telephony/synth_00_8k.wav', dtype='float32')
print(m.recognize(audio, sample_rate=sr))"
```

---

## 8. Результат: что реально сделано (2026-10-13)

### 8.1 Новые файлы (наша зона, ML + стык)

| Файл | Роль |
|---|---|
| `app/voice_agent/asr.py` | process-wide T-one через onnx-asr; env `ASR_MODEL`/`ASR_DEVICE` (по умолчанию CPU — на GPU depthwise-conv не поддержан) |
| `app/voice_agent/tts.py` | process-wide Silero `v5_cis_base_nostress` + `silero-stress`, голос `ru_bogdan`; env `TTS_MODEL_PATH`/`TTS_VOICE`/`TTS_SAMPLE_RATE` |
| `app/voice_agent/speech_cascade.py` | на сессию: PCM → VAD → сегмент → T-one → `ASREvent`; ретроспективный захват начала сегмента; watchdog-тишина, если канал замолчал посреди реплики |
| `app/orchestrator/tts_stream.py` | `TTSSentenceStreamer`: нарезка ответа LLM на фразы → чанки TTS с `generation_id`; отмена по `TurnContext.is_cancelled`; text-fallback при недоступной модели |
| `scripts/stage1_e2e_smoke.py` | E2E-«звонок»: wav → WS → каскад → оркестратор → TTS → аудио назад + barge-in-проверка; артефакты в `artifacts/stage1_e2e/` |
| `tests/speech/test_cascade_junction.py` | 4 юнит-теста каскада на фейках (захват, лаг VAD, watchdog, валидация) |

### 8.2 Правки в файлах бэкенда (минимальные, только точки стыка)

1. `app/schemas/events.py` — `TTSChunkEvent` дополнен **аддитивно**: `generation_id`, `sample_rate`, `first_chunk_ms`, `fallback_text` (старые поля не менялись).
2. `app/orchestrator/dialog_flow.py`:
   - мок-чанки заменены на реальный TTS через `TTSSentenceStreamer` (заблокированный ответ и ошибки LLM теперь отдают `fallback_text`, без фейкового аудио);
   - **исправлен баг**: `stream_final_asr` был объявлен **внутри `__init__`** (вложенная функция) — у класса такого метода не было, поэтому WS никогда не отвечал голосом; вынесен в метод класса.
3. `app/api/main.py` — `websocket_endpoint`:
   - бинарные кадры WS = **PCM16-LE mono 16 kHz** идут в `SpeechCascade` (текстовые JSON-события работают как раньше);
   - `SPEECH_START` во время `SPEAKING/GENERATING/RETRIEVING/ROUTING` → `handle_barge_in()` + отмена задачи генерации + `InterruptionEvent` клиенту;
   - `send_tts_stream` отдаёт чанки **в темпе воспроизведения** (эмуляция медиамоста: иначе ответ улетает мгновенно и перебить его невозможно);
   - явный `aclose()` генератора при отмене — убирает шум OTel «Failed to detach context» в логах на каждом barge-in.

### 8.3 Контракты (зафиксировано)

- **Аудио в WS:** binary frames, PCM16-LE mono, 16 kHz (чанки ~100 мс; поток может содержать тишину).
- **Аудио из WS:** JSON `TTSChunkEvent`, `audio_base64` = PCM16-LE, `sample_rate` (24 кГц Silero), `generation_id == turn_id`; завершение — `is_last_chunk=true`; при недоступном TTS — `fallback_text` вместо аудио; `text` — оригинальная (ненормализованная) фраза ответа (для UI/транскрипта, SSOT §5.7 про сохранение исходной формы).
- **VAD-контекст:** левый padding захвата 400 мс (VAD-онсет запаздывает на «Подс-»/фрикативах: с 96 мс T-one слышал «кдите» вместо «подскажите»).

### 8.4 Найденные проблемы их кода (зафиксировать у команды)

1. `stream_final_asr` был недоступным методом (см. выше) — их `smoke_test.py` не проверял TTS-события, поэтому баг не был виден.
2. `POST /api/v1/sessions` не пишет `Session` в БД, а `Turn` имеет FK на неё — смоук вставляет `Tenant`+`Session` вручную; правильное решение — в `create_session` (задача бэкенда).
3. Alembic: `versions/` пуст → таблиц нет; смоук делает `Base.metadata.create_all`.
4. `app/api/deps.py`: `DATABASE_URL` по умолчанию смотрит на compose-хост `postgres` — для локального прогона обязателен env-override (host-порт тестовой БД 55432).
5. OTel: при отмене генерации контекст `start_as_current_span` детачился в чужом контексте (шум в логах) — обошли явным `aclose()`.
6. Мок-LLM не следовал их же JSON-контракту (SSOT §6.8): отдавал простой текст, `dialog_flow` не находил `"answer_text"` и в конце произносил «Ошибка формата ответа». Теперь мок стримит валидный JSON-контракт (`answer_text`/`citation_ids`/`answer_status`) — на сайте слышен полноценный ответ.
7. Инкрементальный парсер `dialog_flow` озвучивал «небезопасный хвост» стрима: в речь попадало `", "citation_ids` до прихода закрывающего маркера. Добавлено отсечение хвоста длиной закрывающего маркера (17 символов) до его подтверждения.

### 8.5 Доказательства (артефакты)

- `artifacts/stage1_e2e/events.jsonl` — полный лог событий звонка (VAD, ASR, TTS с `generation_id`, interruption).
- `artifacts/stage1_e2e/answer_1_*.wav` — ответ, обрезанный barge-in (0.96 с).
- `artifacts/stage1_e2e/answer_2_*.wav` — полный голосовой ответ на перебившую фразу (1.84 с).
- Тесты: `.venv/bin/python -m pytest -q` → **540 passed** (вся сюита, включая 4 новых).
- Сверка с SSOT/планом и ревизия новых изменений main: `docs/ML_SPEC_AUDIT_STAGE1.md`.

## 9. RUNBOOK (как воспроизвести)

### 9.1 Тестовый сайт-консоль (демо для команды)

Открывается из браузера: **https://voice.194-146-38-78.sslip.io/**

- страница (микрофон → WS бинарное PCM16@16k, проигрыватель TTS-чанков, текст-режим,
  метрики TTFA/first_chunk_ms, журнал событий) живёт на демо-машине и отдаётся
  через VPS Caddy: `voice.194-146-38-78.sslip.io` → `/api/*` на `100.64.0.4:8123`
  (API, WS включён), остальное → `100.64.0.4:8124` (консоль);
- на демо-машине это user-юниты `voice-api.service` и `voice-console.service`
  (`systemctl --user status voice-api voice-console`), модели — локальные;
- проверка всего пути без браузера:
  `.venv/bin/python scripts/voice_console_check.py --url https://voice.194-146-38-78.sslip.io`;
- в консоли: «Начать звонок» → удерживай «🎤» (или включи непрерывный режим) → говори;
  заговори поверх ответа — сработает barge-in. **Наушники обязательны**, иначе эхо
  от колонок вернётся в микрофон и вызовет ложное перебивание (SSOT §5.3).
- «Отправить текстом» проверяет TTS-ветку без микрофона (JS-путь тот же, что у смоука).

### 9.2 Каскад напрямую (терминалы)

```bash
# 1) Тестовая БД (host-порт 55432; admin/123789, db=voice_agent)
docker start mach-e2e-postgres

# 2) API с нашим каскадом (обычно уже запущен юнитом voice-api)
cd /home/eq/techlb/Mach
ENVIRONMENT=demo \
DATABASE_URL=postgresql+asyncpg://admin:123789@127.0.0.1:55432/voice_agent \
  .venv/bin/python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8123

# 3) E2E-смоук (терминал 2)
DATABASE_URL=postgresql+asyncpg://admin:123789@127.0.0.1:55432/voice_agent \
  .venv/bin/python scripts/stage1_e2e_smoke.py

# 4) Тесты/линт
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check speech tests app/voice_agent app/orchestrator/tts_stream.py
```

Ожидаемый вывод смоука — `SMOKE PASSED: call -> ASR -> audio answer -> barge-in cancellation -> new answer`.

Env-переопределения ML-части: `ASR_MODEL`, `ASR_DEVICE`, `TTS_MODEL_PATH`, `TTS_VOICE`, `TTS_SAMPLE_RATE`.

## 10. Границы этапа и хвосты

- Partial-гипотезы ASR (нативные чанки T-one 300 мс, пакет `tone`) — следующий шаг, приёмку не блокируют.
- Качество T-one на отдельных словах («ассистент»→«сисчент») — модель; фолбэк/буст (GigaAM v3) — отдельная задача.
- Калибровка VAD на реальных звонках (шум/эхо/обрывы) — отдельная задача.
- Канал — test/mock: playback-pacing эмулирует медиамост; SIP/LiveKit/реальный ingress вне scope этапа.
- Локальные пакеты `packages/contracts/knowledge`, `packages/rag`, `apps/ingestion` поставлены в venv editable (`mts-contracts-knowledge`, `mts-rag`, `mts-ingestion`) — иначе их тесты не собираются.
- `pytest.ini`: `addopts = -p no:hydra_pytest` — оставлен (плагин hydra 1.0 падает на Python 3.12 и роняет весь pytest).
