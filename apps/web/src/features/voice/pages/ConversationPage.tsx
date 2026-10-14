import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, Mic, MessageSquare, Pause, ShieldCheck, Square, Volume2 } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { env } from '../../../shared/config/env';
import { demoAnswer, demoSources } from '../../knowledge/data/demoSources';
import { MessageBubble } from '../../../shared/components/MessageBubble';
import { SourceCard } from '../../../shared/components/SourceCard';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { Waveform } from '../../../shared/components/Waveform';
import { useVoiceExperience } from '../model/VoiceExperienceContext';
import type { VoiceState } from '../../../shared/types/voice';

const stateCopy: Record<VoiceState, { title: string; caption: string; pill: string }> = {
  idle: { title: 'Начните разговор', caption: 'Нажмите кнопку, чтобы подключиться.', pill: 'Ожидание' },
  requesting_microphone: { title: 'Разрешите микрофон', caption: 'Браузер запросит доступ к микрофону.', pill: 'Микрофон' },
  connecting: { title: 'Подключаю голосовой канал', caption: 'Готовим защищённое соединение.', pill: 'Подключение' },
  listening: { title: 'Слушаю вас', caption: 'Говорите в обычном темпе. Можно перебить помощника в любой момент.', pill: 'Слушаю' },
  processing: { title: 'Проверяю официальные источники', caption: 'Ищу материалы по вашему вопросу. Ответ появится после проверки.', pill: 'Поиск информации' },
  speaking: { title: 'Готовимся к поездке', caption: 'Можно перебить — просто начните говорить.', pill: 'Ответ озвучивается' },
  degraded: { title: 'Голос временно недоступен', caption: 'Продолжите диалог текстом.', pill: 'Текстовый режим' },
  ended: { title: 'Разговор завершён', caption: 'История диалога доступна до закрытия или очистки страницы.', pill: 'Завершено' },
};

export function ConversationPage() {
  const navigate = useNavigate();
  const { conversation, voice } = useVoiceExperience();
  const [demoStage, setDemoStage] = useState<'listening' | 'processing' | 'speaking'>('listening');
  const [demoBusy, setDemoBusy] = useState(false);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    if (env.demoMode) conversation.seedDemoConversation();
    return () => timers.current.forEach(window.clearTimeout);
  }, [conversation.seedDemoConversation]);

  const lastAssistant = useMemo(() => [...conversation.messages].reverse().find((message) => message.role === 'assistant'), [conversation.messages]);
  const state = env.demoMode ? (demoStage === 'processing' ? 'processing' : demoStage === 'speaking' ? 'speaking' : 'listening') : voice.state;
  const copy = stateCopy[state];
  const sampleQuestion = 'Что нужно проверить перед поездкой за границу?';
  const shownAnswer = env.demoMode && demoStage === 'speaking' ? demoAnswer : lastAssistant?.text;
  const shownSources = env.demoMode && demoStage === 'speaking' ? demoSources : lastAssistant?.citations ?? [];

  function runDemoTurn() {
    if (demoBusy) return;
    setDemoBusy(true);
    setDemoStage('processing');
    const processingTimer = window.setTimeout(() => {
      conversation.addMessage('user', sampleQuestion, 'demo');
      setDemoStage('speaking');
      conversation.addMessage('assistant', demoAnswer, 'demo', { citations: demoSources });
      setDemoBusy(false);
    }, 1500);
    timers.current.push(processingTimer);
  }

  async function finish() {
    await voice.stop();
    navigate('/ended');
  }

  return (
    <section className="conversation-page">
      <div className="conversation-page__topline">
        <Link to="/" className="text-link"><ArrowLeft size={15} /> Назад к темам</Link>
        <div className="conversation-page__meta"><span>{voice.channelLabel}</span><StatusBadge tone={env.demoMode ? 'demo' : voice.isConnected ? 'success' : 'neutral'} dot>{env.demoMode ? 'Демо · синтетическая сессия' : voice.isConnected ? `Соединение активно · ${formatElapsed(voice.elapsedSeconds)}` : copy.pill}</StatusBadge></div>
      </div>
      {voice.notice && !env.demoMode && <div className="inline-alert inline-alert--warning" role="status">{voice.notice}</div>}
      <div className="conversation-layout">
        <div className="conversation-main-column">
          <section className={`voice-stage voice-stage--${state}`}>
            <StatusBadge tone={state === 'speaking' ? 'danger' : env.demoMode ? 'demo' : 'success'}>{env.demoMode ? 'Демо-сценарий' : copy.pill}</StatusBadge>
            <h1>{copy.title}</h1>
            <Waveform variant="stage" animated={state === 'listening' || state === 'speaking'} />
            <p>{env.demoMode ? (state === 'listening' ? 'Демо не отправляет ваш голос на сервер. Нажмите кнопку ниже, чтобы увидеть обработку запроса.' : state === 'processing' ? 'Ищем демонстрационные фрагменты источников и проверяем ответ.' : 'Это пример ответа. В демо аудио не генерируется.') : copy.caption}</p>
            {env.demoMode && state === 'listening' && <button className="button button--primary" onClick={runDemoTurn} disabled={demoBusy}><MessageSquare size={17} /> Показать пример обработки</button>}
            {state === 'speaking' && <div className="stage-subtle"><Volume2 size={15} /> Можно перебить — просто начните говорить</div>}
          </section>

          {env.demoMode && state === 'listening' && (
            <section className="partial-transcript-card">
              <StatusBadge tone="danger">Распознаётся · пример текста</StatusBadge>
              <p>{sampleQuestion.slice(0, 45)}…</p>
              <small>В рабочем режиме это место обновляется событиями streaming ASR.</small>
            </section>
          )}
          {state === 'processing' && <section className="evidence-panel"><div className="panel-heading"><div><span className="section-eyebrow">Поиск</span><h2>Ищем ответ в базе знаний</h2></div><StatusBadge tone="warning">Проверка</StatusBadge></div><p className="muted-copy">Сверяем вопрос с материалами компании. Ответ появится после проверки.</p><div className="source-stack">{demoSources.map((source) => <SourceCard key={source.id} source={source} />)}</div></section>}
          {state === 'speaking' && shownAnswer && <article className="answer-card"><div className="answer-card__label"><span>ИИ-помощник</span><span>Демо-текст</span></div><p>{shownAnswer}</p><div className="answer-card__foot"><ShieldCheck size={15} /> Пример ответа. Фактические утверждения рабочей версии проверяются по актуальным источникам.</div></article>}

          <div className="voice-actionbar">
            {env.demoMode && state === 'speaking' && <button className="button button--secondary" onClick={() => { setDemoStage('listening'); }}><Pause size={16} /> Прервать ответ</button>}
            {env.demoMode ? <button className="button button--secondary" onClick={() => navigate('/text')}><MessageSquare size={17} /> Текст</button> : <button className="button button--secondary" onClick={() => { void voice.switchToText().then(() => navigate('/text')); }}><MessageSquare size={17} /> Текст</button>}
            {!env.demoMode && <button className="button button--secondary" onClick={() => void voice.start()} disabled={voice.isConnected}><Mic size={17} /> Включить микрофон</button>}
            <button className="button button--quiet" onClick={() => void finish()}><Square size={15} /> Завершить</button>
            {env.demoMode && state === 'speaking' && <button className="button button--text" onClick={() => { setDemoStage('listening'); }}>Сбросить пример</button>}
          </div>
          <p className="privacy-caption"><ShieldCheck size={14} /> Аудио не сохраняется по умолчанию. Не сообщайте личные данные.</p>
        </div>

        <aside className="conversation-aside">
          <section className="dialog-panel">
            <h2>Ваш диалог</h2><p className="muted-copy">Только завершённые сообщения</p>
            <div className="dialog-panel__messages">
              {conversation.messages.filter((message) => message.final).map((message) => <MessageBubble key={message.id} message={message} compact />)}
              {env.demoMode && state === 'processing' && <div className="pending-message">Ответ ещё не готов. Проверяю информацию…</div>}
            </div>
            <small>Новая реплика появится здесь после завершения распознавания.</small>
          </section>
          {(state === 'speaking' || shownSources.length > 0) && <section className="sources-panel"><h2>Проверить самостоятельно</h2><p className="muted-copy">Материалы, на которые опирается ответ</p><strong className="source-count">Источники · {shownSources.length}</strong><div className="source-stack">{shownSources.map((source) => <SourceCard key={source.id} source={source} compact />)}</div><small>Сверяйте факты с указанными страницами компании.</small></section>}
          <section className="scope-note"><strong>Голосовой помощник в браузере</strong><p>Разговор идёт через браузер. Это не телефонный звонок.</p></section>
        </aside>
      </div>
    </section>
  );
}

function formatElapsed(seconds: number) { return `00:${seconds.toString().padStart(2, '0')}`; }
