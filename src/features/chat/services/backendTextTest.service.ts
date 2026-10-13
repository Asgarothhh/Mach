import { apiRequest } from '../../../shared/api/http';
import { env } from '../../../shared/config/env';
import type { SendTextMessageInput, SendTextMessageResult } from './chat.service';

let cachedSessionId: string | null = null;

function websocketOrigin(): string {
  const apiOrigin = env.apiBaseUrl.replace(/\/api\/v1\/?$/, '');
  return apiOrigin.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:');
}

function decodeTextChunk(base64: string): string {
  const binary = window.atob(base64);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

async function getSessionId(preferredSessionId?: string): Promise<string> {
  if (preferredSessionId) return preferredSessionId;
  if (cachedSessionId) return cachedSessionId;
  const created = await apiRequest<{ session_id: string }>('/sessions', {
    method: 'POST',
    body: { tenant_id: env.backendTestTenantId, channel: 'mock', language: 'ru' },
  });
  if (!created.session_id) throw new Error('Backend не вернул session_id.');
  cachedSessionId = created.session_id;
  return created.session_id;
}

/** Local integration bridge: ships finalized text as ASREvent. It does not stream microphone audio. */
export async function sendBackendTextTest(input: SendTextMessageInput): Promise<SendTextMessageResult> {
  const sessionId = await getSessionId(input.sessionId || undefined);
  const ws = new WebSocket(`${websocketOrigin()}/api/v1/ws/sessions/${encodeURIComponent(sessionId)}`);

  return new Promise<SendTextMessageResult>((resolve, reject) => {
    let answer = '';
    let settled = false;
    const timeoutId = window.setTimeout(() => finishError(new Error('Backend WebSocket timeout. Проверьте логи FastAPI.')), 20_000);
    const finish = (result: SendTextMessageResult) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeoutId);
      ws.close();
      resolve(result);
    };
    const finishError = (error: Error) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeoutId);
      ws.close();
      reject(error);
    };

    ws.addEventListener('open', () => {
      ws.send(JSON.stringify({
        type: 'ASREvent',
        payload: {
          session_id: sessionId,
          turn_id: crypto.randomUUID(),
          timestamp_ms: Date.now(),
          revision: 1,
          text: input.text,
          is_final: true,
          language: 'ru',
          confidence: 1,
        },
      }));
    }, { once: true });

    ws.addEventListener('message', (event) => {
      try {
        const envelope = JSON.parse(String(event.data)) as {
          type?: string;
          payload?: { audio_base64?: string; is_last_chunk?: boolean; code?: string };
        };
        if (envelope.type === 'ErrorEvent') {
          finishError(new Error(`Backend event error: ${envelope.payload?.code ?? 'unknown'}`));
          return;
        }
        if (envelope.type !== 'TTSChunkEvent' || !envelope.payload) return;
        if (envelope.payload.audio_base64) answer += decodeTextChunk(envelope.payload.audio_base64);
        if (envelope.payload.is_last_chunk) {
          finish({
            answer_text: answer.trim() || 'Backend завершил ход без текстового ответа.',
            citation_ids: [],
            citations: [],
            answer_status: 'no_evidence',
          });
        }
      } catch {
        finishError(new Error('Backend вернул сообщение в неподдерживаемом формате.'));
      }
    });

    ws.addEventListener('error', () => finishError(new Error('Не удалось подключиться к backend WebSocket.')));
    ws.addEventListener('close', () => {
      if (!settled) finishError(new Error('Backend закрыл WebSocket до завершения ответа.'));
    });
  });
}
