import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, ArrowLeft, ArrowUpRight, Clock3, Filter, RefreshCw, Server, ShieldCheck } from 'lucide-react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { SectionHeading } from '../../../shared/components/SectionHeading';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { env } from '../../../shared/config/env';
import { useTenant } from '../../tenant/model/TenantContext';
import {
  createBackendSession,
  listBackendSessions,
  sessionStatusLabels,
  sessionStatusTone,
  type BackendSessionSummary,
  type SessionStatus,
} from '../services/adminSessions.service';

const PAGE_SIZE = 20;
const statusOptions: SessionStatus[] = [
  'CREATED', 'CONNECTING', 'NOTICE_PENDING', 'LISTENING', 'ENDPOINT_PENDING',
  'TRANSCRIBING_FINAL', 'ROUTING', 'RETRIEVING', 'GENERATING', 'SPEAKING',
  'INTERRUPTED', 'DEGRADED', 'CHAT_HANDOFF', 'HUMAN_HANDOFF', 'CLOSED',
];

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU');
}

export function AdminSessionsPage() {
  if (!env.backendAdminSessions) return <Navigate to="/admin/calls" replace />;
  return <BackendAdminSessionsPage />;
}

function BackendAdminSessionsPage() {
  const { tenantId, tenantName } = useTenant();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<BackendSessionSummary[]>([]);
  const [status, setStatus] = useState<SessionStatus | ''>('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createBusy, setCreateBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listBackendSessions({
        tenantId: tenantId || env.backendTestTenantId,
        status,
        limit: PAGE_SIZE,
        offset,
      });
      setSessions(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить сессии из API.');
      setSessions([]);
    } finally {
      setLoading(false);
    }
  }, [tenantId, status, offset]);

  useEffect(() => { void load(); }, [load]);

  async function createTestSession() {
    setCreateBusy(true);
    setError(null);
    try {
      const created = await createBackendSession({
        tenant_id: tenantId || env.backendTestTenantId,
        channel: 'mock',
        language: 'ru',
      });
      navigate(`/admin/sessions/${encodeURIComponent(created.session_id)}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось создать тестовую сессию.');
    } finally {
      setCreateBusy(false);
    }
  }

  const visibleSessions = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return sessions;
    return sessions.filter((session) => session.session_id.toLowerCase().includes(query));
  }, [sessions, search]);
  const hasNextPage = sessions.length === PAGE_SIZE;

  return (
    <div className="track-page">
      <SectionHeading
        eyebrow="BACKEND SESSION API"
        title="Сессии и транскрипты"
        description={`Реальные данные API · ${tenantName} · tenant ID: ${tenantId || env.backendTestTenantId}`}
        action={<div className="track-heading-actions"><StatusBadge tone="success" dot>Backend API</StatusBadge><button type="button" className="button button--primary button--small" onClick={() => void createTestSession()} disabled={createBusy}><ArrowUpRight size={14} /> {createBusy ? 'Создаём…' : 'Создать тестовую сессию'}</button><button type="button" className="button button--secondary button--small" onClick={() => void load()} disabled={loading}><RefreshCw size={14} /> Обновить</button></div>}
      />

      <div className="track-info-panel">
        <Server size={18} />
        <div><strong>Подключён ограниченный набор API</strong><p>Список, фильтр по статусу, детали, коррекция транскрипта и действия с сессией используют backend. API пока не возвращает общее количество записей, поэтому пагинация работает по limit/offset.</p></div>
      </div>

      <section className="track-panel">
        <div className="track-panel__heading"><div><span className="track-eyebrow">SESSION FILTERS</span><h2>Поиск сессий</h2></div><span className="track-result-count">{loading ? 'Загрузка…' : `${visibleSessions.length} на странице`}</span></div>
        <div className="track-filters">
          <label className="track-field"><span>ID сессии на текущей странице</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Вставьте session_id" /></label>
          <label className="track-field"><span>Статус</span><select value={status} onChange={(event) => { setStatus(event.target.value as SessionStatus | ''); setOffset(0); }}><option value="">Все статусы</option>{statusOptions.map((value) => <option key={value} value={value}>{sessionStatusLabels[value]}</option>)}</select></label>
        </div>
        {error && <div className="track-form-error" role="alert"><AlertCircle size={16} /> {error}<p>Проверьте VITE_API_BASE_URL, CORS, tenant ID и доступность эндпоинтов из предоставленного OpenAPI.</p></div>}
      </section>

      <section className="track-panel">
        <div className="track-panel__heading"><div><span className="track-eyebrow">SESSIONS</span><h2>Журнал сессий</h2></div><span className="track-result-count">Offset {offset} · limit {PAGE_SIZE}</span></div>
        {loading ? <div className="track-empty-state"><span className="loading-dot" />Загружаем сессии из backend…</div> : visibleSessions.length === 0 ? <div className="track-empty-state"><Filter size={25} /><strong>Сессии не найдены</strong><span>{search ? 'Измените поисковый запрос.' : 'Для этого tenant и фильтра API не вернул записей.'}</span></div> : <div className="track-table-wrap"><table className="track-table"><thead><tr><th>Session ID</th><th>Создана</th><th>Статус</th><th>Детали</th></tr></thead><tbody>{visibleSessions.map((session) => <tr key={session.session_id}><td><Link className="track-call-id" to={`/admin/sessions/${encodeURIComponent(session.session_id)}`}>{session.session_id}<ArrowUpRight size={13} /></Link></td><td>{formatDate(session.created_at)}</td><td><StatusBadge tone={sessionStatusTone(session.status)}>{sessionStatusLabels[session.status] ?? session.status}</StatusBadge><small>{session.status}</small></td><td><Link className="table-action-link" to={`/admin/sessions/${encodeURIComponent(session.session_id)}`}>Открыть <ArrowUpRight size={13} /></Link></td></tr>)}</tbody></table></div>}
        <div className="track-table-foot"><span><ShieldCheck size={13} /> Доступ и tenant isolation должны проверяться backend; выбранный tenant в UI не является авторизацией.</span><span><button type="button" className="button button--secondary button--small" disabled={loading || offset === 0} onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}><ArrowLeft size={13} /> Предыдущая</button><button type="button" className="button button--secondary button--small" disabled={loading || !hasNextPage} onClick={() => setOffset((current) => current + PAGE_SIZE)}>Следующая <ArrowUpRight size={13} /></button></span></div>
        <p className="track-panel-footnote"><Clock3 size={12} /> ID-поиск фильтрует только полученную страницу. Серверный поиск и total count отсутствуют в предоставленном OpenAPI.</p>
      </section>
    </div>
  );
}
