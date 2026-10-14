import { ExternalLink, Info, ShieldCheck } from 'lucide-react';
import { useTenant } from '../../features/tenant/model/TenantContext';
import { env } from '../config/env';

export function AppFooter() {
  const { supportUrl } = useTenant();
  return (
    <footer className="public-footer public-footer--track1">
      <div className="public-footer__notice"><Info size={18} aria-hidden="true" /><div><strong>Голосовой помощник МТС</strong><p>Сервис отвечает по базе знаний вашей компании. Не сообщайте паспортные данные и номера карт.</p></div></div>
      <div className="public-footer__bottom"><span><ShieldCheck size={14} /> {env.demoMode ? 'Используются синтетические звонки и данные. Сырой звук не сохраняется.' : 'Доступ к звонкам, транскриптам и настройкам контролирует сервис.'}</span><span className="public-footer__links"><a href="https://www.mts.by/company/comp/doc/" target="_blank" rel="noopener noreferrer">Документы <ExternalLink size={12} /></a>{supportUrl ? <a href={supportUrl} target="_blank" rel="noopener noreferrer">Поддержка <ExternalLink size={12} /></a> : null}</span></div>
      <p className="public-footer__safety">Не передавайте паспортные данные, номера карт и пароли в диалоге. Ответы помощника нужно сверять с официальными источниками компании.</p>
    </footer>
  );
}
