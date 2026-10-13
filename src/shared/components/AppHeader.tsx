import { ExternalLink, PhoneCall, Settings2 } from 'lucide-react';
import { Link, NavLink } from 'react-router-dom';
import { env } from '../config/env';
import { useLocale } from '../i18n/LocaleContext';
import { Brand } from './Brand';
import { TenantSwitcher } from './TenantSwitcher';

const navItems = [
  { to: '/', label: 'Обзор', end: true },
  { to: '/onboarding', label: 'Подключение' },
  { to: '/calls', label: 'Звонки' },
  { to: '/scenarios', label: 'Сценарии' },
];

export function AppHeader() {
  const { locale, setLocale } = useLocale();
  return (
    <header className="public-header public-header--track1">
      <div className="public-header__inner">
        <Link to="/" className="track-header-brand" aria-label="MTS Inbound Voice Agent — обзор"><Brand /></Link>
        <nav className="track-main-nav" aria-label="Основная навигация">
          {navItems.map((item) => <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => `track-main-nav__link ${isActive ? 'is-active' : ''}`}>{item.label}</NavLink>)}
        </nav>
        <nav className="public-header__actions" aria-label="Настройки интерфейса">
          <TenantSwitcher />
          {env.demoMode && <span className="demo-badge">Демо</span>}
          <div className="locale-switch" role="group" aria-label="Язык интерфейса"><button type="button" className={locale === 'ru' ? 'is-active' : ''} onClick={() => setLocale('ru')} aria-pressed={locale === 'ru'}>РУ</button><button type="button" className={locale === 'be' ? 'is-active' : ''} onClick={() => setLocale('be')} aria-pressed={locale === 'be'}>БЕ</button></div>
          <Link className="track-header-admin" to="/admin"><Settings2 size={15} /><span>Админка</span></Link>
          <a className="support-link" href="https://help.mts.by/" target="_blank" rel="noopener noreferrer">Поддержка <ExternalLink size={14} /></a>
          <Link className="track-header-test" to="/voice/permission" title="Browser mic test mode"><PhoneCall size={15} /><span>Тест голоса</span></Link>
        </nav>
      </div>
      {env.demoMode && <div className="demo-topline" aria-label="Включён демонстрационный режим" />}
    </header>
  );
}
