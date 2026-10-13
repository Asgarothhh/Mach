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
  { to: '/admin/scenarios', label: 'Сценарии и routing', icon: GitBranch },
  { to: '/admin/rag', label: 'RAG-инспектор', icon: FileSearch },
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
        <div className="admin-sidebar__product"><span>Inbound control plane</span><strong>МТС · Voice Agent</strong></div>
        <div className="track-admin-tenant-chip"><span className="track-tenant-avatar">{tenantName.slice(0, 1).toUpperCase()}</span><span><strong>{tenantName}</strong><small>{tenantId}</small></span></div>
        <nav className="admin-nav" aria-label="Разделы административной панели">
          {links.map(({ to, label, icon: Icon, end }) => {
            const href = to === '/admin/sessions' && !env.backendAdminSessions ? '/admin/calls' : to;
            const linkLabel = to === '/admin/sessions' && !env.backendAdminSessions ? 'История звонков' : label;
            return <NavLink key={href} to={href} end={end} className={({ isActive }) => `admin-nav__link ${isActive ? 'is-active' : ''}`}><Icon size={17} /><span>{linkLabel}</span></NavLink>;
          })}
        </nav>
        <div className="admin-sidebar__bottom"><div className="admin-health-dot" /><div><strong>{env.backendAdminSessions ? 'Backend API · sessions' : env.demoMode ? 'Демо-стенд' : 'Backend API'}</strong><span>{env.backendAdminSessions && env.demoMode ? 'Сессии live · прочие разделы demo' : env.demoMode ? 'Синтетические данные' : 'Статус по API'}</span></div></div>
        <a className="admin-doc-link" href="https://www.mts.by/company/comp/doc/" target="_blank" rel="noopener noreferrer"><LockKeyhole size={14} /> Политика обработки данных</a>
      </aside>
      <div className="admin-main-column">
        <header className="admin-topbar"><div><span className="admin-topbar__breadcrumb">Tenant control plane</span><span className="admin-topbar__slash">/</span><strong>Inbound Voice Agent</strong></div><div className="admin-topbar__actions"><TenantSwitcher />{env.backendAdminSessions && <BackendHealthIndicator />}<span className="admin-period"><Clock3 size={13} /> Europe/Minsk</span><span className="role-chip">роль задаёт backend</span><span className="admin-user-avatar">VA</span></div></header>
        {(!env.demoMode || env.backendAdminSessions) && <div className="track-admin-security-note"><ShieldCheck size={14} /> {env.backendAdminSessions && env.demoMode ? 'Список и детали сессий работают через API; остальные разделы остаются демонстрационными. Права, tenant isolation и аудит должны проверяться backend.' : 'Все права, tenant isolation и аудит проверяются на backend. Скрытие UI не является авторизацией.'}</div>}
        <main className="admin-content"><Outlet /></main>
        <footer className="admin-footer"><span><Activity size={13} /> Панель управления входящими звонками</span><span>{env.backendAdminSessions && env.demoMode ? 'HYBRID · sessions API + demo fixtures' : env.demoMode ? 'DEMO · все записи синтетические' : 'Tenant-scoped API data'}</span></footer>
      </div>
    </div>
  );
}
