import { Activity, BookOpen, CheckCircle2, CircleGauge, Database, FileSearch, Gauge, LockKeyhole, Settings2, ShieldCheck, PhoneCall, GitBranch, Clock3 } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';
import { Brand } from '../../../shared/components/Brand';
import { TenantSwitcher } from '../../../shared/components/TenantSwitcher';
import { env } from '../../../shared/config/env';
import { useTenant } from '../../tenant/model/TenantContext';
import { BackendHealthIndicator } from './BackendHealthIndicator';

const links = [
  { to: '/admin', label: 'Обзор звонков', icon: CircleGauge, end: true },
  { to: '/admin/sessions', label: 'Сессии и транскрипты', icon: PhoneCall },
  { to: '/admin/scenarios', label: 'Сценарии и маршруты', icon: GitBranch },
  { to: '/admin/rag', label: 'Проверка источников', icon: FileSearch },
  { to: '/admin/knowledge', label: 'Источники знаний', icon: BookOpen },
  { to: '/admin/sync', label: 'Синхронизация', icon: Database },
  { to: '/admin/quality', label: 'Проверка качества', icon: CheckCircle2 },
  { to: '/admin/configuration', label: 'Конфигурация', icon: Settings2 },
  { to: '/admin/audit', label: 'Аудит и безопасность', icon: ShieldCheck },
  { to: '/admin/evaluations', label: 'Оценка моделей', icon: Gauge },
];

export function AdminLayout() {
  const { tenantName, tenantId } = useTenant();
  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <Brand compact admin />
        <div className="admin-sidebar__product"><span>Кабинет компании</span><strong>МТС · Голосовой помощник</strong></div>
        <div className="track-admin-tenant-chip"><span className="track-tenant-avatar">{tenantName.slice(0, 1).toUpperCase()}</span><span><strong>{tenantName}</strong><small>{tenantId}</small></span></div>
        <nav className="admin-nav" aria-label="Разделы административной панели">
          {links.map(({ to, label, icon: Icon, end }) => {
            const href = to === '/admin/sessions' && !env.backendAdminSessions ? '/admin/calls' : to;
            const linkLabel = to === '/admin/sessions' && !env.backendAdminSessions ? 'История звонков' : label;
            return <NavLink key={href} to={href} end={end} className={({ isActive }) => `admin-nav__link ${isActive ? 'is-active' : ''}`}><Icon size={17} /><span>{linkLabel}</span></NavLink>;
          })}
        </nav>
        <div className="admin-sidebar__bottom"><div className="admin-health-dot" /><div><strong>{env.backendAdminSessions ? 'Сервис подключён' : env.demoMode ? 'Демо-стенд' : 'Сервис'}</strong><span>{env.backendAdminSessions && env.demoMode ? 'Сессии с сервера · прочие разделы демо' : env.demoMode ? 'Синтетические данные' : 'Статус сервиса'}</span></div></div>
        <a className="admin-doc-link" href="https://www.mts.by/company/comp/doc/" target="_blank" rel="noopener noreferrer"><LockKeyhole size={14} /> Политика обработки данных</a>
      </aside>
      <div className="admin-main-column">
        <header className="admin-topbar"><div><span className="admin-topbar__breadcrumb">Админка</span><span className="admin-topbar__slash">/</span><strong>Голосовой помощник</strong></div><div className="admin-topbar__actions"><TenantSwitcher />{env.backendAdminSessions && <BackendHealthIndicator />}<span className="admin-period"><Clock3 size={13} /> Europe/Minsk</span><span className="role-chip">права задаёт сервис</span><span className="admin-user-avatar">VA</span></div></header>
        {(!env.demoMode || env.backendAdminSessions) && <div className="track-admin-security-note"><ShieldCheck size={14} /> {env.backendAdminSessions && env.demoMode ? 'Список сессий приходит с сервера; остальные разделы пока демонстрационные. Права доступа проверяет сервис.' : 'Права доступа и изоляция компаний проверяются сервисом. Скрытие пункта меню само по себе доступ не даёт.'}</div>}
        <main className="admin-content"><Outlet /></main>
        <footer className="admin-footer"><span><Activity size={13} /> Панель управления входящими звонками</span><span>{env.backendAdminSessions && env.demoMode ? 'Сессии с сервера · остальные разделы демо' : env.demoMode ? 'Демо · все записи синтетические' : 'Данные вашей компании'}</span></footer>
      </div>
    </div>
  );
}
