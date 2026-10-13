export interface CreateSessionResponse {
  session_id: string;
  /** Present only if LiveKit is configured. Never create tokens in the browser. */
  token?: string;
  expires_at?: string;
}

export interface ApiErrorPayload {
  detail?: string;
  code?: string;
  request_id?: string;
}

export interface SourceCitation {
  id: string;
  title: string;
  url: string;
  crawledAt?: string;
  revisionId?: string;
  excerpt?: string;
  trustLevel?: string;
  effectiveStatus?: 'active' | 'stale' | 'removed' | 'unknown';
}

export interface AdminSessionSummary {
  session_id: string;
  created_at: string;
  ended_at?: string;
  status: string;
  language?: string;
  intent?: string;
  turn_count?: number;
  latency_ms?: number;
  ttfa_p50_ms?: number | null;
  ttfa_p95_ms?: number | null;
  error_count?: number;
}

export interface AdminOverview {
  active_sessions: number;
  sessions_today: number;
  error_rate: number | null;
  handoff_rate: number | null;
  ttfa_p50_ms: number | null;
  ttfa_p95_ms: number | null;
}

export interface LatencySpan {
  name: string;
  p50_ms: number | null;
  p95_ms: number | null;
  status?: 'ok' | 'degraded' | 'unknown';
}

export interface IngestionRun {
  run_id: string;
  started_at: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'dry_run';
  added: number;
  changed: number;
  failed: number;
  active_index_revision?: string;
}
