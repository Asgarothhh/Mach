import { useCallback, useEffect, useState } from 'react';
import { Activity, AlertTriangle, ArrowRight, ArrowUpRight, BarChart3, Clock3, GitBranch, Headphones, MessageSquare, PhoneCall, RefreshCw, ShieldCheck, UserRound } from 'lucide-react';
import { Link } from 'react-router-dom';
import { SectionHeading } from '../../../shared/components/SectionHeading';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { env } from '../../../shared/config/env';
import { useTenant } from '../../tenant/model/TenantContext';
import { getCallAnalytics, type CallAnalytics } from '../services/admin.service';
import { AdminPanel, MetricCard } from '../components/AdminPrimitives';
import { listBackendSessions, sessionStatusLabels, sessionStatusTone, type BackendSessionSummary } from '../services/adminSessions.service';

function percent(value: number | null) {
  return value == null ? '—' : `${(value * 100).toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%`;
}

export function AdminOverviewPage() {
  return env.backendAdminSessions ? <BackendSessionsOverview /> : <DemoAnalyticsOverview />;
}

function BackendSessionsOverview() {
  const { tenantId, tenantName } = useTenant();
  const [sessions, setSessions] = useState<BackendSessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSessions(await listBackendSessions({ tenantId: tenantId || env.backendTestTenantId, limit: 100, offset: 0 }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить сессии из backend.');
      setSessions([]);
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => { void load(); }, [load]);
  const terminalStatuses = new Set(['CLOSED', 'CHAT_HANDOFF', 'HUMAN_HANDOFF']);
  const activeCount = sessions.filter((session) => !terminalStatuses.has(session.status)).length;
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const todayCount = sessions.filter((session) => new Date(session.created_at).getTime() >= todayStart.getTime()).length;
  const humanCount = sessions.filter((session) => session.status === 'HUMAN_HANDOFF').length;
  const chatCount = sessions.filter((session) => session.status === 'CHAT_HANDOFF').length;
  const degradedCount = sessions.filter((session) => session.status === 'DEGRADED').length;

  return (
    <div className="admin-page-stack">
      <SectionHeading eyebrow="Админка" title="Обзор сессий" description={`Сессии компании ${tenantName}. Показаны до 100 последних записей.`} action={<div className="track-heading-actions"><StatusBadge tone="success" dot>Сервис подключён</StatusBadge><button type="button" className="button button--secondary button--small" onClick={() => void load()} disabled={loading}><RefreshCw size={14} /> Обновить</button></div>} />
      <div className="track-info-panel"><ShieldCheck size={17} /><div><strong>Это обзор по выборке</strong><p>Полная аналитика задержек пока недоступна. Числа ниже считаются по последним 100 сессиям.</p></div></div>
      {error && <div className="notice notice--warning" role="alert">{error}</div>}
      {loading && <div className="track-empty-state"><span className="loading-dot" />Загружаем реальные сессии…</div>}
      {!loading && !error && <>
        <div className="metric-grid metric-grid--four">
          <MetricCard label="Получено сессий" value={String(sessions.length)} detail="Не больше 100 по текущему контракту" icon={<PhoneCall size={17} />} />
          <MetricCard label="Не терминальные" value={String(activeCount)} detail="По текущему статусу сессии" icon={<Activity size={17} />} tone={activeCount ? 'green' : undefined} />
          <MetricCard label="Переданы оператору" value={String(humanCount)} detail="HUMAN_HANDOFF в выборке" icon={<UserRound size={17} />} tone="amber" />
          <MetricCard label="Переданы в чат" value={String(chatCount)} detail="CHAT_HANDOFF в выборке" icon={<MessageSquare size={17} />} />
        </div>
        <div className="metric-grid metric-grid--four">
          <MetricCard label="Созданы сегодня" value={String(todayCount)} detail="В пределах загруженной выборки" icon={<Clock3 size={17} />} />
          <MetricCard label="Деградация" value={String(degradedCount)} detail="DEGRADED в выборке" icon={<AlertTriangle size={17} />} tone={degradedCount ? 'amber' : undefined} />
        </div>
        <AdminPanel title="Последние сессии" eyebrow="Текущие данные" action={<Link className="button button--secondary button--small" to="/admin/sessions">Все сессии <ArrowUpRight size={14} /></Link>}>
          {sessions.length === 0 ? <div className="track-empty-state">Backend пока не вернул сессий для выбранного tenant.</div> : <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Session ID</th><th>Создана</th><th>Статус</th><th /></tr></thead><tbody>{sessions.slice(0, 8).map((session) => <tr key={session.session_id}><td><Link className="table-action-link" to={`/admin/sessions/${encodeURIComponent(session.session_id)}`}>{session.session_id}</Link></td><td>{new Date(session.created_at).toLocaleString('ru-RU')}</td><td><StatusBadge tone={sessionStatusTone(session.status)}>{sessionStatusLabels[session.status] ?? session.status}</StatusBadge></td><td><Link className="table-action-link" to={`/admin/sessions/${encodeURIComponent(session.session_id)}`}>Детали <ArrowUpRight size={13} /></Link></td></tr>)}</tbody></table></div>}
        </AdminPanel>
      </>}
      <div className="track-page-footnote"><Clock3 size={14} /> Полная статистика задержек и ошибок появится после отдельного отчёта.</div>
    </div>
  );
}

function DemoAnalyticsOverview() {
  const { tenantId, tenantName } = useTenant();
  const [data, setData] = useState<CallAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setData(await getCallAnalytics(tenantId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось загрузить аналитику звонков.'); }
    finally { setLoading(false); }
  }, [tenantId]);

  useEffect(() => { void load(); }, [load]);
  const d = data;

  return (
    <div className="admin-page-stack">
      <SectionHeading eyebrow="Админка" title="Обзор входящих звонков" description={`Маршруты, качество и доступность сервисов · ${tenantName}.`} action={<div className="track-heading-actions"><StatusBadge tone={env.demoMode ? 'demo' : 'neutral'} dot>{env.demoMode ? 'Синтетические данные' : 'Кабинет компании'}</StatusBadge><button type="button" className="button button--secondary button--small" onClick={() => void load()} disabled={loading}><RefreshCw size={14} /> Обновить</button></div>} />
      {env.demoMode && <div className="demo-data-callout"><ShieldCheck size={17} /><span><strong>Demo fixture.</strong> Данные считаются по синтетическим звонкам активного tenant. Здесь нет реальной телеком-статистики, настоящих транскриптов или Prometheus scrape.</span></div>}
      {error && <div className="notice notice--warning" role="alert">{error}</div>}
      {loading && <div className="track-empty-state"><span className="loading-dot" />Загружаем аналитику…</div>}
      {!loading && d && <>
        <div className="metric-grid metric-grid--four">
          <MetricCard label="Звонки за период" value={String(d.total_calls)} detail="Только текущий tenant" icon={<PhoneCall size={17} />} />
          <MetricCard label="Активные звонки" value={String(d.active_calls)} detail="Открытые call sessions" icon={<Activity size={17} />} tone={d.active_calls ? 'green' : undefined} />
          <MetricCard label="Chat handoff rate" value={percent(d.chat_handoff_rate)} detail={`${d.route_counts.chat_offer} предложений чата`} icon={<MessageSquare size={17} />} />
          <MetricCard label="Human handoff rate" value={percent(d.human_handoff_rate)} detail={`${d.route_counts.human_handoff} передач человеку`} icon={<UserRound size={17} />} tone="amber" />
        </div>
        <div className="metric-grid metric-grid--four">
          <MetricCard label="Error / degraded rate" value={percent(d.error_rate)} detail="Отмеченные ошибки и деградации" icon={<AlertTriangle size={17} />} tone="amber" />
          <MetricCard label="До ответа · медиана" value={d.ttfa_p50_ms == null ? '—' : `${d.ttfa_p50_ms} мс`} detail="После конца реплики до первого звука" icon={<Clock3 size={17} />} />
          <MetricCard label="До ответа · 95%" value={d.ttfa_p95_ms == null ? '—' : `${d.ttfa_p95_ms} мс`} detail="Ориентир, не гарантия" icon={<Clock3 size={17} />} tone="amber" />
          <MetricCard label="Voice responses" value={String(d.route_counts.voice)} detail="Голосовой маршрут" icon={<Headphones size={17} />} tone="green" />
        </div>
        <div className="admin-grid-two">
          <AdminPanel title="Задержки по сервисам" eyebrow="Медиана и 95%">
            <div className="latency-bars">{d.latency_spans.map((span, index) => <div className="latency-row" key={span.name}><div className="latency-row__label"><span>{span.name}</span><small>{span.p50_ms == null ? '—' : `${span.p50_ms} / ${span.p95_ms ?? '—'} мс`}</small></div><div className="latency-row__track"><span className={`latency-row__bar latency-row__bar--${span.status ?? 'ok'}`} style={{ width: `${Math.min(100, (span.p95_ms ?? 0) / 1200 * 100)}%` }} /></div><span className="latency-row__index">0{index + 1}</span></div>)}</div>
            <p className="admin-footnote">Этапы могут идти параллельно. Для реальных звонков внешняя модель не используется без отдельного согласования.</p>
          </AdminPanel>
          <AdminPanel title="Классификация обращений" eyebrow="Частые темы">
            {d.top_intents.length ? <div className="track-intent-list">{d.top_intents.map((item, index) => <div className="track-intent-row" key={item.intent}><span className="track-intent-row__number">0{index + 1}</span><span className="track-intent-row__label">{item.intent.replaceAll('_', ' ')}</span><strong>{item.count}</strong><span className="track-intent-row__bar"><i style={{ width: `${Math.max(5, item.count / Math.max(1, d.total_calls) * 100)}%` }} /></span></div>)}</div> : <div className="track-empty-state">Данные классификации пока отсутствуют.</div>}
            <p className="admin-footnote">В live-режиме эти значения рассчитывает backend, а не выборка браузера.</p>
          </AdminPanel>
        </div>
        <AdminPanel title="Быстрые переходы" eyebrow="Разделы"><div className="track-admin-shortcuts"><Link to="/calls"><PhoneCall size={18} /><span><strong>История звонков</strong><small>Транскрипты, маршруты и правки</small></span><ArrowUpRight size={15} /></Link><Link to="/scenarios"><GitBranch size={18} /><span><strong>Сценарии и правила</strong><small>Черновик, публикация и версии</small></span><ArrowUpRight size={15} /></Link><Link to="/admin/knowledge"><BarChart3 size={18} /><span><strong>Источники знаний</strong><small>Материалы и актуальность</small></span><ArrowUpRight size={15} /></Link></div></AdminPanel>
        <div className="track-page-footnote"><Clock3 size={14} /> p50 ≤ 400 мс — stretch target для короткого сценария на тёплом стенде, не обещание SLA. <Link to="/calls">Посмотреть звонки <ArrowRight size={13} /></Link></div>
      </>}
    </div>
  );
}
