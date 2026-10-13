import type { AdminSessionSummary, LatencySpan } from '../../../shared/types/api';

/** Every value below is synthetic and for the demo UI only. */
export const demoOverview = {
  activeSessions: 6,
  sessionsToday: 128,
  errorRate: '3,1%',
  handoffRate: '12,5%',
  ttfaP50: 640,
  ttfaP95: 1540,
  openRouterP50: 280,
  openRouterP95: 820,
  retrievalP50: 96,
  retrievalP95: 178,
  ttsP50: 90,
  ttsP95: 160,
};

export const demoSessions: AdminSessionSummary[] = [
  { session_id: 'demo-7f3a', created_at: '2026-10-11T14:32:00+03:00', ended_at: '2026-10-11T14:34:18+03:00', status: 'Завершена', language: 'ru', intent: 'roaming_preparation', turn_count: 4, latency_ms: 640, ttfa_p50_ms: 640, ttfa_p95_ms: 1540, error_count: 0 },
  { session_id: 'demo-81bc', created_at: '2026-10-11T14:31:12+03:00', status: 'Активна', language: 'ru', intent: 'tariff_info', turn_count: 2, latency_ms: 580, error_count: 0 },
  { session_id: 'demo-92df', created_at: '2026-10-11T14:28:04+03:00', status: 'Degraded', language: 'ru', intent: 'home_internet', turn_count: 5, latency_ms: 920, error_count: 1 },
  { session_id: 'demo-a104', created_at: '2026-10-11T14:25:18+03:00', status: 'Handoff', language: 'ru', intent: 'account_operation', turn_count: 2, latency_ms: null as unknown as number, error_count: 0 },
  { session_id: 'demo-b2c8', created_at: '2026-10-11T14:22:40+03:00', status: 'Завершена', language: 'be', intent: 'service_info', turn_count: 3, latency_ms: null as unknown as number, error_count: 0 },
  { session_id: 'demo-c3e0', created_at: '2026-10-11T14:19:32+03:00', status: 'Handoff', language: 'ru', intent: 'roaming_prices', turn_count: 1, latency_ms: 710, error_count: 0 },
  { session_id: 'demo-d4f1', created_at: '2026-10-11T14:15:09+03:00', status: 'Завершена', language: 'ru', intent: 'payment_info', turn_count: 4, latency_ms: 620, error_count: 0 },
  { session_id: 'demo-e502', created_at: '2026-10-11T14:10:27+03:00', status: 'Завершена', language: 'ru', intent: 'store_contacts', turn_count: 2, latency_ms: 590, error_count: 0 },
];

export const demoLatencySpans: LatencySpan[] = [
  { name: 'Final ASR', p50_ms: 70, p95_ms: 140, status: 'ok' },
  { name: 'Guardrails + routing', p50_ms: 20, p95_ms: 36, status: 'ok' },
  { name: 'Retrieval + rerank', p50_ms: 96, p95_ms: 178, status: 'ok' },
  { name: 'OpenRouter TTFT', p50_ms: 280, p95_ms: 820, status: 'degraded' },
  { name: 'TTS first chunk', p50_ms: 90, p95_ms: 160, status: 'ok' },
];

export const demoAuditEvents = [
  { time: '14:34:18', actor: 'system', event: 'session.closed', detail: 'Сессия demo-7f3a завершена' },
  { time: '14:33:31', actor: 'guardrails', event: 'handoff.required', detail: 'Операция вне scope: изменение тарифа' },
  { time: '14:32:29', actor: 'rag', event: 'retrieval.completed', detail: 'Выбраны 6 фрагментов, индекс kb-2026-10-11.2' },
  { time: '14:32:05', actor: 'guardrails', event: 'input.checked', detail: 'PII: не обнаружены; политика guardrails-v1' },
  { time: '14:32:00', actor: 'system', event: 'session.created', detail: 'Синтетическая сессия, язык ru' },
];
