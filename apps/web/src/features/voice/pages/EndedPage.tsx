import { CheckCircle2, MessageSquare, RotateCcw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { MessageBubble } from '../../../shared/components/MessageBubble';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { env } from '../../../shared/config/env';
import { pluralRu } from '../../../shared/lib/pluralRu';
import { useVoiceExperience } from '../model/VoiceExperienceContext';

export function EndedPage() {
  const { conversation, voice } = useVoiceExperience();
  const navigate = useNavigate();

  function newConversation() {
    conversation.clearConversation();
    voice.reset();
    navigate('/');
  }

  const count = conversation.messages.length;
  const countLabel = `${count} ${pluralRu(count, 'сообщение', 'сообщения', 'сообщений')}`;

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
            <div><h2>История текущей сессии</h2><p className="muted-copy">{countLabel} · {env.demoMode ? 'синтетический пример' : 'текущая сессия'}</p></div>
          </div>
          <div className="dialog-panel__messages">
            {conversation.messages.map((message) => <MessageBubble key={message.id} message={message} />)}
          </div>
        </section>

        <aside className="side-info-card">
          <h2>Сессия завершена</h2>
          <p className="muted-copy">Оценка этого разговора на стенде не собирается.</p>
          <div className="scope-note"><MessageSquare size={16} /><span>Это был разговор в браузере. Реальные действия с данными клиентов не выполнялись.</span></div>
        </aside>
      </div>
    </section>
  );
}
