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

| iter/cmp | Лицензия кода | Использование | Статус |
|---|---|---|---|
| onnx-asr | MIT | рантайм ASR (onnxruntime, без torch) | approved |
| pyarrow | Apache-2.0 | чтение parquet-датасетов (eval) | approved |
| soundfile | BSD-3-Clause | чтение/запись аудио (eval) | approved |
| soxr (python-soxr / libsoxr) | LGPL-2.1 | ресемплинг в eval-скриптах | approved-eval (LGPL — только инструменты оценки) |
| numpy | BSD-3-Clause | базовые операции с PCM | approved |
| pydantic | MIT | контракты событий | approved |
| pytest, pytest-asyncio, ruff, mypy | MIT / PSF / Apache-2.0 | dev/CI | approved |
| torch (PyTorch) | BSD-3-Clause | исполнение моделей | approved |
| silero-vad (pip) | MIT | VAD | approved |
| silero-stress (pip) | MIT | автоударения для CIS-base | approved |
| faster-whisper | MIT | baseline ASR + WER-оценка | candidate |
| sherpa-onnx | Apache-2.0 | streaming ASR (кандидат) | candidate |
| kokoro (движок) | Apache-2.0 | Kokoro-ru | approved |
| misaki (G2P для kokoro) | Apache-2.0 | G2P | approved |
| ruaccent | MIT (репозиторий) / Apache-2.0 (PyPI) | ударения/омографы в ru_g2p | approved |
| **phonemizer / phonemizer-fork** | **GPL-3.0** | backend G2P Kokoro-ru (через espeak-ng) | **требует review** |
| **espeak-ng / espeakng-loader** | **GPL-3.0** (сама библиотека) | фонемизация Kokoro-ru | **требует review** |
| s3tokenizer | Apache-2.0 | компонент Chatterbox | approved |
| resemble-perth | MIT | watermark Chatterbox | approved |
| **pykakasi** | **GPL-3.0** | транзитивная зависимость Chatterbox (только японский путь) | **требует review** |
| conformer | MIT | компонент Chatterbox | approved |
| utmosv2 (SaruLab) | MIT | MOS-оценка качества (eval) | approved |
| piper1-gpl | GPL-3.0 | альтернативный TTS (кандидат) | review |

### GPL-3.0 в цепочке зависимостей (важно для production)

- **Kokoro-ru**: веса OpenRAIL, но путь G2P идёт через `ru_g2p.py` →
  `phonemizer` → `espeak-ng` (**GPL-3.0**).
- **Chatterbox**: код и веса MIT, но в зависимостях есть `pykakasi`
  (**GPL-3.0**, используется только для японского текста).

Для **SaaS-эксплуатации** (сервис, к которому пользователи обращаются по сети,
без распространения бинарей) GPL-компоненты обычно допустимы, но это должно
быть подтверждено юристами для конкретной схемы поставки. Если распространение
бинарной сборки планируется, нужно: для Kokoro — заменить espeak-на-фонемизацию
на permissive-реализацию (их же рецепт + RUAccent); для Chatterbox — вырезать
японский путь или заменить токенизатор. **Полностью permissive-чистая связка
без GPL — это Silero `v5_cis_base_nostress` + `silero-stress` (MIT+MIT).**

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

## Раунд 1: подбор коммерчески чистой замены Silero (2026-10-13)

Задача: найти русский TTS «такого же качества», но с лицензией, допускающей
коммерческое использование. Проверенные варианты:

| Кандидат | Лицензия (код / веса) | Голос | Комментарий |
|---|---|---|---|
| **Silero v5_cis_base_nostress + silero-stress** | MIT / MIT | `ru_*` голоса (восточноевропейские актёры) | та же семья Silero; автоударения через silero-stress; без интонации вопросов; CPU |
| **Chatterbox Multilingual V3** (Resemble AI) | MIT / MIT | встроенный голос, без референса | 23 языка вкл. ru; 24 кГц; AR 0.5B — нужен GPU; PerTh watermark; качество ru проверяется benchmark-ом |
| **Kokoro-82M RU** (zaakirio/kokoro-ru) | Apache-2.0 / OpenRAIL | sveta, masha, dima (согласованные актёры) | 82M, RTF ~0.10 на CPU; детерминированная просодия; автоударения через RUAccent (MIT); ONNX для on-device |
| **Piper ru** (SSOT §4.2 baseline) | GPL-3.0 / per-voice | зависит от голоса | лицензии голосов исторически неясные; качество ниже нейросетевых |
| F5-TTS RU (Misha24-10) | код MIT, веса CC-BY-NC | клонирование | **некоммерческая** — отклонён |
| Fish Speech / OpenAudio s1-mini | веса CC-BY-NC-SA | клонирование | **некоммерческая** — отклонён |
| Qwen3-TTS 0.6B | Apache-2.0 | пресеты zh/en/ja/ko | ru поддержан, но «родного» русского голоса нет — нужен cloning с лицензированным референсом; отложен |
| MOSS-TTS-Nano 100M | Apache-2.0 | cloning по референсу | CPU/streaming, но установка тяжёлая (WeTextProcessing); отложен |
| VoxCPM / VoxCPM2 | Apache-2.0 | cloning | карточка VoxCPM прямо просит «research/development only» — флаг риска, не берём без нужды |

Итог раунда (заполняется после прогона `scripts/tts_ab_eval.py`):
- объективные метрики: first-chunk ms, RTF, WER-прокси (Whisper round-trip);
- субъективный выбор голоса — прослушивание командой на
  `https://mach.194-146-38-78.sslip.io/tts-ab.html`;
- рекомендация по production-голосу — см. отчёт в PR/чате.

### Результаты прогона 1 (2026-10-13, 7 конфигураций)

Железо: 12-ядерный CPU + RTX 3060, torch 2.6.0; WER — Whisper large-v3-turbo
(round-trip), MOS — UTMOSv2 (SaruLab). Числа числовых/телефонных фраз одинаково
завышают WER у всех движков (артефакт формата чисел в ASR, не ошибка синтеза).

| Движок | Лицензия | Первый чанк p50 | RTF | WER | MOS |
|---|---|---:|---:|---:|---:|
| Silero v5.5 RU xenia — демо-эталон | CC BY-NC-SA | 133 мс | 0.059 | 0.076 | 2.71 |
| **Silero CIS-base + stress: ru_alexandr** | **MIT+MIT** | **137 мс** | **0.057** | **0.076** | **3.08** |
| Silero CIS-base + stress: ru_albina | MIT+MIT | 152 мс | 0.056 | 0.076 | 2.97 |
| Silero CIS-base + stress: ru_ekaterina | MIT+MIT | 148 мс | 0.057 | 0.076 | 2.87 |
| Silero CIS-base + stress: ru_dmitriy | MIT+MIT | 161 мс | 0.056 | 0.076 | 2.59 |
| Kokoro-82M RU sveta | OpenRAIL (+GPL-3 G2P) | 861 мс | 0.245 | **0.016** | 2.60 |
| Chatterbox Multilingual V3 | MIT | 1850 мс | 0.609 | 0.253 | **3.10** |

**Рекомендация по умолчанию: Silero `v5_cis_base_nostress` + `silero-stress`
(MIT+MIT), голос-кандидат `ru_alexandr`.** Это «та же семья Silero»: MOS не
хуже демо-эталона (3.08 против 2.71), WER идентичен, первый чанк ~137 мс,
RTF ~0.057 на CPU, нативные 8/24/48 кГц (телефония). Единственное отличие от
`v5_5_ru` — нет автоматической интонации вопросов (уточняющие вопросы агента
будут звучать нейтрально).

Нюансы по остальным:
- **Kokoro-ru** — лучшая разборчивость (WER 0.016), но MOS ниже, first-chunk
  ~0.9 c и GPL-3.0 в G2P-цепочке; годится для CPU/VPS-варианта после юр-ревью.
- **Chatterbox V3** — высокий MOS, но WER 0.253 (галлюцинации, «кастой» вместо
  «сколько стоит»), first-chunk 1.85 c и RTF 0.61; RU stress-модуль
  (`russian_text_stresser`) вообще не опубликован. Для русского phone-агента
  в текущем виде не подходит; оставляем как кандидат для пересмотра.

Страница для прослушивания и голосования по голосам:
`https://mach.194-146-38-78.sslip.io/tts-ab.html`.

## Раунд 2: ASR для русской телефонии (2026-10-13)

Задача: выбрать streaming-ASR для телефонного канала и собрать честный
тестовый набор из реальных записей.

Кандидаты (все с коммерчески допустимыми лицензиями; рантайм — `onnx-asr`,
MIT, только onnxruntime):

| Модель | Лицензия | Роль в сравнении |
|---|---|---|
| **T-one** (t-tech, 71M) | Apache-2.0 | основной кандидат: streaming по 300 мс, обучен под телефонию |
| GigaAM v3 CTC/RNNT (Сбер, 242M) | MIT | эталон качества (лучший общий WER по публичным бенчмаркам) |
| Vosk small ru (20M) | Apache-2.0 | лёгкий streaming-базлайн |
| Whisper large-v3-turbo (1540M) | MIT | оффлайн-эталон качества (faster-whisper) |

Датасет тестового набора (234 фразы, ~25 мин; `scripts/fetch_asr_testset.py`):

| Категория | Источник | Лицензия | Статус |
|---|---|---|---|
| calls (110) | OpenSTT телефонные звонки (mirror `Malecc/asr_calls_2_val`) | **не указана в карточке датасета** | **только внутренняя оценка**: не распространять и не коммитить аудио (artifacts/ в .gitignore) |
| clean (60) + clean-noise (40) | FLEURS ru dev + розовый шум 10 дБ | CC-BY-4.0 | ok |
| synthetic-clean/telephony (24) | наш MIT-голос: числа, телефоны, УССД | MIT | ok |

Примечание: Mozilla Common Voice с октября 2025 больше не публикуется на
Hugging Face (переехал в Mozilla Data Collective) — в наборе не используется.
