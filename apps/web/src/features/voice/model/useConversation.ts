import { useCallback, useState } from 'react';
import type { SourceCitation } from '../../../shared/types/api';
import type { ConversationMessage, MessageOrigin, MessageRole, TranscriptEvent } from '../../../shared/types/voice';

function createId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function newMessage(role: MessageRole, text: string, origin: MessageOrigin, options?: { citations?: SourceCitation[]; final?: boolean; turnId?: string }): ConversationMessage {
  return {
    id: createId(), role, text, createdAt: new Date().toISOString(),
    final: options?.final ?? true, origin, citations: options?.citations, turnId: options?.turnId,
  };
}

export function useConversation() {
  const [messages, setMessages] = useState<ConversationMessage[]>([]);

  const addMessage = useCallback((role: MessageRole, text: string, origin: MessageOrigin, options?: { citations?: SourceCitation[]; final?: boolean; turnId?: string }) => {
    setMessages((current) => [...current, newMessage(role, text, origin, options)]);
  }, []);

  const upsertTranscript = useCallback((event: TranscriptEvent) => {
    setMessages((current) => {
      const messageId = `transcript:${event.id}`;
      const index = current.findIndex((message) => message.id === messageId);
      const existing = index >= 0 ? current[index] : undefined;
      // Final revisions cannot be overwritten by a late partial event.
      if (existing?.final && !event.final) return current;
      const next: ConversationMessage = {
        id: messageId, turnId: event.turnId, role: event.role, text: event.text,
        createdAt: existing?.createdAt ?? new Date().toISOString(), final: event.final,
        origin: 'live',
      };
      if (index < 0) return [...current, next];
      return current.map((message, messageIndex) => messageIndex === index ? next : message);
    });
  }, []);

  const seedDemoConversation = useCallback(() => {
    setMessages((current) => {
      if (current.length) return current;
      const now = Date.now();
      const sample: ConversationMessage[] = [
        { id: 'demo-user-1', role: 'user', text: 'Помогите подготовиться к поездке.', createdAt: new Date(now - 60_000).toISOString(), final: true, origin: 'demo' },
        { id: 'demo-assistant-1', role: 'assistant', text: 'Конечно. Что вы хотите узнать о связи за границей?', createdAt: new Date(now - 50_000).toISOString(), final: true, origin: 'demo' },
      ];
      return sample;
    });
  }, []);

  const clearConversation = useCallback(() => setMessages([]), []);
  return { messages, addMessage, upsertTranscript, clearConversation, seedDemoConversation };
}
