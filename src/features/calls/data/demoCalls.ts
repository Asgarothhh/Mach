import type { CallDetail, CallSummary, RoutingEvent, SourceReference, TranscriptTurn } from '../../../shared/types/track1';

const tenant = 'demo-business-01';
const demoSources: SourceReference[] = [
  { source_id: 'src-brief', title: 'Краткая информация о компании', url: 'https://example.com/about', revision_id: 'demo-doc-r2', approved: false, excerpt: 'Синтетический источник для отображения UI. Не является одобренным источником бизнес-ответа.' },
  { source_id: 'src-faq', title: 'Вопросы и ответы', url: 'https://example.com/faq', revision_id: 'demo-faq-r1', approved: false, excerpt: 'Синтетический FAQ для проверки интерфейса и маршрутизации; не использовать как фактическое доказательство.' },
];

const baseCalls: CallSummary[] = [
  { call_id: 'call-d7f3a', session_id: 'session-d7f3a', tenant_id: tenant, created_at: '2026-10-13T09:42:00+03:00', ended_at: '2026-10-13T09:44:18+03:00', status: 'completed', channel: 'telephone', caller_alias: 'Входящий · •• 41', language: 'ru', intent: 'service_question', route_decision: 'voice', consent_state: 'accepted', duration_seconds: 138, turn_count: 4, ttfa_ms: 620 },
  { call_id: 'call-a81bc', session_id: 'session-a81bc', tenant_id: tenant, created_at: '2026-10-13T09:31:12+03:00', status: 'active', channel: 'telephone', caller_alias: 'Входящий · •• 08', language: 'ru', intent: 'pricing_question', route_decision: 'voice', consent_state: 'accepted', turn_count: 2, ttfa_ms: 580 },
  { call_id: 'call-b92df', session_id: 'session-b92df', tenant_id: tenant, created_at: '2026-10-13T09:28:04+03:00', ended_at: '2026-10-13T09:31:11+03:00', status: 'degraded', channel: 'test_call', caller_alias: 'Тестовый звонок', language: 'ru', intent: 'complex_request', route_decision: 'chat_offer', consent_state: 'accepted', duration_seconds: 187, turn_count: 5, ttfa_ms: 920, error_code: 'chat_not_configured' },
  { call_id: 'call-c104a', session_id: 'session-c104a', tenant_id: tenant, created_at: '2026-10-13T09:25:18+03:00', ended_at: '2026-10-13T09:26:30+03:00', status: 'handoff', channel: 'telephone', caller_alias: 'Входящий · •• 72', language: 'ru', intent: 'human_requested', route_decision: 'human_handoff', consent_state: 'accepted', duration_seconds: 72, turn_count: 2 },
  { call_id: 'call-b2c8e', session_id: 'session-b2c8e', tenant_id: tenant, created_at: '2026-10-13T09:22:40+03:00', ended_at: '2026-10-13T09:23:58+03:00', status: 'completed', channel: 'telephone', caller_alias: 'Входящий · •• 15', language: 'ru', intent: 'opening_hours', route_decision: 'voice', consent_state: 'accepted', duration_seconds: 78, turn_count: 3, ttfa_ms: 590 },
  { call_id: 'call-c3e0f', session_id: 'session-c3e0f', tenant_id: tenant, created_at: '2026-10-13T09:19:32+03:00', ended_at: '2026-10-13T09:22:12+03:00', status: 'completed', channel: 'telephone', caller_alias: 'Входящий · •• 66', language: 'ru', intent: 'complex_request', route_decision: 'chat_offer', consent_state: 'accepted', duration_seconds: 160, turn_count: 3, ttfa_ms: 710 },
  { call_id: 'call-d4f10', session_id: 'session-d4f10', tenant_id: tenant, created_at: '2026-10-13T09:15:09+03:00', ended_at: '2026-10-13T09:16:52+03:00', status: 'completed', channel: 'telephone', caller_alias: 'Входящий · •• 29', language: 'ru', intent: 'service_question', route_decision: 'voice', consent_state: 'accepted', duration_seconds: 103, turn_count: 4, ttfa_ms: 620 },
  { call_id: 'call-e502a', session_id: 'session-e502a', tenant_id: tenant, created_at: '2026-10-13T09:10:27+03:00', ended_at: '2026-10-13T09:11:12+03:00', status: 'completed', channel: 'test_call', caller_alias: 'Тестовый звонок', language: 'ru', intent: 'general_question', route_decision: 'voice', consent_state: 'not_required_demo', duration_seconds: 45, turn_count: 2, ttfa_ms: 540 },
];

const turnsByCall: Record<string, TranscriptTurn[]> = {
  'call-d7f3a': [
    { turn_id: 'turn-d7-1', sequence_no: 1, role: 'system', text: 'Воспроизведено уведомление об обработке звонка · consent accepted', status: 'final', started_at: '2026-10-13T09:42:00+03:00' },
    { turn_id: 'turn-d7-2', sequence_no: 2, role: 'caller', text: 'Здравствуйте, расскажите, какие услуги вы оказываете.', status: 'final', started_at: '2026-10-13T09:42:12+03:00', confidence: 0.96 },
    { turn_id: 'turn-d7-3', sequence_no: 3, role: 'agent', text: 'Здравствуйте! Могу кратко рассказать об основных услугах компании на основе утверждённой справки.', status: 'final', started_at: '2026-10-13T09:42:13+03:00', citations: demoSources },
    { turn_id: 'turn-d7-4', sequence_no: 4, role: 'caller', text: 'Пришлите, пожалуйста, подробности в чат.', status: 'final', started_at: '2026-10-13T09:43:05+03:00', confidence: 0.92 },
    { turn_id: 'turn-d7-5', sequence_no: 5, role: 'agent', text: 'Могу предложить продолжить в настроенном чате. Перед передачей контекста требуется ваше согласие.', status: 'final', started_at: '2026-10-13T09:43:06+03:00' },
  ],
  'call-b92df': [
    { turn_id: 'turn-b9-1', sequence_no: 1, role: 'caller', text: 'У меня нестандартный вопрос по срокам и стоимости.', status: 'final', started_at: '2026-10-13T09:28:15+03:00', confidence: 0.81 },
    { turn_id: 'turn-b9-2', sequence_no: 2, role: 'agent', text: 'Чтобы не дать неточную информацию, предлагаю продолжить в чате, где можно разобрать детали.', status: 'final', started_at: '2026-10-13T09:28:17+03:00' },
  ],
};

const routingByCall: Record<string, RoutingEvent[]> = {
  'call-d7f3a': [
    { event_id: 'route-d7-1', created_at: '2026-10-13T09:42:00+03:00', decision: 'voice', reason: 'Стандартный информационный запрос', policy_revision: 'routing-r3', consent_state: 'accepted', outcome: 'Голосовой ответ завершён' },
    { event_id: 'route-d7-2', created_at: '2026-10-13T09:43:07+03:00', decision: 'chat_offer', reason: 'Звонящий попросил подробности в чате', policy_revision: 'routing-r3', consent_state: 'accepted', outcome: 'Предложение показано; реальная доставка не симулируется как успешная' },
  ],
  'call-b92df': [
    { event_id: 'route-b9-1', created_at: '2026-10-13T09:28:20+03:00', decision: 'chat_offer', reason: 'Сложность выше порога tenant policy', policy_revision: 'routing-r3', consent_state: 'accepted', outcome: 'В демо провайдер чата не настроен' },
  ],
};

export const demoCallStore: CallSummary[] = [...baseCalls];

export function buildDemoCallDetail(callId: string, tenantId: string): CallDetail | null {
  // Demo ownership is enforced too; this is a fixture guard, not a substitute for backend authorization.
  const call = demoCallStore.find((item) => (item.call_id === callId || item.session_id === callId) && item.tenant_id === tenantId);
  if (!call) return null;
  const sourcesForCall = call.tenant_id === tenant ? demoSources : [];
  const turns = turnsByCall[call.call_id] ?? [
    { turn_id: `${call.call_id}-turn-1`, sequence_no: 1, role: 'caller' as const, text: 'Здравствуйте, расскажите, пожалуйста, подробнее.', status: 'final' as const, started_at: call.created_at, confidence: 0.91 },
    { turn_id: `${call.call_id}-turn-2`, sequence_no: 2, role: 'agent' as const, text: 'Могу помочь по утверждённому сценарию компании. Если данных недостаточно, предложу уточнение или передачу человеку.', status: 'final' as const, started_at: call.ended_at ?? call.created_at, citations: sourcesForCall },
  ];
  return {
    call,
    turns: turns.map((turn) => ({ ...turn, citations: turn.citations ? [...turn.citations] : undefined })),
    routing_events: routingByCall[call.call_id] ?? [{ event_id: `${call.call_id}-route-1`, created_at: call.created_at, decision: call.route_decision, reason: 'Решение демонстрационной routing policy', policy_revision: 'routing-r3', consent_state: call.consent_state, outcome: call.route_decision === 'human_handoff' ? 'Путь handoff показан как синтетический пример' : 'Демо-событие' }],
    sources: sourcesForCall,
    audio_recorded: false,
    transcript_revision: 'transcript-r1',
  };
}

export function addDemoTestCall(tenantId: string, displayName: string, adapter: 'mock' | 'sip'): CallSummary {
  const id = `call-test-${Math.random().toString(36).slice(2, 7)}`;
  const call: CallSummary = {
    call_id: id,
    session_id: id.replace('call-', 'session-'),
    tenant_id: tenantId,
    created_at: new Date().toISOString(),
    ended_at: new Date().toISOString(),
    status: 'completed',
    channel: 'test_call',
    caller_alias: `${adapter === 'mock' ? 'Mock' : 'SIP test'} · ${displayName}`,
    language: 'ru',
    intent: 'onboarding_test_call',
    route_decision: 'voice',
    consent_state: 'not_required_demo',
    duration_seconds: 19,
    turn_count: 2,
    ttfa_ms: 580,
  };
  demoCallStore.unshift(call);
  turnsByCall[call.call_id] = [
    { turn_id: `${id}-caller`, sequence_no: 1, role: 'caller', text: 'Это тестовый входящий звонок. Проверьте, пожалуйста, сценарий.', status: 'final', started_at: call.created_at, confidence: 0.98 },
    { turn_id: `${id}-agent`, sequence_no: 2, role: 'agent', text: `Здравствуйте! Вы дозвонились в демонстрационный профиль «${displayName}». Это синтетический тестовый ответ.`, status: 'final', started_at: call.created_at },
  ];
  return call;
}

export function saveDemoTranscriptCorrection(callId: string, tenantId: string, turnId: string, correctedText: string, reason: string): CallDetail | null {
  const detail = buildDemoCallDetail(callId, tenantId);
  if (!detail) return null;
  const index = detail.turns.findIndex((turn) => turn.turn_id === turnId);
  if (index < 0) return detail;
  const turn = detail.turns[index];
  const before = turn.original_text ?? turn.text;
  const correctedAt = new Date().toISOString();
  detail.turns[index] = {
    ...turn,
    original_text: before,
    text: correctedText,
    status: 'corrected',
    correction_reason: reason,
    correction_audit: { audit_event_id: `audit-demo-${Date.now().toString(36)}`, actor_id: 'demo-support-supervisor', corrected_at: correctedAt, diff: { before, after: correctedText } },
  };
  // Keep the correction in the demo fixture so it remains visible while navigating during this session.
  turnsByCall[detail.call.call_id] = detail.turns;
  return { ...detail, transcript_revision: `transcript-r${Date.now()}` };
}
