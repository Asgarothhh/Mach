# План разработки MTS Inbound Voice Agent (трек 1): распределение задач между четырьмя разработчиками

Версия: 1.1 — выравнивание по треку 1\
Дата: 2026-10-13\
Единый источник требований: `SPEC_MTS_VOICE_AGENT_TRACK1.md`\
Основа: «Лекции_ТЗ_МТС.pdf», трек 1. Исходный план 1.0 сохранён отдельным файлом.

## 0. Правила работы

Этот документ распределяет задачи, но не заменяет основную спецификацию.
При конфликте требований приоритет имеет `SPEC_MTS_VOICE_AGENT_TRACK1.md`
(SSOT). Ссылки ниже указывают на разделы SSOT. Перед изменением API,
схем событий, безопасности или архитектуры сначала согласовать изменение
SSOT.

-   [ ] Прочитать указанные разделы SSOT перед началом задачи.
-   [ ] Контракты API и доменных модулей сверять с разделами 9 и 14.
-   [ ] Не коммитить ключи, реальные транскрипты, телефоны или другие
    клиентские данные.
-   [ ] Для моделей фиксировать версии, лицензии, параметры запуска и
    benchmark.
-   [ ] Каждый PR включает тесты, инструкцию запуска и оценку влияния на
    latency/security.
-   [ ] 300--400 мс --- stretch-target первого аудио для короткого тестового сценария, не гарантия полного ответа. Внешний LLM для реальных звонков запрещён до legal/security approval.

## 1. Распределение ответственности

  --------------------------------------------------------------------------
  Роль                    Основная ответственность   Модули
  ----------------------- -------------------------- -----------------------
  ML                      VAD, streaming ASR/TTS,    `speech/`, ML
                          телеком-аудио, речевые     evaluation
                          метрики и benchmark                  

  ML + Backend            Tenant-scoped источники,  `rag/`, `knowledge/`
                          ingestion, RAG, retrieval/
                          reranking, grounding                  

  Backend + ML-Flow       API, orchestrator, call    `api/`, `orchestrator/`,
                          routing, telephony/chat    `telephony/`, `security/`,
                          adapters, guardrails,      `infra/`
                          persistence, audit,
                          deployment/observability   

  Frontend                Onboarding, call history,       `web/`
                          сценарии/routing и админ-панель               
  --------------------------------------------------------------------------

Границы: ML не реализует бизнес-оркестрацию и не обращается напрямую к
PostgreSQL. ML + Backend владеет tenant-scoped базой знаний, но не общей авторизацией.
Backend + ML-Flow владеет API/событиями, telephony/chat handoff и безопасным сквозным потоком.
Frontend использует только публичные API/WebSocket-контракты; браузер
никогда не получает ключ OpenRouter и credentials внутренних сервисов.

## 1.1. Сопоставление с ТЗ трека 1

**Обязательные gates:** (1) onboarding ≤ 5 минут; (2) маршрутизация «голос/чат» для сложного обращения; (3) измеряемая точность транскрибации с ручной коррекцией; (4) история звонков, редактор сценариев и правил; (5) конфиденциальность, уведомление/согласие и tenant isolation.

**Усилители ценности:** аналитика статистики/классификаций/частых вопросов; работа с разрешёнными примерами разговоров; экстренный перевод на человека по команде звонящего; подключение мессенджера одним шагом; последующие email/CRM-модули. Они не заменяют обязательные gates.

Поскольку исходный SSOT был ориентирован на браузерного информационного помощника по публичным материалам МТС, эта редакция переводит его на входящие бизнес-звонки. Исторические RAG/guardrails/streaming/observability наработки сохраняются. Public `mts.by` corpus используется только как отдельный demo fixture, не как база знаний клиента по умолчанию.

## 2. Очерёдность этапов

### Этап 0 --- каркас и контракты

SSOT: §§ 9, 13, 14, 15 «Этап 0», 16.

-   [ ] **Backend + ML-Flow:** репозиторий, конфигурация, Docker
    Compose, health endpoints.
-   [ ] **Backend + ML-Flow:** версионируемые Pydantic-модели API,
    telephony events, routing decisions, chat/human handoff и доменных сущностей.
-   [ ] **ML:** контракты VAD/ASR/TTS и формат partial/final
    результатов.
-   [ ] **ML + Backend:** tenant-scoped ingestion contract и
    `retrieve(query, tenant_id, filters, top_k)`, формат provenance/source metadata.
-   [ ] **Frontend:** каркас onboarding/call history/settings UI и подключение к test-call API/WebRTC.
-   [ ] **Все:** E2E: создание tenant → входящий mock call → ASR → routing →
    ответ/источник → call history/audit → UI.
-   [ ] **Все:** `.env.example` без секретов, README, CI с lint/type
    check/unit tests.

Критерий выхода: каждый модуль запускается отдельно; mock E2E проходит;
health checks работают; секретов в репозитории нет.

### Этап 1 --- минимальный voice cascade и входящий call flow

SSOT: §§ 4--5, 9--11, 15 «Этап 1».

-   [ ] ML: streaming VAD/ASR/TTS, partial/final transcript и barge-in.
-   [ ] Backend + ML-Flow: TelephonyAdapter, test incoming call, call state machine, routing и cancellation.
-   [ ] ML + Backend: подключаемый tenant-scoped retrieval stub или минимальный индекс.
-   [ ] Frontend: onboarding/call-history shell; browser mic — только test mode.
-   [ ] Все: E2E от mock/SIP call до аудиоответа; проверить voice/chat offer и остановку устаревшей генерации.

### Этап 2 --- Tenant RAG, routing, grounding и безопасность

SSOT: §§ 6--7, 11, 15 «Этап 2--3».

-   [ ] ML + Backend: ingestion одобренных company sources per tenant и hybrid retrieval.
-   [ ] Backend + ML-Flow: подключить RAG, scenario router и guardrails к потоку ответа.
-   [ ] ML: измерить влияние ASR-ошибок на routing/retrieval, включая имена и термины бизнеса.
-   [ ] Frontend: показать источники, отсутствие подтверждения, ручную коррекцию транскрипта.
-   [ ] Все: проверить отказ при недостатке evidence, tenant isolation и запрет внешнего LLM для реальных звонков без approval.

### Этап 3 --- админка, качество и демонстрация

SSOT: §§ 7--8, 11--12, 15 «Этап 4--5», 16.

-   [ ] Backend + ML-Flow: аудит, tenant RBAC, consent/retention, telephony/chat provider health, monitoring и admin APIs.
-   [ ] Frontend: onboarding ≤ 5 минут, call history, transcript editing, scenario/routing editor, latency и call analytics.
-   [ ] ML и ML + Backend: business-call ASR/RAG evaluation datasets и regression checks.
-   [ ] Все: нагрузочные, security, tenant isolation, consent, routing/handoff и E2E тесты.

## 3. Разработчик 1 --- ML

**Миссия:** локальный речевой контур, streaming, barge-in,
воспроизводимые оценки качества и задержки.\
**SSOT:** §§ 3.2, 5.3--5.5, 5.7--5.8, 10--12, 14.1, 16, 18; § 15, этапы 1--2.

### To-Do

#### Выбор моделей и воспроизводимость

-   [ ] Сравнить VAD, ASR и TTS для русского языка: streaming, CPU/GPU,
    RAM/VRAM, лицензия, коммерческое использование, размер модели.
-   [ ] Проверить Silero VAD на шуме, паузах, перебиваниях и фоновой
    речи.
-   [ ] Сравнить `sherpa-onnx` и `faster-whisper` на русском, включая
    числа, даты, суммы, названия услуг, аббревиатуры и англицизмы.
-   [ ] Проверить Piper и выбранные голоса на разборчивость, скорость,
    произношение брендов и лицензию именно модели голоса.
-   [ ] Зафиксировать версии, хеши артефактов, параметры запуска и
    способ получения моделей.
-   [ ] Подготовить fallback при отсутствии GPU, недоступности модели и
    timeout.

#### Адаптеры и потоковые события

-   [ ] Реализовать VAD adapter с событиями начала/окончания речи,
    confidence и timestamp.
-   [ ] Реализовать streaming ASR adapter с partial/final transcript,
    sequence ID и timestamp.
-   [ ] Гарантировать порядок событий: поздний partial не перезаписывает
    final.
-   [ ] Реализовать TTS adapter с небольшими аудиочанками и метаданными
    начала/окончания синтеза.
-   [ ] Поддержать отмену ASR/TTS при закрытии сессии и barge-in.
-   [ ] Возвращать типизированные ошибки: `model_unavailable`,
    `timeout`, `invalid_audio`, `cancelled`, `synthesis_failed`.
-   [ ] Покрыть пустой/повреждённый звук, тишину, короткую/длинную речь,
    out-of-order events и отмену unit-тестами.

#### VAD, endpointing и barge-in

-   [ ] Настроить пороги VAD и hangover; измерить false
    positives/negatives.
-   [ ] Не считать каждую паузу окончанием пользовательского хода.
-   [ ] Проверить вдохи, шумы, медленную речь и короткие паузы внутри
    предложения.
-   [ ] При речи пользователя во время TTS отправлять событие
    перебивания и прекращать выдачу новых чанков.
-   [ ] Проверить гонки: отменённый TTS не играет дальше, поздний
    LLM-ответ не возобновляет старый ход.
-   [ ] Измерять время от последнего речевого фрейма до endpointing.

#### Качество и производительность

-   [ ] Подготовить обезличенный/синтетический тестовый набор; реальные
    записи использовать только при утверждённом основании и контроле
    доступа.
-   [ ] Считать WER/CER и отдельные метрики для чисел, сумм, дат,
    названий условий и прайсов tenant.
-   [ ] Подготовить tenant-specific phrase hints/словарь имён и терминов, если поддерживается моделью;
    не терять исходный транскрипт.
-   [ ] Провести субъективную оценку TTS: разборчивость, темп, паузы и
    произношение.
-   [ ] Проверить, что имена, числа, суммы, условия и контактные данные не меняются при нормализации текста для озвучивания.
-   [ ] Измерять p50/p95/p99 VAD, ASR partial/final, endpointing, TTS
    first chunk и полного синтеза.
-   [ ] Записывать hardware, длину фразы, кодек, batch size и
    concurrency в benchmark.
-   [ ] Добавить warm-up, readiness probe и тест длительных сессий на
    утечки памяти.

#### Артефакты и DoD

-   [ ] Речевые адаптеры, тесты и `speech/README.md`.
-   [ ] Model manifest: версии, лицензии, хеши и параметры запуска.
-   [ ] Benchmark качества/latency и CPU/GPU конфигурации.
-   [ ] Контракты SSOT соблюдены; streaming и barge-in проверены
    end-to-end.
-   [ ] Метрики доступны системе наблюдаемости; ограничения
    задокументированы.

## 4. Разработчик 2 --- ML + Backend (RAG/Knowledge Base)

**Миссия:** изолированная база знаний каждой компании-tenant на основе одобренных владельцем документов/FAQ/URL. Каждый найденный фрагмент имеет provenance; при недостатке доказательств агент уточняет, предлагает chat/human handoff или воздерживается от конкретного ответа.\
**SSOT:** §§ 3, 6.1--6.9, 7.2, 9, 11, 12.2, 14.2, 16--17; § 15, этапы 2--4.

### To-Do

#### Источники и crawling

-   [ ] Создать tenant-scoped реестр разрешённых источников компании (URL, документы, FAQ); наследуемые источники `mts.by` хранить только в отдельном тестовом tenant, если нужны для demo regression.
-   [ ] Для источника фиксировать URL, тип, приоритет, allowlist путей,
    частоту обновления, статус и владельца.
-   [ ] Покрыть темы компании, заданные tenant profile: услуги/продукты, контакты, цены, сроки, типовые вопросы и правила обработки обращений.
-   [ ] Исключить личные кабинеты, закрытые API, страницы с
    пользовательскими данными и любые области, требующие авторизации.
-   [ ] Реализовать allowlist доменов/путей, rate limit, timeout,
    retry/backoff и защиту от crawler traps.
-   [ ] Соблюдать robots.txt и условия использования; предусмотреть
    объяснимое ручное исключение URL.
-   [ ] Создать отчёт покрытия: нельзя считать ingestion завершённым
    после загрузки главной страницы.

#### Ingestion pipeline

-   [ ] Реализовать
    `fetch → parse → normalize → deduplicate → classify → chunk → embed → index → validate → publish`.
-   [ ] Поддержать HTML и публичные документы; хранить URL, title, время
    загрузки, дату изменения, content hash и версию парсера.
-   [ ] Удалять boilerplate, не теряя сноски, исключения, условия и даты
    действия условий и прайсов tenant.
-   [ ] Дедуплицировать по canonical URL и content hash;
    переиндексировать только изменённое.
-   [ ] Сохранять provenance до уровня chunk: документ, URL, заголовок,
    anchor, дата индексации и версия индекса.
-   [ ] Ошибка одного URL не должна отменять весь run; ingestion должен
    быть идемпотентным.
-   [ ] Добавить dry-run и отчёт added/changed/deleted/failed/skipped.
-   [ ] Публиковать индекс атомарно и поддержать rollback на предыдущую
    версию.
-   [ ] Проверить прайсы, таблицы условий, исключения, даты действия и документы tenant.

#### Chunking и retrieval

-   [ ] Разбивать по структуре и смысловым блокам; не отделять значения
    таблиц от названий параметров.
-   [ ] Подобрать размер chunk/overlap на benchmark; сохранять заголовки
    родительских разделов.
-   [ ] Выбрать multilingual embeddings с лицензией и качеством на
    русском; зафиксировать версию и размерность.
-   [ ] Реализовать dense retrieval в Qdrant и sparse retrieval для
    точных терминов бизнеса, названий услуг, сумм и аббревиатур.
-   [ ] Реализовать hybrid fusion через RRF, если benchmark не
    обосновывает иной согласованный вариант.
-   [ ] Добавить фильтры по домену, актуальности, статусу, типу
    документа и версии индекса.
-   [ ] Реализовать retrieval API строго по SSOT: query, filters, top_k,
    chunks, scores, source metadata, index version.
-   [ ] Сохранять числа, отрицания, даты и названия продуктов при query
    normalization.
-   [ ] Добавить deduplication и reranking; ограничить timeout и размер
    входа reranker.
-   [ ] Возвращать стабильные ссылки и короткие фрагменты источников.
-   [ ] Низкорелевантный/пустой результат --- штатный исход, не
    исключение.
-   [ ] Кэшировать частые безопасные запросы с ключом, включающим index
    version и filters; инвалидировать при публикации.
-   [ ] Проверять health Qdrant, размерность векторов и целостность
    индекса.

#### Grounding, безопасность и evaluation

-   [ ] Настроить abstention thresholds на эталонном наборе, а не только
    на синтетических позитивных примерах.
-   [ ] Для цен/сроков/условий приоритизировать актуальный одобренный источник данного tenant; не смешивать конфликтующие версии или tenants.
-   [ ] Передавать только evidence, необходимое для ответа; retrieved
    content всегда считать недоверенными данными.
-   [ ] При низкой релевантности, конфликте или устаревшем источнике
    возвращать «недостаточно подтверждений».
-   [ ] Подготовить версионируемый набор русских вопросов, включая
    опечатки, ASR-ошибки и разговорные формулировки.
-   [ ] Для примеров указать ожидаемый источник, тип ответа и критерий
    abstention.
-   [ ] Измерять Recall@k, MRR/nDCG, валидность источников,
    groundedness, ложные утверждения и latency retrieval.
-   [ ] Сравнить dense-only, sparse-only, hybrid и reranker на одном
    benchmark.
-   [ ] Добавить regression gate для смены embedding, parser, chunking и
    reranker.
-   [ ] Тестировать prompt injection в содержимом источников.
-   [ ] Создать отчёт покрытия и перечень документов, которые не удалось
    корректно разобрать.

#### Артефакты и DoD

-   [ ] Source registry, crawler и ingestion pipeline.
-   [ ] RAG API с Qdrant и локальными embedding/reranker моделями.
-   [ ] Версионирование индекса, атомарная публикация и rollback.
-   [ ] Evaluation dataset, метрики и `rag/README.md`.
-   [ ] Для каждого результата доступен официальный URL/версия; нет
    индексации закрытых систем/пользовательских данных и нет пересечения индексов tenants.
-   [ ] Пустой evidence приводит к abstention; повторный ingestion не
    плодит дубликаты.

## 5. Разработчик 3 --- Backend + ML-Flow

**Миссия:** безопасный и отменяемый call flow: tenant/onboarding API, telephony adapter, voice/chat/human routing, state machine, OpenRouter policy, guardrails, хранение, аудит, admin endpoints, observability и deployment.\
**SSOT:** §§ 3--5, 7--16, 18.

### To-Do

#### API и каркас

-   [ ] Реализовать FastAPI, конфигурацию окружений, dependency injection и структурированные ошибки.
-   [ ] Реализовать tenant onboarding/config API, включая measurement event для ≤ 5-minute setup.
-   [ ] Реализовать HTTP/WebSocket API строго по разделу 9; не создавать
    несовместимые payload.
-   [ ] Ввести типизированные модели, версионирование API,
    correlation/session/turn/trace IDs.
-   [ ] Разделить публичные и административные endpoints.
-   [ ] Добавить health/readiness/liveness; readiness проверяет
    необходимые зависимости.
-   [ ] Ввести rate limits, лимиты размера аудиофрейма и длительности
    сессии, backpressure и graceful shutdown.

#### Orchestrator и state machine

-   [ ] Реализовать call/session state machine согласно SSOT.
-   [ ] Реализовать `TelephonyAdapter` contract: incoming call, media lifecycle, hangup, human transfer result; подключить mock adapter и при наличии доступа SIP/VoIP test integration.
-   [ ] Реализовать routing policy: voice answer, offer chat, human handoff, safe fallback; не передавать контекст в мессенджер без согласия.
-   [ ] Связать VAD/ASR events с turn; игнорировать устаревшие
    partial/final.
-   [ ] Создать cancel token на каждый turn и распространять отмену на
    RAG, OpenRouter и TTS.
-   [ ] При barge-in отменять ответ, останавливать аудио и очищать
    буферы.
-   [ ] Обеспечить idempotency и защиту от повторных событий.
-   [ ] Ограничить параллельные turns, добавить очередь и backpressure.
-   [ ] Реализовать fallback при недоступности ASR, RAG, OpenRouter или
    TTS.
-   [ ] Хранить минимально необходимое состояние диалога и `tenant_id`; не отправлять всю транскрипцию без причины.
-   [ ] Сохранять consent/notice version, routing decision, outcome и provider callback для каждого handoff.
-   [ ] Зафиксировать compaction/summarization с сохранением фактов,
    отрицаний и ограничений без смешения сессий.

#### OpenRouter adapter

-   [ ] Реализовать streaming adapter с timeout, cancellation, retry
    policy и нормализованными ошибками.
-   [ ] Хранить ключ только на сервере; исключить из bundle, логов,
    traces и error messages.
-   [ ] Настроить allowlist model IDs; неизвестная модель запрещена по
    умолчанию.
-   [ ] Конфигурировать лимит токенов, timeout, параметры модели,
    fallback model и максимальный контекст.
-   [ ] Проверить актуальные условия провайдера, retention/routing и
    допустимость передачи данных; не считать параметр zero-retention
    гарантией соответствия требованиям без проверки.
-   [ ] Передавать только минимизированный контекст, evidence и
    структурированные инструкции.
-   [ ] Обрабатывать неполные stream chunks и сетевые разрывы.
-   [ ] Не завершать ответ до post-generation checks.
-   [ ] Добавить mock provider для локальной разработки без ключа.
-   [ ] Логировать model ID, latency, token counts и категорию ошибки,
    но не auth headers/ключи/нефильтрованный чувствительный prompt.

#### Guardrails и privacy

-   [ ] Реализовать PII detection/masking перед внешним вызовом LLM
    согласно SSOT.
-   [ ] Разделить оригинальный транскрипт, маскированную версию и
    UI-представление; доступ к оригиналу отдельно авторизовать и
    аудировать.
-   [ ] Документировать, какие поля покидают инфраструктуру.
-   [ ] Защищаться от prompt injection в retrieved content.
-   [ ] Проверять выход на PII, неподтверждённые бизнес-условия и запрещённые
    обещания; при критическом нарушении --- abstain/fallback.
-   [ ] Не заявлять об успешной операции в биллинге/личном кабинете без
    реализованного инструмента и подтверждения.
-   [ ] Реализовать RBAC на сервере для каждой админской операции.
-   [ ] Определить retention для transcript, session metadata, audio,
    application logs и security audit logs.
-   [ ] Не сохранять raw audio по умолчанию без утверждённой
    необходимости.
-   [ ] Реализовать удаление/редакцию по политике и аудит
    доступа/изменений.
-   [ ] Проверить TLS, сетевую изоляцию, CORS, CSRF (где применимо),
    secure cookies и rate limiting.
-   [ ] Провести threat-model review.

#### Persistence, audit и observability

-   [ ] Создать миграции PostgreSQL для sessions, turns, transcript
    segments, source refs, latency spans, ingestion runs и audit events.
-   [ ] Хранить только необходимые поля; не дублировать PII.
-   [ ] Сохранять partial/final transcript с timestamps в соответствии с
    masking/retention policy.
-   [ ] Логировать state events, retrieval IDs/index version, model ID,
    latency, fallback и cancellation reason.
-   [ ] Разделить операционные логи, транскрипты и audit logs.
-   [ ] Реализовать pagination/filtering и серверные ограничения на
    экспорт.
-   [ ] Добавить OpenTelemetry spans для websocket, ASR, retrieval,
    reranker, OpenRouter TTFT/stream, guardrails, TTS.
-   [ ] Экспортировать метрики в Prometheus; подготовить Grafana
    dashboards и alerts.
-   [ ] Не использовать телефон, transcript, prompt и другие
    чувствительные значения как labels.
-   [ ] Считать end-to-end latency и этапы отдельно; измерять
    p50/p95/p99.
-   [ ] Настроить sampling и redaction чувствительных атрибутов.

#### Admin API, deployment и тесты

-   [ ] Защищённые endpoints для сессий, транскриптов, источников,
    latency, ошибок и ingestion runs.
-   [ ] Запуск ingestion доступен только соответствующей роли; добавить
    idempotency и защиту от параллельных full runs.
-   [ ] Не открывать внутренние PostgreSQL/Redis/Qdrant/inference
    endpoints браузеру.
-   [ ] Docker Compose: API/orchestrator, PostgreSQL, Redis (если
    используется), Qdrant, frontend, observability и нужные ML services.
-   [ ] Использовать pinned image tags, volumes, health checks, restart
    policy и документированный reset demo data.
-   [ ] Секреты через env/secret injection; `.env` не коммитить.
-   [ ] Unit/integration tests для state machine, cancellation,
    guardrails, persistence, RBAC и ошибок зависимостей.
-   [ ] E2E smoke test с mock LLM и mock speech adapters.
-   [ ] CI: lint, type check, unit tests, migration checks,
    dependency/security scan.
-   [ ] Runbook: старт/стоп, восстановление БД, reindex, ротация ключей,
    диагностика OpenRouter и очистка демо-данных.

#### Артефакты и DoD

-   [ ] API/orchestrator, OpenRouter adapter, guardrails, RBAC, аудит и
    миграции.
-   [ ] Docker Compose, telemetry, dashboards и runbook.
-   [ ] Timeout/cancellation/fallback есть для всех внешних вызовов.
-   [ ] Нет секретов в браузере/логах; админские данные защищены и
    аудитируются.
-   [ ] Стенд разворачивается по README на чистом окружении.

## 6. Разработчик 4 --- Frontend

**Миссия:** onboarding-портал бизнес-клиента, call history, редактор сценариев/правил и админ-панель на согласованных API-контрактах; показывать транскрипт, маршрут, consent state, handoff, latency и ошибки. Browser voice UI — test console, не единственный продуктовый канал.\
**SSOT:** §§ 3.1, 5.1--2, 5.7, 8--12, 16; § 15, этапы 0 и 4--5.

### To-Do

#### Каркас, onboarding и контракты

-   [ ] Создать TypeScript-проект со строгими типами, lint, formatter и
    тестами.
-   [ ] Разделить пользовательское приложение и админ-панель по
    маршрутам/layout.
-   [ ] Вынести API client, WebSocket client, типы событий и обработку
    ошибок в отдельные модули.
-   [ ] Использовать OpenAPI/общие контракты для генерации типов, если
    доступно; не дублировать схемы вручную.
-   [ ] Добавить loading, disconnected, reconnecting, error, empty и permission-denied states.
-   [ ] Реализовать onboarding wizard с минимальным путём до test call ≤ 5 минут и понятными блокировками отсутствующих production credentials.
-   [ ] Не включать OpenRouter key или внутренние credentials во
    frontend.

#### Call/test UI и маршрутизация

-   [ ] В browser test mode запрашивать разрешение микрофона; для входящего telephone call не требовать browser mic.
-   [ ] Проверить MediaDevices/WebSocket и требования secure context.
-   [ ] Реализовать состояния: connecting, listening, transcribing,
    thinking, speaking, cancelling, error.
-   [ ] Отображать partial transcript как предварительный, final --- как
    подтверждённый.
-   [ ] Воспроизводить streaming audio chunks и очищать очередь при
    barge-in.
-   [ ] При перебивании сразу обновлять UI и не проигрывать старые
    chunks.
-   [ ] Ограничить reconnect retries; не создавать несколько микрофонных
    потоков.
-   [ ] Добавить call status, consent/notice status, voice/chat route state, human handoff result, завершение тестовой сессии и понятные fallback-сообщения.
-   [ ] Обеспечить keyboard navigation, focus, aria labels и доступные
    статусы.

#### Диалог и источники

-   [ ] Показывать user/bot turns в правильном порядке.
-   [ ] Показывать статус ответа и безопасную диагностику, но не
    prompts/секреты.
-   [ ] Для каждого ответа отображать источники: заголовок, URL/домен,
    дата/версия и короткий фрагмент.
-   [ ] Безопасно открывать внешние ссылки (`noopener noreferrer`).
-   [ ] Отображать отсутствие evidence и fallback как отдельные
    состояния.
-   [ ] Не показывать «операция выполнена», если backend не подтвердил
    результат.
-   [ ] Очищать локальное аудио-состояние после завершения сессии.

#### Админка: сессии и транскрипты

-   [ ] Реализовать авторизацию согласно backend-схеме; скрытие маршрута
    не заменяет серверную авторизацию.
-   [ ] Список сессий: фильтры по времени/status/session ID и
    pagination.
-   [ ] Детальная сессия: timeline, transcript segments, sources, model
    ID, latency breakdown, ошибки и fallback.
-   [ ] Различать partial/final transcript и отменённые turns; дать уполномоченной роли редактировать final transcript с отображением исходной версии, diff и audit status.
-   [ ] По умолчанию показывать маскированные данные; раскрытие
    оригинала --- только при разрешении backend.
-   [ ] Не выводить транскрипт в URL, browser console или frontend
    telemetry.
-   [ ] Экспортировать данные только при наличии permission и серверного
    audit event; иначе не показывать фиктивную кнопку.
-   [ ] Очищать чувствительное состояние при logout и смене
    пользователя.

#### Админка: сценарии, маршрутизация, мониторинг и knowledge base

-   [ ] Dashboard: число звонков, типы обращений, частые вопросы, доли chat/human handoff, latency p50/p95, error rate, состояние telephony/chat dependencies и RAG.
-   [ ] Получать метрики из backend/Prometheus API, а не рассчитывать из
    неполной browser выборки.
-   [ ] Показывать ingestion runs per tenant: время, статус, количество документов, изменения, ошибки и active index version.
-   [ ] Реализовать scenario/routing editor, draft validation, publish/version diff и rollback.
-   [ ] Кнопка синхронизации доступна только роли с нужным permission;
    запрос --- через backend.
-   [ ] Подтверждать запуск ресурсоёмкой операции и показывать
    результат.
-   [ ] Страница retrieval diagnostics: query, chunks, scores, reranker
    score, source URL и index version --- только для разрешённой роли.
-   [ ] Не показывать stack trace обычным пользователям, secrets,
    prompts или PII без специального доступа.

#### Надёжность, безопасность и тесты

-   [ ] Обработать disconnect, истечение сессии, server error, rate
    limit и недоступность источника.
-   [ ] Добавить timeout UI и безопасный retry только для идемпотентных
    операций.
-   [ ] Защититься от XSS: transcript и retrieved snippets рендерить как
    текст, не как доверенный HTML.
-   [ ] Не выполнять markdown/HTML из транскриптов/документов без
    безопасной очистки.
-   [ ] Проверить длинные транскрипты, большие списки сессий, ошибки
    сети и адаптивность.
-   [ ] Unit tests для статусов, транскриптов, источников и latency.
-   [ ] Contract tests по примерам API/WebSocket из SSOT.
-   [ ] E2E: mock-сессия, transcript, ответ с источником, barge-in,
    завершение.
-   [ ] Admin E2E: авторизация, просмотр сессии, masking, ingestion
    status и отказ неавторизованному пользователю.
-   [ ] Подготовить `web/README.md`: запуск, env, mock mode, тесты и
    сборка.

#### Артефакты и DoD

-   [ ] Voice web-app и админ-панель.
-   [ ] Типизированные API/WebSocket clients и тесты.
-   [ ] Основной flow демонстрирует входящий call через SIP/test adapter; voice TTS streaming и barge-in работают. Browser WebRTC явно маркирован как test mode.
-   [ ] Источники tenant видны либо показано явное отсутствие подтверждений; чужие tenants недоступны.
-   [ ] Портал показывает onboarding, call history, исправления транскриптов, сценарии/routing, handoff results, аналитику и latency по правам доступа.
-   [ ] Недоверенный контент не интерпретируется как HTML; секреты не
    попадают в браузер.

## 7. Общий Definition of Done продукта

Приёмка проводится по SSOT, раздел 16.

-   [ ] Чистое развёртывание по инструкции проходит без ручного
    исправления БД.
-   [ ] Текстовый E2E проходит на mock provider.
-   [ ] Входящий call E2E проходит от SIP/test-call adapter до TTS; browser mic E2E остаётся дополнительным test mode.
-   [ ] Barge-in останавливает устаревший ответ.
-   [ ] Ответы подтверждаются одобренными источниками конкретного tenant; без evidence агент уточняет/предлагает chat/human handoff, а не выдумывает.
-   [ ] Браузер не имеет прямого доступа к OpenRouter, PostgreSQL, Redis
    или Qdrant.
-   [ ] Секреты и неотфильтрованные чувствительные данные отсутствуют в
    логах/telemetry.
-   [ ] История и транскрипты доступны по tenant-scoped RBAC и retention policy; ручная коррекция audit trail сохраняется.
-   [ ] Новый tenant проходит onboarding до тестового звонка за ≤ 5 минут.
-   [ ] Voice/chat routing и human handoff/fallback покрыты E2E.
-   [ ] Уведомление/согласие по обработке звонка протестированы; real-call traffic не уходит во внешний LLM без approval.
-   [ ] Видны latency каждого этапа и end-to-end p50/p95 с условиями
    измерения.
-   [ ] Есть отчёты нагрузочных, security, regression и E2E тестов.
-   [ ] Ограничения MVP честно указаны в README и demo UI.

## 8. Definition of Done для каждого PR

-   [ ] Ссылка на задачу и разделы SSOT.
-   [ ] Описание изменения и мотивация.
-   [ ] Тесты и команда запуска.
-   [ ] Изменения API/схем/событий и совместимость.
-   [ ] Влияние на latency/нагрузку, если применимо.
-   [ ] Влияние на privacy/security, новые поля логов и хранения.
-   [ ] Обновлённая документация и конфигурация.
-   [ ] Нет секретов и реальных клиентских данных.
-   [ ] Скриншот/demo-результат для UI PR.

## 9. Разрешение конфликтов

1.  `SPEC_MTS_VOICE_AGENT_TRACK1.md` --- единственный источник архитектурных,
    функциональных, security и acceptance-требований.
2.  Этот документ определяет ownership и порядок исполнения.
3.  API schemas и тесты проверяют соответствие SSOT, но не меняют требования молча. SSOT для этой редакции — `SPEC_MTS_VOICE_AGENT_TRACK1.md`.
4.  Если требование невыполнимо или найдена более подходящая open-source
    альтернатива, подготовить ADR с причиной, лицензией, benchmark,
    security review, миграционным планом и обновлением SSOT.
5.  До согласования изменения использовать текущий SSOT; обходные
    решения помечать явно.
