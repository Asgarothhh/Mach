import { env } from '../../../shared/config/env';
import { apiRequest } from '../../../shared/api/http';
import type { SourceCitation } from '../../../shared/types/api';
import { demoSources, demoAnswer } from '../../knowledge/data/demoSources';
import { sendBackendTextTest } from './backendTextTest.service';

export interface SendTextMessageInput {
  sessionId: string;
  text: string;
}

export interface SendTextMessageResult {
  answer_text: string;
  citation_ids?: string[];
  citations?: SourceCitation[];
  answer_status?: 'grounded' | 'needs_clarification' | 'no_evidence' | 'handoff';
}

/** Explicit canned response for UI work only. This is not an LLM call or MTS fact. */
export async function sendTextMessage(
  input: SendTextMessageInput,
): Promise<SendTextMessageResult> {
  if (env.backendTextTest) {
    return sendBackendTextTest(input);
  }

  if (env.demoMode) {
    await new Promise((resolve) => window.setTimeout(resolve, 450));
    await new Promise((resolve) => window.setTimeout(resolve, 650));
    const question = input.text.toLowerCase();
    if (/тариф|подключ|измен|баланс|сч[её]т|платеж/.test(question)) {
      return {
        answer_text: 'Я не могу менять тарифы, подключать услуги или проверять личный счёт. Для такой операции обратитесь в официальную поддержку МТС: https://help.mts.by/. Это демонстрационная подсказка, а не выполненная операция.',
        answer_status: 'handoff',
        citations: [],
      };
    }
    return {
      answer_text: demoAnswer,
      answer_status: 'grounded',
      citations: demoSources,
    };
  }

  // CONTRACT GAP: POST /sessions/{id}/messages is not specified in SPEC_MTS_VOICE_AGENT.md.
  // Agree on the request/response schema with backend before using text mode against a real API.
  if (!input.sessionId) {
    throw new Error('Текстовый endpoint ещё не согласован с backend для сессии без LiveKit.');
  }
  return apiRequest<SendTextMessageResult>(
    `/sessions/${encodeURIComponent(input.sessionId)}/messages`,
    { method: 'POST', body: { text: input.text } },
  );
}
