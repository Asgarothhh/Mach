import { ExternalLink, PhoneCall, Settings2 } from 'lucide-react';
import { Link, NavLink } from 'react-router-dom';
import { env } from '../config/env';
import { useTenant } from '../../features/tenant/model/TenantContext';
import { Brand } from './Brand';
import { TenantSwitcher } from './TenantSwitcher';

const navItems = [
  { to: '/', label: 'Обзор', end: true },
  { to: '/onboarding', label: 'Подключение' },
  { to: '/calls', label: 'Звонки' },
  { to: '/scenarios', label: 'Сценарии' },
];

export function AppHeader() {
  const { supportUrl } = useTenant();
  return (
    <header className="public-header public-header--track1">
      <div className="public-header__inner">
        <div className="track-header-brand"><Brand /></div>
        <nav className="track-main-nav" aria-label="Основная навигация">
          {navItems.map((item) => <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => `track-main-nav__link ${isActive ? 'is-active' : ''}`}>{item.label}</NavLink>)}
        </nav>
        <nav className="public-header__actions" aria-label="Настройки интерфейса">
          <TenantSwitcher />
          {env.demoMode && <span className="demo-badge">Демо</span>}
          <Link className="track-header-admin" to="/admin"><Settings2 size={15} /><span>Админка</span></Link>
          {supportUrl ? <a className="support-link" href={supportUrl} target="_blank" rel="noopener noreferrer">Поддержка <ExternalLink size={14} /></a> : null}
          <Link className="track-header-test" to="/voice/permission" title="Голосовой помощник"><PhoneCall size={15} /><span>Голосовой помощник</span></Link>
        </nav>
      </div>
      {env.demoMode && <div className="demo-topline" aria-label="Включён демонстрационный режим" />}
    </header>
  );
}
