import { apiRequest } from '../../../shared/api/http';
import { env } from '../../../shared/config/env';
import type { CallDetail, CallSummary, TranscriptCorrectionInput } from '../../../shared/types/track1';
import { buildDemoCallDetail, demoCallStore, saveDemoTranscriptCorrection } from '../data/demoCalls';

export interface CallFilters {
  tenantId?: string;
  query?: string;
  status?: string;
  route?: string;
  channel?: string;
  from?: string;
  to?: string;
  intent?: string;
  page?: number;
  pageSize?: number;
  scope?: 'tenant' | 'admin';
}

export interface CallListResult {
  items: CallSummary[];
  total: number;
  page: number;
  page_size: number;
}

export async function listCalls(filters: CallFilters = {}): Promise<CallListResult> {
  const page = Math.max(1, filters.page ?? 1);
  const pageSize = Math.min(100, Math.max(1, filters.pageSize ?? 8));
  if (env.backendAdminSessions) {
    const params = new URLSearchParams({ limit: '100' });
    params.set('tenant_id', env.backendTestTenantId);
    const sessions = await apiRequest<Array<{session_id: string; tenant_id?: string; status: string; created_at: string; ended_at?: string | null; channel?: string; language?: string; turn_count?: number}>>(`/admin/sessions?${params.toString()}`);
    const items: CallSummary[] = sessions.map((session): CallSummary => ({
      call_id: session.session_id,
      session_id: session.session_id,
      tenant_id: session.tenant_id ?? env.backendTestTenantId,
      created_at: session.created_at,
      ...(session.ended_at ? { ended_at: session.ended_at } : {}),
      status: ['CLOSED', 'closed'].includes(session.status) ? 'completed' : ['DEGRADED', 'degraded'].includes(session.status) ? 'degraded' : ['HUMAN_HANDOFF', 'CHAT_HANDOFF', 'HANDOFF'].includes(session.status) ? 'handoff' : 'active',
      channel: 'test_call',
      caller_alias: 'Локальный test call',
      language: (session.language === 'be' || session.language === 'en' ? session.language : 'ru'),
      intent: 'general_question',
      route_decision: 'voice',
      consent_state: 'not_required_demo',
      turn_count: session.turn_count ?? 0,
      ttfa_ms: undefined,
    }));
    const query = (filters.query ?? '').trim().toLowerCase();
    const filtered = items.filter((call) => {
      const matchesQuery = !query || `${call.call_id} ${call.intent}`.toLowerCase().includes(query);
      const matchesStatus = !filters.status || filters.status === 'all' || call.status === filters.status;
      return matchesQuery && matchesStatus;
    });
    const start = (page - 1) * pageSize;
    return { items: filtered.slice(start, start + pageSize), total: filtered.length, page, page_size: pageSize };
  }
  if (env.demoMode) {
    const query = (filters.query ?? '').toLowerCase().trim();
    const filtered = demoCallStore.filter((call) => {
      const matchTenant = !filters.tenantId || call.tenant_id === filters.tenantId;
      const matchQuery = !query || `${call.call_id} ${call.caller_alias} ${call.intent}`.toLowerCase().includes(query);
      const matchStatus = !filters.status || filters.status === 'all' || call.status === filters.status;
      const matchRoute = !filters.route || filters.route === 'all' || call.route_decision === filters.route;
      const matchChannel = !filters.channel || filters.channel === 'all' || call.channel === filters.channel;
      const matchIntent = !filters.intent || filters.intent === 'all' || call.intent === filters.intent;
      const callDate = new Date(call.created_at).getTime();
      const fromDate = filters.from ? new Date(`${filters.from}T00:00:00`).getTime() : null;
      const toDate = filters.to ? new Date(`${filters.to}T23:59:59.999`).getTime() : null;
      const matchFrom = fromDate === null || callDate >= fromDate;
      const matchTo = toDate === null || callDate <= toDate;
      return matchTenant && matchQuery && matchStatus && matchRoute && matchChannel && matchIntent && matchFrom && matchTo;
    });
    const start = (page - 1) * pageSize;
    return { items: filtered.slice(start, start + pageSize), total: filtered.length, page, page_size: pageSize };
  }

  return { items: [], total: 0, page, page_size: pageSize };
}

export async function getCallDetail(
  resourceId: string,
  tenantId: string,
  scope: 'tenant' | 'admin' = 'tenant',
): Promise<CallDetail | null> {
  void scope;
  if (!env.backendAdminSessions) {
    if (env.demoMode) return buildDemoCallDetail(resourceId, tenantId);
    return null;
  }
  const detail = await apiRequest<{
    session_id: string;
    tenant_id?: string;
    status: string;
    channel?: string;
    created_at: string;
    turns?: Array<{ turn_id: string; sequence_no?: string | number; redacted_text?: string | null; intent?: string | null; started_at?: string }>;
  }>(`/admin/sessions/${encodeURIComponent(resourceId)}`);
  const turns = detail.turns ?? [];
  const callSummary: CallSummary = {
    call_id: resourceId, session_id: resourceId, tenant_id: detail.tenant_id ?? env.backendTestTenantId,
    created_at: detail.created_at ?? turns[0]?.started_at ?? new Date().toISOString(), status: 'completed', channel: 'test_call',
    caller_alias: 'Локальный test call', language: 'ru', intent: 'general_question', route_decision: 'voice',
    consent_state: 'not_required_demo', turn_count: turns.length,
  };
  return {
    call: callSummary,
    turns: turns.map((turn, index) => ({
      turn_id: turn.turn_id,
      sequence_no: Number(turn.sequence_no) || index + 1,
      role: 'caller',
      text: turn.redacted_text ?? '',
      status: 'final',
      started_at: turn.started_at ?? detail.created_at,
    })),
    routing_events: [], sources: [], audio_recorded: false, transcript_revision: 'backend-demo-r1',
    permissions: { can_correct_transcript: false, can_view_original: false, can_export: false },
  };
}

export async function correctCallTranscript(
  callId: string,
  lookupId: string,
  tenantId: string,
  input: TranscriptCorrectionInput,
  scope: 'tenant' | 'admin' = 'tenant',
): Promise<CallDetail | null> {
  if (env.backendTextTest) throw new Error('Коррекция транскрипта ещё не реализована в загруженном backend. Здесь доступен только просмотр тестовых ходов.');
  if (env.demoMode) return saveDemoTranscriptCorrection(lookupId, tenantId, input.turn_id, input.corrected_text, input.reason);
  await apiRequest<unknown>(`/admin/sessions/${encodeURIComponent(callId)}/transcript-corrections`, { method: 'POST', body: input });
  return getCallDetail(lookupId, tenantId, scope);
}
