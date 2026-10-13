import { apiRequest } from '../../../shared/api/http';
import { env } from '../../../shared/config/env';
import type { SourceCitation } from '../../../shared/types/api';
import type { SendTextMessageInput, SendTextMessageResult } from './chat.service';

let cachedSessionId: string | null = null;

type ApiTextTurnResponse = {
  answer_text?: unknown;
  answer?: unknown;
  response?: unknown;
  text?: unknown;
  message?: unknown;
  answer_status?: unknown;
  citations?: unknown;
  citation_ids?: unknown;
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

function extractCitations(payload: unknown): SourceCitation[] {
  if (!isRecord(payload)) return [];
  const value = payload.citations;
  if (Array.isArray(value)) {
    return value.filter((item): item is SourceCitation =>
      isRecord(item)
      && typeof item.id === 'string'
      && typeof item.title === 'string'
      && typeof item.url === 'string'
    );
  }
  for (const key of ['result', 'turn', 'assistant_turn', 'data']) {
    const nested = extractCitations(payload[key]);
    if (nested.length) return nested;
  }
  return [];
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

async function getSessionId(preferredSessionId?: string): Promise<string> {
  if (preferredSessionId) return preferredSessionId;
  if (cachedSessionId) return cachedSessionId;

  const created = await apiRequest<{ session_id?: unknown }>('/sessions', {
    method: 'POST',
    body: {
      tenant_id: env.backendTestTenantId,
      channel: 'mock',
      language: 'ru',
    },
  });

  if (typeof created.session_id !== 'string' || !created.session_id) {
    throw new Error('Backend не вернул session_id при создании тестовой сессии.');
  }
  cachedSessionId = created.session_id;
  return created.session_id;
}

/**
 * Text-only integration for the current REST contract:
 * POST /api/v1/sessions, then POST /api/v1/sessions/{id}/turns/text.
 * This does not send microphone audio and does not represent real TTS playback.
 */
export async function sendBackendTextTest(input: SendTextMessageInput): Promise<SendTextMessageResult> {
  const sessionId = await getSessionId(input.sessionId || undefined);
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
    citation_ids: extractCitationIds(raw),
    citations: extractCitations(raw),
    answer_status: extractAnswerStatus(raw) ?? 'no_evidence',
  };
}
