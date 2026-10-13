# Задача для агента: Этап 1 — живой речевой каскад по test-каналу (+ barge-in)

**Статус:** спецификация задачи для исполнителя
**Дата:** 2026-10-13
**SSOT:** `docs/SPEC_MTS_VOICE_AGENT_TRACK1.md`; план — `docs/DEV_PLAN_TRACK1.md` (§2, «Этап 1»)
**Ветки:** ML-стек — `audio` (готова, не влита в main); Backend — `main` (API/оркестратор/RAG-заготовки уже влиты); Frontend — отдельная ветка (не в main).

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

## 6. Приёмка (DoD задачи)

- [ ] непрерывная реплика (wav) → корректный ASR-текст → реальный аудио-ответ (собранный WAV звучит)
- [ ] перебивание во время ответа → старая генерация отменена (нет чанков после `InterruptionEvent`), `INTERRUPTED → LISTENING`, следующий ввод обрабатывается
- [ ] JSONL-лог: VAD start/end, ASR final, TTS-чанки с `generation_id`, interruption, latency-метки
- [ ] тесты: наши 78 + новые (WS-парсинг аудио, отмена по barge-in); `ruff` чистый
- [ ] README/RUNBOOK дополнены; ограничение «mock-канал, не SIP» явно указано

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
