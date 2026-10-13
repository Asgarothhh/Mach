import { useState, type FormEvent } from 'react';
import { ArrowRight, Info, Mic, Send } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { MessageBubble } from '../../../shared/components/MessageBubble';
import { SourceCard } from '../../../shared/components/SourceCard';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { env } from '../../../shared/config/env';
import { demoSources } from '../../knowledge/data/demoSources';
import { sendTextMessage } from '../../chat/services/chat.service';
import { useVoiceExperience } from '../model/VoiceExperienceContext';

export function TextModePage() {
  const { conversation, voice } = useVoiceExperience();
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const navigate = useNavigate();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;

    setDraft('');
    setSending(true);
    conversation.addMessage('user', text, env.demoMode && !env.backendTextTest ? 'demo' : 'live');
    try {
      const result = await sendTextMessage({ sessionId: voice.sessionId ?? '', text });
      conversation.addMessage('assistant', result.answer_text, env.demoMode && !env.backendTextTest ? 'demo' : 'live', {
        citations: result.citations ?? [],
      });
    } catch (cause) {
      conversation.addMessage(
        'system',
        cause instanceof Error ? cause.message : 'Не удалось отправить вопрос.',
        'live',
      );
    } finally {
      setSending(false);
    }
  }

  const latestAnswer = [...conversation.messages].reverse().find((message) => message.role === 'assistant');
  const sources = latestAnswer?.citations ?? (env.demoMode && !env.backendTextTest && conversation.messages.length ? demoSources : []);

  return (
    <section className="text-page">
      <div className="text-page__title-row">
        <h1>Продолжим текстом</h1>
        <div><StatusBadge tone="danger">РУ · выбран</StatusBadge><StatusBadge>БЕ · текст поддерживается</StatusBadge></div>
      </div>
      <div className="inline-alert inline-alert--info">
        <Info size={19} />
        <div>
          <strong>Голос временно недоступен. Продолжим текстом</strong>
          <p>Ваш диалог сохранён. Ответы будут появляться здесь. Можно попробовать восстановить голос, не начиная разговор заново.</p>
        </div>
      </div>

      <div className="text-layout">
        <section className="dialog-panel text-dialog-panel">
          <h2>Ваш диалог</h2>
          <div className="dialog-panel__messages">
            {conversation.messages.map((message) => <MessageBubble key={message.id} message={message} />)}
          </div>
          <form className="text-composer" onSubmit={(event) => void submit(event)}>
            <label className="sr-only" htmlFor="text-message">Напишите вопрос без личных данных</label>
            <textarea
              id="text-message"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Напишите вопрос без личных данных…"
              maxLength={2000}
              rows={3}
            />
            <button type="submit" className="button button--primary" disabled={!draft.trim() || sending}>
              {sending ? 'Отправляем…' : 'Отправить'} <Send size={16} />
            </button>
          </form>
          <button className="button button--text clear-dialog" type="button" onClick={() => conversation.clearConversation()}>
            Очистить диалог
          </button>
        </section>

        <aside className="text-aside">
          <section className="side-info-card">
            <h2>Голосовой режим</h2>
            <p className="muted-copy">Микрофон не передаёт аудио. Текстовый диалог доступен.{env.backendTextTest ? ' Запрос отправляется в FastAPI как финальный ASR-текст; синтез аудио пока заглушка.' : ''}</p>
            <button
              className="button button--secondary"
              type="button"
              onClick={() => { void voice.resumeVoiceInput().then((resumed) => navigate(resumed ? '/voice/live' : '/voice/permission')); }}
            >
              <Mic size={17} /> Восстановить голос
            </button>
          </section>
          <section className="side-info-card">
            <h2>Из предыдущего ответа</h2>
            <p className="muted-copy">Источники отображаются рядом с ответом, когда их вернёт backend.</p>
            <div className="source-stack">{sources.map((source) => <SourceCard key={source.id} source={source} compact />)}</div>
          </section>
          <div className="scope-note">
            <strong>Не выполняю операции</strong>
            <p>Текстовый режим сохраняет тестовый диалог. Не обещайте действий без подтверждённого backend adapter.</p>
            <a href="https://help.mts.by/" target="_blank" rel="noopener noreferrer">Официальная поддержка <ArrowRight size={14} /></a>
          </div>
        </aside>
      </div>
    </section>
  );
}
