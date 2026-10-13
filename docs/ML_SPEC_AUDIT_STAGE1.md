# Аудит: ML-часть и стык против SSOT (Этап 1)

**Дата:** 2026-10-13
**Область:** `speech/` (VAD/ASR/TTS), каскад `app/voice_agent/`, стык (`app/orchestrator/tts_stream.py`,
правки точек стыка в `app/api/main.py`, `app/orchestrator/dialog_flow.py`, `app/schemas/events.py`),
тестовый канал (смоук + веб-консоль).
**Источники требований:** `docs/SPEC_MTS_VOICE_AGENT_TRACK1.md` (v1.1), `docs/DEV_PLAN_TRACK1.md` §3 (ML).
**Проверяемые состояния:** ветка `audio` (наша, `8fa99c1` + правки консоли), `origin/main` (после `e0ca093`).

---

## 1. Резюме

Реализованное ядро (VAD → T-one → оркестратор → Silero TTS, barge-in, деградация, тесты)
**соответствует** контрактам SSOT §5.3–5.7, §10, §14 и чек-листу ML-плана по большинству пунктов;
E2E подтверждён на стенде и через публичную консоль.

Главные расхождения, требующие решения (детали в §2–3):

1. **FR-03 MUST — interim-гипотезы ASR не публикуются.** Каскад отдаёт только `final` по VAD-endpoint.
   Контракт (`ASREvent.revision`, `revisions.py`) готов, но partial-поток T-one (300 мс чанки, пакет `tone`) — не реализован.
2. **§11.4 WER-ориентир:** T-one на нашем наборе 14.7% (ориентир «чистая речь ≤ 12%»), GigaAM v3 — 9.2%,
   но не стриминговый. Нужен либо ADR-выбор (качество vs стриминг), либо улучшение (LM/домены).
3. **§10/§5.8 — нет watchdog на первый чанк TTS (500 мс) и таймаута на `recognize`** (ASR считается в `to_thread`
   без `wait_for`); деградация срабатывает по исключению, а не по времени.
4. **Реестр версий неполный:** `config/models.lock.yaml` содержит записи, но у большинства `sha256: null`,
   у `silero-vad` пин «TODO»; ASR-кандидаты (t-one/gigaam) в статусе `benchmark`, а не `approved-dev`.
5. **p50/p95-гарнесс по этапам** (VAD/ASR/first chunk) не выделен: есть `first_chunk_ms` в чанках,
   TTFA в смоуке/консоли и RTF в бенчмарке, но не регулярные процентные метрики.
6. **Метрики в Prometheus** для ML-этапов не экспортируются (TTFA/first_chunk_ms живут в событиях и логах).

---

## 2. Соответствие по пунктам (ML и стык)

| Требование | Статус | Доказательство | Расхождение / действие |
|---|---|---|---|
| FR-02 входящий вызов за `TelephonyAdapter`; mock-канал допустим и помечен | ✅ (наш вклад) | WS-канал = mock/test adapter; на сайте и в доке явно «синтетический канал, не SIP» | SIP/VoIP — зона backend; интерфейс адаптера — за нами позже |
| FR-03 потоковый разговор: ASR interim/final, TTS по мере готовности, перебивание | ⚠️ частично | final-ASR + потоковый TTS (фразы) + barge-in: 0 чанков после `InterruptionEvent`, стоп ≈63 мс | **interim не реализован** (P0); контракт готов |
| FR-03/§5.7 поздние события отменённого хода не озвучиваются | ✅ | `generation_id`; смоук: 0 чанков старой генерации после перебивания | — |
| FR-04 точная транскрибация: отдельные ревизии, final не перезаписывается | ✅ (контракт) | `speech/revisions.py` + тесты; `ASREvent.revision` | confidence: T-one не отдаёт — это допустимо («там, где доступны»); ручная коррекция — backend/UI |
| FR-11 безопасная деградация | ⚠️ | TTS-недоступен → `fallback_text` (текст); ошибка LLM → деградация в текст | нет таймаутного watchdog TTS/ASR; низкая уверенность ASR без сигнала confidence → уточнение невозможно |
| FR-12 наблюдаемость | ⚠️ | `session_id/turn_id/generation_id` в событиях; TTFA/first_chunk_ms измеряются | нет экспорта ML-метрик в Prometheus (только события/логи) |
| §5.3 VAD/endpointing; настраиваемые пороги; barge-in 150–250 мс; тишина 250–450 мс | ✅ | `VADConfig` (min_speech=160, min_silence=320, prefix, max_utterance); каскад переопределяет prefix=400 мс (онсет) | калибровка false positive/negative на реальных звонках — хвост (P2) |
| §5.3 во время речи бота микрофон слушается; эхо/loopback | ✅ | barge-in по VAD в состоянии SPEAKING; в консоли AEC-флаги и предупреждение про наушники | эхо-тест на реальном hardware — хвост |
| §5.4 ASR-интерфейс `ASRAdapter.stream` + поля `ASREvent` | ✅ | `speech/contracts.py` соответствует сигнатуре SSOT посимвольно | — |
| §5.4 сравнение моделей на своём наборе | ✅ | бенчмарк 234 фразы: GigaAM 9.2 / Whisper 10.8 / T-one 14.7 / Vosk 15.0; RTF T-one ≈0.06 | см. WER-решение (P0) |
| §5.4 custom vocabulary / phrase hints | ❌ | — | у T-one нет hotword-механизма; возможен доменный пост-корректор — ADR (P1) |
| §5.4 язык на уровне сессии | ⚠️ | `language="ru"` на сессии | be-валидация не проводилась (FR-19) — P1 |
| §5.7 TTS: фразовые сегменты, короткий первый сегмент, отмена, чанк-метаданные | ✅ | `TTSSentenceStreamer`; `TTSChunk`: `chunk_id/segment_id/generation_id/is_first/last/first_chunk_ms/synthesis_ms`; тест отмены | — |
| §5.7 нормализация чисел; исходная форма сохраняется | ✅ | `text_norm`+`number_norm` (УССД/телефоны/суммы) + тесты; `TTSChunkEvent.text` теперь несёт исходную фразу | — |
| §5.7 лицензия голоса проверена до выбора | ✅ | `LICENSES.md`, `config/models.lock.yaml`; `ru_bogdan` — MIT (CIS-base) | — |
| §5.8 latency: измерения и честная метрика | ⚠️ | TTFA warm ≈1.43 с (endpoint→первое аудио, включает финализацию ASR ≈0.57 с); cold ≈6.6 с | cold-путь = загрузка модели; **warm-up при старте** (P0); p50/p95-гарнесс (P1) |
| §10 отмена/таймауты внешних операций | ⚠️ | отмена LLM/TTS по `TurnContext`/токену; `asyncio`-отмена генерации | нет timeout на ASR-вызов и watchdog на первый TTS-чанк (P0/P1) |
| §11.1 unit-тесты ML-слоя | ✅ | 540 passed: VAD-endpointing, ревизии (поздний partial не перезаписывает final), отмена TTS, каскад (захват/лаг/watchdog/валидация), ПССД-нормализация | — |
| §11.4 barge-in: остановка плеера p95 ≤ 100 мс | ✅ (стенд) | измерено 63 мс; 0 чанков после `InterruptionEvent` | на реальном media-мосте перемерить (P2) |
| NFR-01 модульность адаптеров | ✅ | протоколы `VADAdapter/ASRAdapter/TTSAdapter`; Silero/onnx-asr/Piper-совместимый интерфейс | — |
| NFR-06 версии моделей/промптов фиксируются | ⚠️ | `models.lock.yaml` + `scripts/fetch_models.py` | SHA-256 и пины — TODO (P1) |
| NFR-10 честная деградация | ✅ | текст-фолбэк, «Ошибка формата ответа» устранена (см. §4), `fallback_reason` в их контракте | — |
| §12.1 веса монтируются, не скачиваются на старте | ✅ | `_PackagedSileroEngine` (torch.package) + `fetch_models.py` | — |
| Отклонения от списка §4.2 (sherpa-onnx/Piper) | ⚠️ | onnx-asr (t-one/GigaAM/Vosk) и Silero TTS прошли сравнение качества | оформить ADR-001 (стек ASR) и ADR-002 (TTS) — P1 |

---

## 3. Измеренные факты на стенде (13.10.2026)

Условия: mock-LLM, локальные модели на CPU демо-машины, канал — WS (локально и через VPS/Tailscale),
`ru_bogdan` 24 кГц, T-one segment-режим. Клочки данных: `artifacts/stage1_e2e/`.

| Метрика | Значение | Комментарий |
|---|---:|---|
| TTFA (конец реплики → первое аудио), тёплый ход | ≈1.43 с | из них финализация ASR ≈0.57 с (полный сегмент), LLM mock ≈0.4 с, TTS first chunk ≈50–150 мс |
| TTFA, первый ход (cold) | ≈6.6 с | загрузка ONNX T-one в процессе; нужен warm-up |
| `first_chunk_ms` (TTS, сервер) | 43–150 мс | A/B Silero MIT: 43 мс first chunk, RTF ≈0.017 |
| Barge-in: чанков после `InterruptionEvent` | 0 | отмена генерации работает |
| Barge-in stop (последний чанк → событие) | 63 мс | p95-цель ≤100 мс на стенде выполняется |
| WER (234 синтетические фразы, телефония) | GigaAM 9.2% / Whisper 10.8% / **T-one 14.7%** / Vosk 15.0% | ориентир SSOT «чистая ≤12%» |
| RTF ASR (T-one, CPU) | ≈0.06 | запас по времени достаточный |

---

## 4. Новые изменения `main` (после `e0ca093`) и влияние на наш стык

### Что появилось в main

- `app/orchestrator/dialog_flow.py`: крупный рефакторинг — `run_turn(...)` (текстовый путь Этапа 0),
  `_retrieve_guarded`, abstention, `_persist(Turn, RetrievalEvent)`, `TurnOutcome` (answer_status/evidence_status).
- `app/orchestrator/grounding.py` (новый) — проверка опоры на evidence.
- `app/models/store.py` (новый) + `app/models/database.py`: **persistence-слой**; `POST /sessions` теперь
  пишет `Session` в БД (best-effort) и появился `SessionBinding` (tenant/language/channel).
- `app/api/main.py`: readiness с проверкой retriever, `/turns/text`, `/end`, handoff-эндпоинты,
  WS-защита `close(1008)` без биндинга, проверка `tenant_id` при создании сессии.
- `app/schemas/api.py`: новые схемы (`TextTurnRequest/Response`, `HandoffResponse`, `SourceRef`).
- `pytest.ini`: из main пропал наш `addopts = -p no:hydra_pytest` (плагин hydra 1.0 роняет pytest на py3.12).

### Влияние на ветку `audio` (интеграция — отдельной задачей, не мерджим)

1. **Сигнатура изменилась:** `stream_final_asr(session_id, asr_text)` — без `tenant_id`/`db`.
   Наш `send_tts_stream` вызывает старую сигнатуру → при переносе стыка обновить вызов.
2. **TTS в main по-прежнему мок** (`_create_mock_tts_chunk` в новом `stream_final_asr`) — наша
   реальная стриминг-озвучка остаётся уникальной и переносится на новый `run_turn`-поток.
3. **Barge-in:** в main — только через JSON `InterruptionEvent`; наш аудио-detect (VAD) дополняет его.
4. `app/schemas/events.py` в main **не менялся** → аддитивные поля `TTSChunkEvent`
   (`generation_id/sample_rate/first_chunk_ms/fallback_text/text`) конфликтов не создают.
5. `app/voice_agent/` в main не тронут (stub) → наши модули каскада не конфликтуют.
6. **Ранее найденные нами проблемы закрыты в main:** сессии пишутся в БД (FK `Turn`), tenant-binding
   на WS; alembic по-прежнему без миграций (таблицы — вне нашего контура).
7. Ожидаемые конфликты при переносе: `dialog_flow.py`, `api/main.py`, `pytest.ini`
   (наш addopts сохранить). План: **переналожить точечные правки стыка** на новые версии, не слепой merge.

---

## 5. Приоритетные действия

**P0 (до демо/приёмки):**
1. Warm-up моделей при старте API (T-one + Silero TTS) — убирает cold-TTFA ≈6.6 с.
2. Interim-гипотезы ASR (T-one 300 мс / `tone`) — закрывает MUST FR-03.
3. Решение по WER: ADR «T-one (стриминг, 14.7%) vs GigaAM (9.2%, нестриминговый)» либо план
   улучшения (LM/домены/фразовые подсказки).
4. Таймаут на ASR-распознавание + разумный fallback.

**P1:**
5. Watchdog первого TTS-чанка (500 мс) с переключением в текстовый режим.
6. p50/p95-гарнесс по этапам + экспорт ML-метрик в Prometheus (без PII).
7. Заполнить `models.lock.yaml` (SHA-256, пины) и перевести выбранные модели в `approved-dev`.
8. ADR-001/002 по стеку ASR/TTS; доменный словарь/пост-корректор (phrase hints).
9. Валидация be-языка (ASR/TTS) перед включением (FR-19).

**P2:**
10. Калибровка VAD/эхо на реальных записях; перемер barge-in на реальном медиамосте.
11. Нотис/согласие в каскаде и retention-политики — совместно с backend (FR-08).
