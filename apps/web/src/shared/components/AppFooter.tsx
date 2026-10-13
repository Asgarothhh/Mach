import { ExternalLink, Info, ShieldCheck } from 'lucide-react';
import { env } from '../config/env';

export function AppFooter() {
  return (
    <footer className="public-footer public-footer--track1">
      <div className="public-footer__notice"><Info size={18} aria-hidden="true" /><div><strong>Демонстрационный inbound voice agent</strong><p>Mock/test call не означает подключение к телефонной сети. Перед реальными звонками настройте уведомление и согласие, tenant-scoped доступы и approved источники, а external LLM оставьте выключенным до legal/security approval.</p></div></div>
      <div className="public-footer__bottom"><span><ShieldCheck size={14} /> {env.demoMode ? 'Используются синтетические звонки и данные. Сырой звук не сохраняется.' : 'Доступ к звонкам, транскриптам и настройкам контролирует backend.'}</span><span className="public-footer__links"><a href="https://www.mts.by/company/comp/doc/" target="_blank" rel="noopener noreferrer">Документы <ExternalLink size={12} /></a><a href="https://help.mts.by/" target="_blank" rel="noopener noreferrer">Поддержка <ExternalLink size={12} /></a></span></div>
      <p className="public-footer__safety">Никогда не помещайте API keys, SIP credentials или настоящие персональные данные в frontend bundle. Транскрипты и snippets отображаются как недоверенный текст.</p>
    </footer>
  );
}
