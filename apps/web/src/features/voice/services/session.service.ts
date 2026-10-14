import { apiRequest } from '../../../shared/api/http';
import { resolveSessionTenantId } from '../../../shared/config/env';
import type { CreateSessionResponse } from '../../../shared/types/api';

/**
 * Current backend contract (SSOT §9 on main): POST /sessions returns session_id.
 * A LiveKit/media token is BLOCKED until LiveKit is in Compose. The WS mock
 * channel uses session_id only.
 */
export async function createVoiceSession(tenantId?: string): Promise<CreateSessionResponse> {
  const raw = await apiRequest<Record<string, unknown>>('/sessions', {
    method: 'POST',
    body: {
      tenant_id: resolveSessionTenantId(tenantId),
      channel: 'webrtc',
      language: 'ru',
    },
  });

  const sessionId = raw.session_id;
  if (typeof sessionId !== 'string' || !sessionId) {
    throw new Error('Неподходящий ответ POST /sessions: ожидается session_id.');
  }
  const tokenValue = raw.token ?? raw.media_token ?? raw.livekit_token;

  return {
    session_id: sessionId,
    ...(typeof tokenValue === 'string' && tokenValue ? { token: tokenValue } : {}),
  };
}

export async function endVoiceSession(sessionId: string): Promise<void> {
  await apiRequest<void>(`/sessions/${encodeURIComponent(sessionId)}/end`, {
    method: 'POST',
  });
}
