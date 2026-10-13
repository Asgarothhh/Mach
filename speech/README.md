# `speech/` — речевой контур (ML, трек 1)

Локальные VAD / streaming ASR / streaming TTS адаптеры и контракты событий для
voice-каскада. Нормативные источники: [`docs/SPEC_MTS_VOICE_AGENT_TRACK1.md`](../docs/SPEC_MTS_VOICE_AGENT_TRACK1.md)
(§5.3–5.4, §5.7–5.8, §10, §14) и [`docs/DEV_PLAN_TRACK1.md`](../docs/DEV_PLAN_TRACK1.md) (§3, ML).

## Что уже есть

| Модуль | Назначение |
|---|---|
| `speech/contracts.py` | Типизированные контракты: `AudioFrame`, `VADEvent`, `ASREvent`, `TTSRequest`, `TTSChunk`, `CancellationToken`, протоколы `VADAdapter`/`ASRAdapter`/`TTSAdapter`, типизированные ошибки (`model_unavailable`, `timeout`, `invalid_audio`, `cancelled`, `synthesis_failed`). |
| `speech/audio.py` | PCM16 ↔ float32, нарезка аудио на транспортные чанки, длительности. |
| `speech/text_norm.py` | Консервативная нормализация текста для TTS: безопасные сокращения, управляющие символы, маркеры интонации вопросов `*слово*`. |
| `speech/revisions.py` | `TranscriptRevisionTracker` — поздний partial не перезаписывает final, дубликаты не создают новые ходы (SSOT §5.4). |
| `speech/vad/silero_vad.py` | Streaming VAD: Silero VAD (MIT) + собственный endpointing-автомат (`min_speech`, `min_silence`, `prefix_padding`, `max_utterance`, гистерезис). |
| `speech/tts/_streaming.py` | Общий streaming-цикл TTS: нормализация → препроцессор → движок → PCM-чанки с `chunk_id`/`generation_id` и отменой. |
| `speech/tts/silero_tts.py` | Silero v5: `v5_5_ru` (вопросы/ударения, NC — демо) и MIT-вариант `v5_cis_base_nostress` (`stress=True`). |
| `speech/tts/chatterbox_tts.py` | Chatterbox Multilingual V3 (MIT, ru, GPU, встроенный голос, PerTh watermark). |
| `speech/tts/kokoro_tts.py` | Kokoro-82M RU (OpenRAIL): sveta/masha/dima, CPU, автоударения через RUAccent (MIT). |
| `speech/tts/preprocess.py` | `TextPreprocessor` + `SileroStressPreprocessor` (silero-stress, MIT). |
| `speech/asr/mock.py` | Детерминированный mock ASR (interim→final) для E2E этапа 0–1. |
| `scripts/tts_ab_eval.py` | A/B-бенчмарк русских TTS: first-chunk, RTF, WER-прокси (Whisper round-trip), HTML-страница для команды. |

Манифест моделей и лицензий: [`config/models.lock.yaml`](../config/models.lock.yaml),
разбор лицензий и кандидатов: [`LICENSES.md`](../LICENSES.md).

## Лицензии голосов (кратко)

- **Silero `v5_5_ru` — CC BY-NC-SA 4.0**: только демо/оценка (эталон качества).
- **MIT-варианты:** Silero `v5_cis_base_nostress` + `silero-stress`; Chatterbox
  Multilingual V3 (встроенный голос); RUAccent/Kokoro G2P.
- **Kokoro-ru — OpenRAIL** (коммерческое использование допустимо с обычными
  use-restrictions RAIL).
- Подробности и сравнение — в `LICENSES.md`.

## Установка окружения

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[dev]" --python .venv/bin/python          # базовые + тесты
uv pip install -e ".[vad]" --python .venv/bin/python          # VAD (torch + silero-vad)
uv pip install -e ".[tts]" --python .venv/bin/python          # torch
uv pip install -e ".[tts-stress]" --python .venv/bin/python   # silero-stress (MIT)
uv pip install -e ".[tts-kokoro]" --python .venv/bin/python   # kokoro + ruaccent + misaki
uv pip install -e ".[eval]" --python .venv/bin/python         # faster-whisper (WER-прокси)
```

GPU-движки (Chatterbox) ставятся отдельно — пакет пинит `torch==2.6.0`, поэтому
в CI для него нужен отдельный venv, а на демо-машине с GPU это допустимо в
общем окружении:

```bash
uv pip install chatterbox-tts --python .venv/bin/python
```

## Тесты

```bash
.venv/bin/python -m pytest tests/speech -v                 # unit (без весов)
.venv/bin/python -m pytest tests/speech -m integration -v  # только с реальными весами
```

Unit-тесты не требуют ни torch, ни весов: адаптеры проверяются на
детерминированных фейковых движках (TTS/VAD), включая порядок чанков,
отмену, препроцессор ударений и типизированные ошибки.

## Модели

```bash
.venv/bin/python scripts/fetch_models.py --list
.venv/bin/python scripts/fetch_models.py silero-tts-v5_5_ru --output-dir models/tts
.venv/bin/python scripts/fetch_models.py silero-tts-v5_cis_base_nostress --output-dir models/tts
# вставить sha256 в config/models.lock.yaml (поле sha256)
```

Веса не коммитятся (`models/` в `.gitignore`). В production веса монтируются
как read-only volume (SSOT §12.1).

## A/B-сравнение TTS-движков

```bash
.venv/bin/python scripts/tts_ab_eval.py \
    --engines silero-v5,silero-mit-ru_dmitriy,chatterbox,kokoro-ru-sveta \
    --out artifacts/tts_ab \
    --html demo/vps-showcase/tts-ab.html
```

Скрипт пишет WAV-файлы и `report.json` (first-chunk, RTF, WER), а затем —
HTML-страницу для прослушивания командой. Фразы включают числа, телефон
`+375 …` и гомографы «за́мок/замо́к» для проверки автоударений.

## Интеграция с оркестратором (кратко)

1. Оркестратор создаёт `CancelToken` на ход и получает VAD-события из
   `VADAdapter.stream(...)`; на `SPEECH_START` во время `SPEAKING` — barge-in.
2. `ASREvent` прогоняются через `TranscriptRevisionTracker`; реагировать
   нужно только на события, которые он вернул (остальные — поздние partial).
3. `TTSChunk.generation_id` позволяет отбросить аудио отменённых поколений до
   воспроизведения; `is_first_chunk/first_chunk_ms` — для метрик TTFA.
4. Адаптеры отдают аудио в нативном sample rate (Silero: 8/24/48 кГц;
   Chatterbox и Kokoro: 24 кГц). Down-resampling для телефонии 8 кГц —
   задача медиа-слоя (LiveKit/SIP bridge).

## Что дальше (по плану ML)

- [x] Подбор коммерчески чистой замены силеро-TTS: MIT-связка CIS-base+stress, Chatterbox V3, Kokoro-ru; A/B-прогон и страница для команды.
- [ ] Streaming ASR: адаптер `sherpa-onnx` (T-One CTC RU / Zipformer RU) + baseline `faster-whisper` large-v3-turbo; WER/latency на своём наборе.
- [ ] Датасет ASR (≥200 utterances, синтетика/обезличенное) и метрики WER/CER по числам, суммам, датам.
- [ ] Калибровка порогов VAD на шум/паузы/перебивания; замер false positives/negatives.
- [ ] Пайплайн barge-in E2E (VAD → cancel → flush TTS) совместно с Backend + ML-Flow.
- [ ] Финальный выбор production-голоса по итогам прослушивания командой и license review.
