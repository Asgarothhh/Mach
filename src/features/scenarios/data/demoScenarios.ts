import type { ScenarioProfile } from '../../../shared/types/track1';

export const demoScenarioStore: ScenarioProfile[] = [
  {
    scenario_id: 'scenario-welcome', tenant_id: 'demo-business-01', revision_id: 'greeting-r3', name: 'Приветствие и первичная классификация', description: 'Базовый маршрут для каждого нового входящего обращения.', intent: 'general_question', instructions: 'Выясни суть обращения одним уточняющим вопросом. Кратко объясняй только проверенные сведения и не обещай действий, которые не были подтверждены интеграцией.', greeting: 'Здравствуйте! Вы позвонили в компанию. Я голосовой помощник. Разговор может обрабатываться для подготовки ответа согласно уведомлению. Чем могу помочь?', fallback_text: 'Не хочу давать неточную информацию. Могу предложить чат или перевести вас на сотрудника.', status: 'published', updated_at: '2026-10-13T09:00:00+03:00', rules: [
      { rule_id: 'welcome-standard', label: 'Стандартный вопрос', match_description: 'Короткий вопрос по утверждённым услугам и FAQ', decision: 'voice', enabled: true, priority: 1 },
      { rule_id: 'welcome-complex', label: 'Сложный / длинный вопрос', match_description: 'Нужно приложить документы или ответ требует подробностей', decision: 'chat_offer', enabled: true, priority: 2 },
      { rule_id: 'welcome-human', label: 'Просьба о человеке', match_description: 'Звонящий просит оператора или сотрудника', decision: 'human_handoff', enabled: true, priority: 0 },
    ]
  },
  {
    scenario_id: 'scenario-pricing', tenant_id: 'demo-business-01', revision_id: 'pricing-r1', name: 'Вопросы о стоимости и сроках', description: 'Обрабатывает вопросы, где важно подтвердить источник и актуальность.', intent: 'pricing_question', instructions: 'Не называй стоимость, сроки или наличие, если значения не подтверждены активным tenant-источником. При конфликте источников предложи сотрудника.', greeting: 'Подскажу по стоимости и срокам на основе актуальной информации компании.', fallback_text: 'Сейчас не могу подтвердить эти условия. Предлагаю уточнить у сотрудника компании.', status: 'draft', updated_at: '2026-10-12T16:20:00+03:00', rules: [
      { rule_id: 'pricing-grounded', label: 'Есть подтверждённый источник', match_description: 'Актуальный approved source найден', decision: 'voice', enabled: true, priority: 1 },
      { rule_id: 'pricing-no-evidence', label: 'Источник отсутствует или устарел', match_description: 'Нет доказательств, источник stale или конфликтует', decision: 'human_handoff', enabled: true, priority: 0 },
    ]
  },
];
