# `speech/` — речевой контур (ML, трек 1)

Локальные VAD / streaming ASR / streaming TTS адаптеры и контракты событий для
voice-каскада. Нормативные источники: [`docs/SPEC_MTS_VOICE_AGENT_TRACK1.md`](../docs/SPEC_MTS_VOICE_AGENT_TRACK1.md)
(§5.3–5.4, §5.7–5.8, §10, §14) и [`docs/DEV_PLAN_TRACK1.md`](../docs/DEV_PLAN_TRACK1.md) (§3, ML).

## Что уже есть

| Модуль | Назначение |
|---|---|
| `speech/contracts.py` | Типизированные контракты: `AudioFrame`, `VADEvent`, `ASREvent`, `TTSRequest`, `TTSChunk`, `CancellationToken`, протоколы `VADAdapter`/`ASRAdapter`/`TTSAdapter`, типизированные ошибки (`model_unavailable`, `timeout`, `invalid_audio`, `cancelled`, `synthesis_failed`). |
| `speech/audio.py` | PCM16 ↔ float32, нарезка аудио на транспортные чанки, длительности. |
| `speech/text_norm.py` | Консервативная нормализация текста для TTS: безопасные сокращения (`т.е.`, `руб.`), управляющие символы, маркеры интонации вопросов `*слово*`. Оригинал сохраняется отдельно. |
| `speech/revisions.py` | `TranscriptRevisionTracker` — поздний partial не перезаписывает final, дубликаты не создают новые ходы (SSOT §5.4, контракт с frontend). |
| `speech/vad/silero_vad.py` | Streaming VAD: Silero VAD (MIT) + собственный endpointing-автомат (`min_speech`, `min_silence`, `prefix_padding`, `max_utterance`, гистерезис). |
| `speech/tts/silero_tts.py` | Streaming TTS на Silero v5 (вопросы/ударения/омографы), чанки с `chunk_id`/`generation_id`, отмена, `first_chunk_ms`. |
| `speech/asr/mock.py` | Детерминированный mock ASR (interim→final) для E2E этапа 0–1. |

Манифест моделей и лицензий: [`config/models.lock.yaml`](../config/models.lock.yaml),
разбор лицензий: [`LICENSES.md`](../LICENSES.md).

## Лицензии (важно)

- **Silero TTS `v5_5_ru`/`v5_4_ru` — CC BY-NC-SA 4.0 (некоммерческая)**: только
  демостенд/внутренняя оценка. Для production нужна отдельная лицензия Silero
  либо MIT-модель `v5_cis_base_nostress` (`ru_*` голоса) с явной разметкой
  ударений. Подробности — в `LICENSES.md`.
- **Silero VAD — MIT**, разрешена.

## Установка окружения

```bash
# Python 3.11/3.12 (в проекте закреплён диапазон в pyproject.toml)
uv venv --python 3.12 .venv
uv pip install -e ".[dev]" --python .venv/bin/python        # базовые + тесты
uv pip install -e ".[vad]" --python .venv/bin/python        # VAD (torch + silero-vad)
uv pip install -e ".[tts]" --python .venv/bin/python        # TTS (torch, веса качаются отдельно)
```

## Тесты

```bash
.venv/bin/python -m pytest tests/speech -v                 # unit (без весов)
.venv/bin/python -m pytest tests/speech -m integration -v  # только с реальными весами
```

Unit-тесты не требуют ни torch, ни весов: VAD/TTS проверяются на
детерминированных фейковых моделях. Интеграционный тест TTS запустится после
загрузки весов (см. ниже).

## Модели

```bash
# скачать веса и получить SHA-256 для lock-файла
.venv/bin/python scripts/fetch_models.py --list
.venv/bin/python scripts/fetch_models.py silero-tts-v5_5_ru --output-dir models/tts
# вставить sha256 в config/models.lock.yaml (поле sha256)
```

Веса не коммитятся (`models/` в `.gitignore`). В production веса монтируются
как read-only volume (SSOT §12.1).

## TTS smoke / benchmark

```bash
.venv/bin/python scripts/tts_smoke.py \
    --model-path models/tts/v5_5_ru.pt \
    --sample-rate 8000 --out artifacts/tts
```

Скрипт пишет WAV-файлы по сегментам и печатает `first_chunk_ms`, полное время
синтеза и RTF — это измеряемая часть latency-бюджета SSOT §5.8. Для
телефонного тракта используйте `--sample-rate 8000`.

## Интеграция с оркестратором (кратко)

1. Оркестратор создаёт `CancelToken` на ход и получает VAD-события из
   `VADAdapter.stream(...)`; на `SPEECH_START` во время `SPEAKING` — barge-in.
2. `ASREvent` прогоняются через `TranscriptRevisionTracker`; реагировать
   нужно только на события, которые он вернул (остальные — поздние partial).
3. `TTSChunk.generation_id` позволяет отбросить аудио отменённых поколений до
   воспроизведения; `is_first_chunk/first_chunk_ms` — для метрик TTFA.

## Что дальше (по плану ML)

- [ ] Streaming ASR: адаптер `sherpa-onnx` (T-One CTC RU / Zipformer RU) + baseline `faster-whisper` large-v3-turbo; WER/latency benchmark на своём наборе.
- [ ] Датасет ASR (≥200 utterances, синтетика/обезличенное) и метрики WER/CER по числам, суммам, датам.
- [ ] Калибровка порогов VAD на шум/паузы/перебивания; замер false positives/negatives.
- [ ] Пайплайн barge-in E2E (VAD → cancel → flush TTS) совместно с Backend + ML-Flow.
- [ ] Подготовка phrase hints / словаря терминов tenant (после выбора ASR-движка).
- [ ] License review для production-голоса (см. `LICENSES.md`) и pin версий.
