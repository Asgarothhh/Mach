import { useState } from 'react';
import { ArrowLeft, Info, Mic } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { env } from '../../../shared/config/env';

export function PermissionPage() {
  const navigate = useNavigate();
  const [requesting, setRequesting] = useState(false);
  const [granted, setGranted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function requestMicrophone() {
    setError(null);
    setRequesting(true);
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Браузер не поддерживает доступ к микрофону или страница открыта не в безопасном контексте. Используйте HTTPS или localhost.');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
      setGranted(true);
      window.setTimeout(() => navigate('/voice/connecting'), 350);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось получить доступ к микрофону. Проверьте разрешения браузера.');
    } finally { setRequesting(false); }
  }

  return (
    <section className="flow-page">
      <div className="flow-topline"><Link to="/" className="text-link"><ArrowLeft size={15} /> Назад к темам</Link><span className="neutral-pill">Настройка голоса</span></div>
      <div className="permission-panel">
        <div className="permission-icon"><Mic size={42} strokeWidth={1.7} /></div>
        <h1>Разрешите доступ к микрофону</h1>
        <p className="permission-description">Он нужен, чтобы услышать ваш вопрос и поддержать голосовой разговор. Доступ можно отключить в настройках браузера.</p>
        {granted && <StatusBadge tone="success" dot>Доступ к микрофону разрешён</StatusBadge>}
        <div className="permission-instructions">
          <strong>Как включить голос</strong>
          <p>1. Нажмите «Разрешить и продолжить». 2. В запросе вашего браузера выберите «Разрешить». 3. Дождитесь подключения и задайте вопрос.</p>
          <small>Запрос доступа появится в браузере. Это не окно приложения.</small>
        </div>
        {error && <div className="inline-alert inline-alert--warning" role="alert"><Info size={18} /><div><strong>Не удалось получить доступ</strong><p>{error}</p></div></div>}
        <div className="permission-actions">
          <button className="button button--primary button--large" onClick={() => void requestMicrophone()} disabled={requesting}><Mic size={18} />{requesting ? 'Запрашиваем доступ…' : 'Разрешить и продолжить'}</button>
          <Link className="button button--secondary button--large" to="/text">Продолжить текстом</Link>
          {env.demoMode && <button className="button button--text" onClick={() => navigate('/voice/connecting')}>Посмотреть демо без микрофона</button>}
        </div>
        <div className="permission-help"><Info size={18} /><div><strong>Если доступ запрещён</strong><p>Откройте настройки сайта рядом с адресной строкой и разрешите микрофон. Можно не менять разрешения и сразу написать вопрос.</p></div></div>
      </div>
    </section>
  );
}
