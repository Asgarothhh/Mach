# ADR-0001: Контракты базы знаний и retrieval для трека 1

- Статус: принято для группы 1 (ML + Backend); вопросы в разделе «Открытые вопросы» не закрыты
- Дата: 2026-10-13
- Роль-владелец: ML + Backend (RAG/Knowledge Base)
- Нормативный источник: `docs/SPEC_MTS_VOICE_AGENT_TRACK1.md` (SSOT, v1.1)
- Декомпозиция: `docs/MTS_VOICE_AGENT_4_DEVELOPERS.md` (v1.0), раздел 4

## Контекст

Декомпозиция v1.0 написана для предыдущей редакции SSOT (`SPEC_MTS_VOICE_AGENT.md`,
публичная база знаний МТС). В коммите `60546a6` этот файл переименован в
`SPEC_MTS_VOICE_AGENT_TRACK1.md` и переписан под трек 1: мультиарендный агент
входящих звонков для бизнес-клиентов. Нумерация разделов §1–§18 сохранилась, но
содержание §6 стало tenant-scoped. По правилу разрешения конфликтов (декомпозиция §0, §9)
приоритет имеет SSOT.

В спецификации №2 у задач нет идентификаторов. Для трассируемости им присвоены ID
вида `MLB-<область>-<номер>` со ссылкой на строки раздела 4 спецификации №2.

## Решения по противоречиям

| ID | Противоречие | Решение |
|---|---|---|
| C1 | Спецификация №2 ссылается на `SPEC_MTS_VOICE_AGENT.md`, которого больше нет. | Нормативной считается `SPEC_MTS_VOICE_AGENT_TRACK1.md` v1.1. |
| C2 | Миссия «база публичной клиентской информации МТС» (спецификация №2, §4) против tenant-scoped источников (SSOT §1, §2.4, §6.1, §18.4). | Корпус `mts.by` живёт только в изолированном tenant `mts-public-demo` (`config/legacy_demo_sources.mts.by.yaml`, `trust_level=legacy_demo_fixture`). Бизнес-tenants описываются в `config/sources.by_tenant.yaml`. Загрузчик реестра запрещает смешивать эти два файла и использовать хосты `mts.by` в бизнес-tenant. |
| C3 | Контракт `retrieve(query, filters, top_k)` (спецификация №2, Этап 0) против SSOT §14.2. | Сигнатура взята из SSOT дословно: `retrieve(query, *, tenant_id, language, audience, filters, index_revision, deadline_ms)`. `top_k` не входит в сигнатуру; используются параметры `RetrievalConfig` из §6.7 (`dense_top_k=30`, `sparse_top_k=30`, `rrf_top_k=30`, `rerank_top_k=20`, `context_top_k=6`). `RetrievalFilters` не содержит `tenant_id`, `language` и `audience`, чтобы у этих значений был один источник; фактически применённые фильтры возвращаются в `RetrievalResult.applied_filters`. |
| C4 | Каталоги `rag/` и `knowledge/` (спецификация №2) против структуры SSOT §13. | По SSOT §13: `packages/rag` (поиск и fusion), `apps/ingestion` (реестр, URL-политика, robots; далее краулер и пайплайн), `packages/contracts/knowledge` (Pydantic-контракты в namespace-пакете `mts_contracts`). |
| C5 | Не определено, кто владеет миграциями `knowledge_documents/revisions/chunks/ingestion_runs` (SSOT §8.3 против спецификации №2, задачи Backend + ML-Flow). | В группе 1 нет PostgreSQL. Контракты не зависят от способа хранения; слой хранения блокирован до решения. |
| C6 | SSOT §17 включает `https://ihelper.mts.by/selfcare/`, а §6.2.3 запрещает `/selfcare` и вход в Интернет-помощник. | URL есть в реестре со `status: excluded`, `approval: rejected` и причиной. `lk.landing.mts.by` (хост с меткой личного кабинета), `shop.mts.by` (корзина и checkout, риск crawler trap) и `help.mts.by` (виджет поддержки и формы) получают `review_required` до live dry-run. |

## Решения по дизайну

1. **Изолированные пакеты.** Решение пользователя: каждый пакет имеет свой
   `pyproject.toml`, корневых файлов workspace нет. Корневой каркас и CI принадлежат роли
   Backend + ML-Flow. Окружение — conda `mach` (Python 3.12). Пакеты
   ставятся вместе через `pip install --no-deps --no-build-isolation -e ...`, чтобы локальные
   имена никогда не искались в PyPI.
2. **Контракты строгие.** Модели frozen, `extra="forbid"`. Все 21 поле SSOT §6.5 у
   `ChunkMetadata` обязательны, datetime только с часовым поясом и приводятся к UTC.
   Множества хранятся как отсортированные кортежи, чтобы сериализация была детерминированной
   (ключ кэша по §6.7.8).
3. **Изоляция tenant (FR-09, NFR-11).** `tenant_id` — строгий slug без нормализации.
   Retriever читает только bucket `(tenant_id, index_revision)`, дополнительно проверяет
   результат (`TenantIsolationError`), а `RetrievalResult` отвергает чужие chunks.
   На неизвестную ревизию и ревизию чужого tenant возвращается одинаковая ошибка,
   чтобы не раскрывать существование чужих данных.
4. **Псевдоним `"active"`.** `index_revision="active"` разрешается в текущую активную
   ревизию tenant. Результат всегда содержит конкретную ревизию (NFR-06).
5. **`EvidenceStatus`** — `sufficient`, `no_evidence`, `low_relevance`, `evidence_conflict`
   (§7.2), `stale_only` (§6.3). Пустой или слабый результат — штатный исход, а не исключение.
   Отвечать по фактам можно только при `sufficient`; маппинг на `answer_status` LLM описан
   в `packages/rag/README.md`.
6. **Идентичность документа.** `document_id = sha256("mts-doc-v1" | tenant_id | canonical_url)`.
   Canonicalization удаляет tracking-параметры и fragment, но сохраняет смысловые параметры.
   Изменение правил canonicalization меняет `document_id`, поэтому требует нового ADR и плана
   миграции (`CANONICALIZATION_VERSION`).
7. **Нормализация текста для `content_hash`** — NFC, а не NFKC, чтобы не искажать `№`, дроби и
   цены. Регистр, цифры и пунктуация сохраняются.
8. **robots.txt** — собственный парсер по RFC 9309 (выигрывает самое длинное правило,
   при равенстве — Allow, поддержаны `*` и `$`). Stdlib `urllib.robotparser` применяет
   первое совпавшее правило и может разрешить запрещённый путь. User-Agent краулера —
   обязательный параметр без значения по умолчанию.
9. **URL-политика (§6.2.3).** Разрешающие правила сужены (точный хост, префикс пути по границе
   сегмента). Запрещающие правила расширены (без учёта регистра, после декодирования,
   сравнение сегментов на равенство). URL с токенами исключаются целиком. В отчёты попадает
   только `redact_url(...)` (NFR-03).
10. **YAML реестров** загружается строгим `SafeLoader`: дубликаты ключей и anchors/aliases
    запрещены, лимит 1 MiB. Ошибки собираются все сразу и не содержат входных значений.
11. **Время.** Хранение в UTC. Даты окончания действия с белорусских страниц («до 31.10.2026»)
    в группе 2 должны конвертироваться в исключающий UTC-момент конца дня Europe/Minsk.

## Правки после независимого ревью группы 1

- Проверки запрета хоста выполняются и по сырому имени, и по IDNA/ASCII-свёртке
  (полноширинные метки вроде `ｌｋ` больше не обходят `personal_area_host`).
- Сегменты пути проверяются на JWT и длинный hex; в `redacted_url` они заменяются на
  `REDACTED`. Порог смешанного base64 может ложно срабатывать на title-case slug с цифрой
  и на MD5-папки CMS; это LOW-ограничение до появления реальных document-источников.
- `RetrievalResult.excluded_counts` — отсортированный кортеж пар `(reason, count)`, а не
  изменяемый `dict`. JSON-формат изменился с объекта на массив пар; persisted retrieval
  events ещё нет, миграции не требуются.
- `AbsoluteHttpUrl` отвергает userinfo.
- Canonicalization невалидных percent-байтов в query (`%FF` vs `%FE`) больше не схлопывает
  их в U+FFFD. Для валидного UTF-8 поведение не изменилось, `CANONICALIZATION_VERSION`
  остаётся 1.

- In-memory retriever (stub) работает только лексически: dense, reranker и Qdrant появятся
  в группе 3. Порог `min_relevance_score` не переносится между режимами, его калибрует
  MLB-GRD-01.
- Конфликт актуальных ревизий одного документа обнаруживается. Конфликт цен между разными
  документами отложен до MLB-GRD-02.
- `RetrievalResult.query_variants` содержит сырой пользовательский текст. Он исключён из `repr`,
  но в `retrieval_events` (Backend + ML-Flow) нужно сохранять только redacted-версию или hash.
- `LICENSES.md` (SSOT §16.6) — корневой файл; до появления общего каркаса лицензии
  зависимостей группы 1 (pydantic — MIT, PyYAML — MIT) перечислены здесь.

## Открытые вопросы

1. Кто утверждает изменения `mts_contracts.knowledge` после `schema_version=1`
   (ML + Backend или совместно с Backend + ML-Flow)?
2. C5: владение миграциями таблиц knowledge и ingestion runs.
3. Значение User-Agent product token краулера (нужно до группы 2).
4. Допустимость общего хоста у нескольких бизнес-tenants (сейчас — жёсткая ошибка).
