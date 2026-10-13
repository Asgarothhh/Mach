import { useEffect, useRef } from 'react';
import { ArrowLeft, CheckCircle2, LoaderCircle, MessageSquare, X } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { Waveform } from '../../../shared/components/Waveform';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { env } from '../../../shared/config/env';
import { useVoiceExperience } from '../model/VoiceExperienceContext';

export function ConnectingPage() {
  const navigate = useNavigate();
  const { voice, conversation } = useVoiceExperience();
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void voice.start();
  }, [voice.start]);

  useEffect(() => {
    if (voice.state !== 'listening') return;
    if (env.demoMode) conversation.seedDemoConversation();
    const timer = window.setTimeout(() => navigate('/voice/live', { replace: true }), 500);
    return () => window.clearTimeout(timer);
  }, [voice.state, conversation.seedDemoConversation, navigate]);

  const failed = voice.state === 'degraded';
  return (
    <section className="flow-page">
      <div className="flow-topline"><Link to="/voice/permission" className="text-link"><ArrowLeft size={15} /> Настройка микрофона</Link><StatusBadge tone={failed ? 'danger' : 'success'} dot>{failed ? 'Не удалось подключиться' : 'Доступ к микрофону разрешён'}</StatusBadge></div>
      <div className="connecting-panel">
        <span className="connecting-kicker">{env.demoMode ? 'Демонстрационный сценарий' : 'Подключение ещё не установлено'}</span>
        <h1>{failed ? 'Не удалось подключить голосовой канал' : 'Подключаю голосовой канал'}</h1>
        <Waveform variant="stage" animated={!failed} />
        <p className="connecting-copy">{failed ? (voice.notice ?? 'Проверьте настройки соединения и попробуйте снова или продолжите текстом.') : env.demoMode ? 'Показываем демонстрационный переход. Реальная голосовая сессия будет доступна после подключения backend и LiveKit.' : 'Готовим соединение. Можно немного подождать или продолжить текстом.'}</p>
        <div className="connection-checklist">
          <div><CheckCircle2 size={20} className="check-icon" /><span>Микрофон доступен</span><StatusBadge tone="success">Готово</StatusBadge></div>
          <div>{failed ? <X size={20} className="error-icon" /> : <LoaderCircle size={20} className="loader-icon spin" />}<span>Устанавливаем защищённое соединение</span><StatusBadge tone={failed ? 'danger' : 'neutral'}>{failed ? 'Ошибка' : 'Ожидание'}</StatusBadge></div>
          <small>{failed ? 'Сессия не началась. Старые задачи не будут запущены.' : 'Обычно это занимает несколько секунд.'}</small>
        </div>
        {failed && <div className="inline-alert inline-alert--warning" role="alert">{voice.notice}</div>}
        <div className="connecting-actions">
          {failed && <button className="button button--primary" onClick={() => { started.current = false; void voice.start(); }}>Повторить подключение</button>}
          <Link to="/text" className="button button--secondary"><MessageSquare size={17} /> Написать вопрос</Link>
          <button className="button button--quiet" onClick={() => { void voice.stop(); navigate('/'); }}>Отменить</button>
        </div>
      </div>
    </section>
  );
}
