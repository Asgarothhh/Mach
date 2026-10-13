# Software / model / voice licenses and review status

Нормативные источники: `docs/SPEC_MTS_VOICE_AGENT_TRACK1.md` §4.2 и §16 (DoD,
п. 6), `docs/DEV_PLAN_TRACK1.md` §3 («Выбор моделей и воспроизводимость»).

Правило: ни одна зависимость, чекпойнт или голос не включаются в продукт,
пока в этом файле нет строки review. «Open-weight» ≠ «open-source»: лицензия
весов проверяется отдельно от лицензии кода. Точные версии/SHA-256
фиксируются в `config/models.lock.yaml`.

## Критическая находка: Silero TTS v5 RU — некоммерческая лицензия

Публикация, по которой выбрана модель: «Теперь silero-tts v5 на русском
языке умеет задавать вопросы» (habr.com/ru/articles/1015942).

По состоянию на 2026-10-13:

- **Лицензия репозитория/весов `v5_5_ru`, `v5_4_ru`, `v5_ru` и остальных
  моделей репозитория — CC BY-NC-SA 4.0 (NonCommercial)**. Это **не**
  допускает коммерческое использование без отдельного соглашения с Silero.
- Исключение по README репозитория: **`v5_cis_base` / `v5_cis_base_nostress`
  опубликованы под MIT** (файл `LICENSE_CIS`), включая русские голоса с
  префиксом `ru_`. Но у них нет автоматических ударений (для славянских
  языков нужно явно размечать ударение `к+ошка`) и нет интонации вопросов.

**Решение для трека 1 (зафиксировать явно):**

1. **Демо/внутренняя оценка:** разрешается `v5_5_ru` (CC BY-NC-SA) как
   основной русский голос — это соответствует статусу демостенда; в UI/README
   демо нельзя заявлять коммерческую готовность.
2. **Коммерческий production:** нужна одна из опций — (а) отдельная
   коммерческая лицензия Silero; (б) `v5_cis_base_nostress` (MIT) + инструмент
   расстановки ударений (license review для silero-stress обязателен);
   (в) другой разрешённый TTS (например, Piper с проверенной лицензией
   конкретного голоса). Решение и дата — по согласованию с владельцем продукта.

## Программные зависимости (код)

| Компонент | Лицензия кода | Использование | Статус |
|---|---|---|---|
| numpy | BSD-3-Clause | базовые операции с PCM | approved |
| pydantic | MIT | контракты событий | approved |
| pytest, pytest-asyncio, ruff, mypy | MIT / PSF / Apache-2.0 | dev/CI | approved |
| torch (PyTorch) | BSD-3-Clause | исполнение Silero-моделей | approved |
| silero-vad (pip) | MIT | VAD | approved |
| faster-whisper | MIT | baseline ASR (кандидат) | candidate |
| sherpa-onnx | Apache-2.0 | streaming ASR (кандидат) | candidate |
| piper1-gpl | GPL-3.0 | альтернативный TTS (кандидат) | review |
| silero-stress | требует проверки | авторасстановка ударений | review |

## Модели и голоса

| Модель / голос | Лицензия весов | Коммерческое использование | Статус | Комментарий |
|---|---|---|---|---|
| Silero VAD v6 | MIT | разрешено | approved-dev | пороги endpointing настраиваются нами |
| Silero TTS `v5_5_ru` (aidar, baya, kseniya, xenia, eugene) | CC BY-NC-SA 4.0 | **запрещено без отдельного соглашения** | demo-only | интонация вопросов, ударения, омографы, 8/24/48 кГц |
| Silero TTS `v5_4_ru` | CC BY-NC-SA 4.0 | запрещено без соглашения | demo-only | без голоса eugene |
| Silero TTS `v5_cis_base_nostress` (`ru_*`) | MIT | разрешено | candidate | нужна явная разметка ударений; без интонации вопросов |
| Whisper large-v3-turbo (faster-whisper) | MIT | разрешено | candidate | baseline качества транскрипции |
| sherpa-onnx RU модели | per-model | требует review на выбранной модели | candidate | выбрать по WER/latency на своём наборе |
| Piper voice-модели | per-voice | требует review на выбранном голосе | review | каждая voice-модель лицензируется отдельно |

## Обязательные действия перед production

- [ ] Юридически подтвердить или заменить голос Silero TTS RU (см. решение выше).
- [ ] Провести license review для silero-stress (если используется с MIT-моделью).
- [ ] Зафиксировать точные версии и SHA-256 всех весов в `config/models.lock.yaml`.
- [ ] Не выдавать демостенд как production-готовый продукт (SSOT §1.2, §2.5).
