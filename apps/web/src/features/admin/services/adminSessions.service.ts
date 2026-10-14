import { apiRequest } from '../../../shared/api/http';
import { env } from '../../../shared/config/env';

export interface BackendHealthStatus {
  live: boolean;
  ready: boolean;
}

export async function checkBackendHealth(): Promise<BackendHealthStatus> {
  const apiOrigin = env.apiBaseUrl.replace(/\/api\/v1$/i, '');
  const check = async (path: 'live' | 'ready') => {
    try {
      const response = await fetch(`${apiOrigin}/health/${path}`, { headers: { Accept: 'application/json' } });
      return response.ok;
    } catch {
      return false;
    }
  };
  const [live, ready] = await Promise.all([check('live'), check('ready')]);
  return { live, ready };
}

export type SessionStatus =
  | 'CREATED'
  | 'CONNECTING'
  | 'NOTICE_PENDING'
  | 'LISTENING'
  | 'ENDPOINT_PENDING'
  | 'TRANSCRIBING_FINAL'
  | 'ROUTING'
  | 'RETRIEVING'
  | 'GENERATING'
  | 'SPEAKING'
  | 'INTERRUPTED'
  | 'DEGRADED'
  | 'CHAT_HANDOFF'
  | 'HUMAN_HANDOFF'
  | 'CLOSED';

export interface BackendSessionSummary {
  session_id: string;
  tenant_id?: string;
  status: SessionStatus;
  channel?: string;
  language?: string;
  created_at: string;
  ended_at?: string | null;
  turn_count?: number;
}

export interface BackendTurn {
  turn_id: string;
  sequence_no: string;
  started_at: string;
  redacted_text?: string | null;
  intent?: string | null;
}

export interface BackendSessionDetail extends BackendSessionSummary {
  tenant_id: string;
  channel: string;
  turns: BackendTurn[];
}

export interface HandoffResponse {
  session_id: string;
  status: string;
  handoff_type: string;
  chat_link?: string | null;
  message: string;
}

export interface SessionListFilters {
  tenantId?: string;
  status?: SessionStatus | '';
  limit?: number;
  offset?: number;
}

export async function createBackendSession(input: { tenant_id: string; channel: string; language: string }): Promise<BackendSessionSummary> {
  return apiRequest<BackendSessionSummary>('/sessions', { method: 'POST', body: input });
}

export async function listBackendSessions(filters: SessionListFilters = {}): Promise<BackendSessionSummary[]> {
  const params = new URLSearchParams();
  if (filters.tenantId) params.set('tenant_id', filters.tenantId);
  if (filters.status) params.set('status', filters.status);
  params.set('limit', String(Math.min(100, Math.max(1, filters.limit ?? 20))));
  params.set('offset', String(Math.max(0, filters.offset ?? 0)));
  return apiRequest<BackendSessionSummary[]>(`/admin/sessions?${params.toString()}`);
}

export async function getBackendSession(sessionId: string): Promise<BackendSessionDetail> {
  return apiRequest<BackendSessionDetail>(`/admin/sessions/${encodeURIComponent(sessionId)}`);
}

export async function correctBackendTranscript(
  sessionId: string,
  input: { turn_id: string; corrected_text: string; reason: string },
): Promise<void> {
  await apiRequest<unknown>(`/admin/sessions/${encodeURIComponent(sessionId)}/transcript-corrections`, {
    method: 'POST',
    body: input,
  });
}

export async function endBackendSession(sessionId: string): Promise<void> {
  await apiRequest<unknown>(`/sessions/${encodeURIComponent(sessionId)}/end`, { method: 'POST' });
}

export async function handoffBackendSessionToHuman(sessionId: string): Promise<HandoffResponse> {
  return apiRequest<HandoffResponse>(`/sessions/${encodeURIComponent(sessionId)}/handoff/human`, { method: 'POST' });
}

export async function handoffBackendSessionToChat(sessionId: string): Promise<HandoffResponse> {
  return apiRequest<HandoffResponse>(`/sessions/${encodeURIComponent(sessionId)}/handoff/chat`, { method: 'POST' });
}

export const sessionStatusLabels: Record<SessionStatus, string> = {
  CREATED: 'Создана',
  CONNECTING: 'Подключение',
  NOTICE_PENDING: 'Ожидание согласия',
  LISTENING: 'Слушает',
  ENDPOINT_PENDING: 'Ожидание конца реплики',
  TRANSCRIBING_FINAL: 'Финальная расшифровка',
  ROUTING: 'Маршрутизация',
  RETRIEVING: 'Поиск знаний',
  GENERATING: 'Генерация ответа',
  SPEAKING: 'Ответ голосом',
  INTERRUPTED: 'Прервано',
  DEGRADED: 'Деградация',
  CHAT_HANDOFF: 'Передана в чат',
  HUMAN_HANDOFF: 'Передана оператору',
  CLOSED: 'Завершена',
};

export function sessionStatusTone(status: SessionStatus): 'neutral' | 'success' | 'warning' | 'danger' {
  if (status === 'CLOSED') return 'success';
  if (status === 'DEGRADED') return 'danger';
  if (status === 'HUMAN_HANDOFF' || status === 'CHAT_HANDOFF' || status === 'INTERRUPTED') return 'warning';
  return 'neutral';
}

export function isTerminalSessionStatus(status: SessionStatus): boolean {
  return status === 'CLOSED' || status === 'HUMAN_HANDOFF' || status === 'CHAT_HANDOFF';
}
