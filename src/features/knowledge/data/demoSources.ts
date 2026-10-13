import type { SourceCitation } from '../../../shared/types/api';

/** Tenant-scoped synthetic company fixtures. Not real company content and not an ingestion result. */
export const demoSources: SourceCitation[] = [
  {
    id: 'S1', title: 'Краткая информация о компании', url: 'https://example.com/company/about',
    crawledAt: 'Демо fixture', revisionId: 'company-about-r1', excerpt: 'Синтетическая карточка услуги и общая информация, добавленная только для демонстрации интерфейса.',
    trustLevel: 'synthetic_unapproved_fixture', effectiveStatus: 'active',
  },
  {
    id: 'S2', title: 'Вопросы и ответы', url: 'https://example.com/company/faq',
    crawledAt: 'Демо fixture', revisionId: 'company-faq-r1', excerpt: 'Синтетический FAQ для тестирования grounding, источников и безопасного fallback.',
    trustLevel: 'synthetic_unapproved_fixture', effectiveStatus: 'active',
  },
];

export const demoAnswer = 'По демонстрационной справке могу кратко объяснить основные услуги компании. Для точной стоимости, сроков или специальных условий нужно подтвердить информацию в актуальном одобренном источнике. Если данных недостаточно, предложу уточнение, чат или передачу сотруднику.';
