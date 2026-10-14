import { apiRequest } from '../../../shared/api/http';
import { resolveSessionTenantId } from '../../../shared/config/env';
import type { SourceCitation } from '../../../shared/types/api';
import type { SendTextMessageInput, SendTextMessageResult } from './chat.service';

let cachedSessionId: string | null = null;
let cachedTenantId: string | null = null;

type ApiTextTurnResponse = {
  answer_text?: unknown;
  answer?: unknown;
  response?: unknown;
  text?: unknown;
  message?: unknown;
  answer_status?: unknown;
  citations?: unknown;
  citation_ids?: unknown;
  sources?: unknown;
  fallback_reason?: unknown;
  evidence_status?: unknown;
  tenant_id?: unknown;
  result?: unknown;
  turn?: unknown;
  assistant_turn?: unknown;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function extractAnswer(payload: unknown): string | undefined {
  if (!isRecord(payload)) return typeof payload === 'string' ? payload : undefined;
  const direct = [payload.answer_text, payload.answer, payload.response, payload.text, payload.message]
    .find((value) => typeof value === 'string' && value.trim().length > 0);
  if (typeof direct === 'string') return direct;

  for (const key of ['result', 'turn', 'assistant_turn', 'data']) {
    const nested = extractAnswer(payload[key]);
    if (nested) return nested;
  }
  return undefined;
}

function mapSourceItem(item: unknown): SourceCitation | null {
  if (!isRecord(item)) return null;
  const id = item.chunk_id ?? item.id;
  const url = item.canonical_url ?? item.source_url ?? item.url;
  if (typeof id !== 'string' || typeof url !== 'string' || !id || !url) return null;
  return {
    id,
    title: typeof item.title === 'string' && item.title ? item.title : id,
    url,
    ...(typeof item.excerpt === 'string' ? { excerpt: item.excerpt } : {}),
  };
}

function extractCitations(payload: unknown): SourceCitation[] {
  if (!isRecord(payload)) return [];
  if (Array.isArray(payload.sources)) {
    const mapped = payload.sources.map(mapSourceItem).filter((item): item is SourceCitation => item !== null);
    if (mapped.length) return mapped;
  }
  const value = payload.citations;
  if (Array.isArray(value)) {
    return value.map(mapSourceItem).filter((item): item is SourceCitation => item !== null);
  }
  for (const key of ['result', 'turn', 'assistant_turn', 'data']) {
    const nested = extractCitations(payload[key]);
    if (nested.length) return nested;
  }
  return [];
}

function extractStringField(payload: unknown, field: 'fallback_reason' | 'evidence_status'): string | undefined {
  if (!isRecord(payload)) return undefined;
  const value = payload[field];
  if (typeof value === 'string' && value.trim()) return value;
  for (const key of ['result', 'turn', 'assistant_turn', 'data']) {
    const nested = extractStringField(payload[key], field);
    if (nested) return nested;
  }
  return undefined;
}

function extractCitationIds(payload: unknown): string[] {
  if (!isRecord(payload)) return [];
  const value = payload.citation_ids;
  if (Array.isArray(value)) return value.filter((id): id is string => typeof id === 'string');
  for (const key of ['result', 'turn', 'assistant_turn', 'data']) {
    const nested = extractCitationIds(payload[key]);
    if (nested.length) return nested;
  }
  return [];
}

function extractAnswerStatus(payload: unknown): SendTextMessageResult['answer_status'] {
  if (!isRecord(payload)) return undefined;
  const allowed = ['grounded', 'needs_clarification', 'no_evidence', 'handoff'] as const;
  if (typeof payload.answer_status === 'string' && allowed.includes(payload.answer_status as (typeof allowed)[number])) {
    return payload.answer_status as (typeof allowed)[number];
  }
  for (const key of ['result', 'turn', 'assistant_turn', 'data']) {
    const nested = extractAnswerStatus(payload[key]);
    if (nested) return nested;
  }
  return undefined;
}

export async function resetBackendTextSession(): Promise<void> {
  const sessionId = cachedSessionId;
  cachedSessionId = null;
  cachedTenantId = null;
  if (!sessionId) return;
  try {
    await apiRequest(`/sessions/${encodeURIComponent(sessionId)}/end`, { method: 'POST' });
  } catch {
    // Best-effort close; a missing or already-ended session must not block UI reset.
  }
}

async function getSessionId(preferredSessionId?: string, tenantId?: string): Promise<string> {
  if (preferredSessionId) return preferredSessionId;
  const resolvedTenant = resolveSessionTenantId(tenantId);
  if (cachedSessionId && cachedTenantId === resolvedTenant) return cachedSessionId;
  cachedSessionId = null;

  const created = await apiRequest<{ session_id?: unknown }>('/sessions', {
    method: 'POST',
    body: {
      tenant_id: resolvedTenant,
      channel: 'mock',
      language: 'ru',
    },
  });

  if (typeof created.session_id !== 'string' || !created.session_id) {
    throw new Error('Backend не вернул session_id при создании тестовой сессии.');
  }
  cachedSessionId = created.session_id;
  cachedTenantId = resolvedTenant;
  return created.session_id;
}

/**
 * Text-only integration for the current REST contract:
 * POST /api/v1/sessions, then POST /api/v1/sessions/{id}/turns/text.
 * This does not send microphone audio and does not represent real TTS playback.
 */
export async function sendBackendTextTest(input: SendTextMessageInput): Promise<SendTextMessageResult> {
  const sessionId = await getSessionId(input.sessionId || undefined, input.tenantId);
  const raw = await apiRequest<ApiTextTurnResponse>(
    `/sessions/${encodeURIComponent(sessionId)}/turns/text`,
    {
      method: 'POST',
      body: { text: input.text },
    },
  );

  const answer = extractAnswer(raw);
  if (!answer) {
    throw new Error('Backend принял текст, но в ответе нет распознаваемого поля ответа (answer_text/answer/response/text). Проверьте response schema в Swagger.');
  }

  return {
    answer_text: answer,
    tenant_id: typeof raw.tenant_id === 'string' ? raw.tenant_id : cachedTenantId ?? undefined,
    citation_ids: extractCitationIds(raw),
    citations: extractCitations(raw),
    answer_status: extractAnswerStatus(raw) ?? 'no_evidence',
    fallback_reason: extractStringField(raw, 'fallback_reason'),
    evidence_status: extractStringField(raw, 'evidence_status'),
  };
}
