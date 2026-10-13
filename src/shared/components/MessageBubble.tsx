import { Clock3 } from 'lucide-react';
import type { ConversationMessage } from '../types/voice';

function timeLabel(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

export function MessageBubble({ message, compact = false }: { message: ConversationMessage; compact?: boolean }) {
  const roleLabel = message.role === 'user' ? 'Вы' : message.role === 'system' ? 'Система' : 'ИИ-помощник';
  return (
    <article className={`message-bubble message-bubble--${message.role} ${compact ? 'message-bubble--compact' : ''} ${!message.final ? 'message-bubble--partial' : ''}`}>
      <div className="message-bubble__meta"><strong>{roleLabel}{!message.final && ' · распознаётся'}</strong><span><Clock3 size={12} />{timeLabel(message.createdAt)}</span></div>
      <p>{message.text}</p>
      {!message.final && <small>Текст уточняется, пока вы говорите. Это ещё не завершённое сообщение.</small>}
    </article>
  );
}
