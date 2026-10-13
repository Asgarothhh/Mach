import { useState } from 'react';
import { CheckCircle2, MessageSquare, RotateCcw, ThumbsDown, ThumbsUp } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { MessageBubble } from '../../../shared/components/MessageBubble';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { env } from '../../../shared/config/env';
import { useVoiceExperience } from '../model/VoiceExperienceContext';

type Rating = 'yes' | 'no' | null;

export function EndedPage() {
  const { conversation, voice } = useVoiceExperience();
  const navigate = useNavigate();
  const [rating, setRating] = useState<Rating>(null);

  function newConversation() {
    conversation.clearConversation();
    voice.reset();
    setRating(null);
    navigate('/');
  }

  return (
    <section className="ended-page">
      <div className="ended-hero">
        <div className="ended-check"><CheckCircle2 size={38} /></div>
        <StatusBadge tone={env.demoMode ? 'demo' : 'success'}>{env.demoMode ? 'Демонстрационный сеанс' : 'Сессия завершена'}</StatusBadge>
        <h1>Спасибо за разговор</h1>
        <p>Диалог доступен на этой странице до её закрытия или очистки. Начало нового разговора создаст новую сессию.</p>
        <button className="button button--primary button--large" type="button" onClick={newConversation}>
          <RotateCcw size={18} /> Новый разговор
        </button>
      </div>

      <div className="ended-layout">
        <section className="dialog-panel">
          <div className="panel-heading">
            <div><h2>История текущей сессии</h2><p className="muted-copy">{conversation.messages.length} сообщений · {env.demoMode ? 'синтетический пример' : 'текущая сессия'}</p></div>
          </div>
          <div className="dialog-panel__messages">
            {conversation.messages.map((message) => <MessageBubble key={message.id} message={message} />)}
          </div>
        </section>

        <aside className="side-info-card">
          <h2>Помощник был полезен?</h2>
          <p className="muted-copy">Оцените именно этот разговор.</p>
          <div className="rating-actions">
            <button type="button" className={`rating-button ${rating === 'yes' ? 'is-selected' : ''}`} onClick={() => setRating('yes')} aria-pressed={rating === 'yes'}><ThumbsUp size={20} /> Да</button>
            <button type="button" className={`rating-button ${rating === 'no' ? 'is-selected' : ''}`} onClick={() => setRating('no')} aria-pressed={rating === 'no'}><ThumbsDown size={20} /> Нет</button>
          </div>
          {rating && <p className="inline-success">Спасибо за отзыв. В этом макете оценка не отправляется на сервер.</p>}
          <div className="scope-note"><MessageSquare size={16} /><span>Это был browser test call. В тесте не выполнялись реальные действия и не использовались данные клиентов.</span></div>
        </aside>
      </div>
    </section>
  );
}
