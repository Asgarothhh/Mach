import { apiRequest } from '../../../shared/api/http';
import type { CreateSessionResponse } from '../../../shared/types/api';

/**
 * Contract from SPEC_MTS_VOICE_AGENT.md: POST /sessions returns session_id + short-lived media token.
 * Confirm the token field name with backend; response mapping stays isolated in this service.
 */
export async function createVoiceSession(): Promise<CreateSessionResponse> {
  const raw = await apiRequest<Record<string, unknown>>('/sessions', {
    method: 'POST',
    body: {},
  });

  const sessionId = raw.session_id;
  const token = raw.token ?? raw.media_token ?? raw.livekit_token;
  if (typeof sessionId !== 'string' || typeof token !== 'string') {
    throw new Error('Неподходящий ответ POST /sessions: ожидаются session_id и media token.');
  }

  return {
    session_id: sessionId,
    token,
    ...(typeof raw.expires_at === 'string' ? { expires_at: raw.expires_at } : {}),
  };
}

export async function endVoiceSession(sessionId: string): Promise<void> {
  await apiRequest<void>(`/sessions/${encodeURIComponent(sessionId)}/end`, {
    method: 'POST',
  });
}
