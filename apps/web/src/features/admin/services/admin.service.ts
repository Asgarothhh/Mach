import { apiRequest } from '../../../shared/api/http';
import { env } from '../../../shared/config/env';
import type { AdminSessionSummary } from '../../../shared/types/api';
import type { CallSummary } from '../../../shared/types/track1';
import { demoCallStore } from '../../calls/data/demoCalls';
import { demoLatencySpans } from '../data/demoData';

export interface CallAnalytics {
  total_calls: number;
  active_calls: number;
  error_rate: number | null;
  chat_handoff_rate: number | null;
  human_handoff_rate: number | null;
  ttfa_p50_ms: number | null;
  ttfa_p95_ms: number | null;
  route_counts: Record<'voice' | 'chat_offer' | 'human_handoff' | 'fallback', number>;
  top_intents: { intent: string; count: number }[];
  latency_spans: { name: string; p50_ms: number | null; p95_ms: number | null; status?: 'ok' | 'degraded' | 'unknown' }[];
}

export async function listAdminSessions(): Promise<AdminSessionSummary[]> {
  if (env.demoMode) return [];
  return apiRequest<AdminSessionSummary[]>('/admin/sessions');
}

export async function getCallAnalytics(tenantId: string): Promise<CallAnalytics> {
  if (!env.demoMode) {
    // The server derives and authorizes the tenant from the authenticated identity; tenantId is not an auth claim.
    // Response shape should be generated from the finalized backend OpenAPI schema.
    return apiRequest<CallAnalytics>('/admin/analytics/calls');
  }
  const calls = demoCallStore.filter((call) => call.tenant_id === tenantId);
  const count = (decision: CallSummary['route_decision']) => calls.filter((call) => call.route_decision === decision).length;
  const intentCounts = new Map<string, number>();
  calls.forEach((call) => intentCounts.set(call.intent, (intentCounts.get(call.intent) ?? 0) + 1));
  const ttfa = calls.map((call) => call.ttfa_ms).filter((value): value is number => value != null).sort((a, b) => a - b);
  const percentile = (p: number) => ttfa.length ? ttfa[Math.min(ttfa.length - 1, Math.ceil(ttfa.length * p) - 1)] : null;
  return {
    total_calls: calls.length,
    active_calls: calls.filter((call) => call.status === 'active').length,
    error_rate: calls.length ? calls.filter((call) => call.status === 'failed' || call.status === 'degraded').length / calls.length : 0,
    chat_handoff_rate: calls.length ? count('chat_offer') / calls.length : 0,
    human_handoff_rate: calls.length ? count('human_handoff') / calls.length : 0,
    ttfa_p50_ms: percentile(0.5), ttfa_p95_ms: percentile(0.95),
    route_counts: { voice: count('voice'), chat_offer: count('chat_offer'), human_handoff: count('human_handoff'), fallback: count('fallback') },
    top_intents: [...intentCounts.entries()].map(([intent, total]) => ({ intent, count: total })).sort((a, b) => b.count - a.count).slice(0, 5),
    latency_spans: demoLatencySpans,
  };
}
