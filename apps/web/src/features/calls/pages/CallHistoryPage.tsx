import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowDownToLine, ArrowUpRight, Filter, Headphones, PhoneCall, RefreshCw, Search, MessageSquare, UserRound, FileText } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { SectionHeading } from '../../../shared/components/SectionHeading';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { env } from '../../../shared/config/env';
import { useTenant } from '../../tenant/model/TenantContext';
import type { CallSummary, CallStatus, ChannelChoice } from '../../../shared/types/track1';
import { listCalls } from '../services/calls.service';

const statusLabels: Record<CallStatus, string> = { active: 'Активен', completed: 'Завершён', degraded: 'Деградация', handoff: 'Передан', failed: 'Ошибка' };
const routeLabels: Record<ChannelChoice, string> = { voice: 'Голос', chat_offer: 'Предложен чат', human_handoff: 'Человек', fallback: 'Fallback' };
const intentLabels: Record<string, string> = {
  service_question: 'Вопрос об услуге', pricing_question: 'Стоимость / сроки', complex_request: 'Сложное обращение', human_requested: 'Запрос человека', opening_hours: 'Режим работы', general_question: 'Общий вопрос', onboarding_test_call: 'Тестовый звонок',
};

function StatusPill({ status }: { status: CallStatus }) {
  const tone = status === 'completed' ? 'success' : status === 'active' ? 'neutral' : status === 'handoff' ? 'warning' : status === 'failed' ? 'danger' : 'neutral';
  return <StatusBadge tone={tone}>{statusLabels[status]}</StatusBadge>;
}

function RoutePill({ decision }: { decision: ChannelChoice }) {
  const Icon = decision === 'voice' ? Headphones : decision === 'chat_offer' ? MessageSquare : decision === 'human_handoff' ? UserRound : FileText;
  return <span className={`track-route-pill track-route-pill--${decision}`}><Icon size={13} />{routeLabels[decision]}</span>;
}

export function CallHistoryPage() {
  const { tenantId, tenantName } = useTenant();
  const location = useLocation();
  const inAdmin = location.pathname.startsWith('/admin');
  const callDetailHref = (call: CallSummary) => `${inAdmin ? '/admin/calls' : '/calls'}/${encodeURIComponent(inAdmin ? call.session_id : call.call_id)}`;
  const [calls, setCalls] = useState<CallSummary[]>([]);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const [route, setRoute] = useState('all');
  const [channel, setChannel] = useState('all');
  const [intent, setIntent] = useState('all');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 8;
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listCalls({ tenantId, query, status, route, channel, intent, from, to, page, pageSize, scope: inAdmin ? 'admin' : 'tenant' });
      setCalls(result.items);
      setTotal(result.total);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить историю звонков.');
    } finally {
      setLoading(false);
    }
  }, [tenantId, query, status, route, channel, intent, from, to, page, inAdmin]);

  useEffect(() => { void load(); }, [load]);
  const stats = useMemo(() => ({ total, human: calls.filter((call) => call.route_decision === 'human_handoff').length, chat: calls.filter((call) => call.route_decision === 'chat_offer').length }), [calls, total]);
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  function downloadCsv() {
    // This action is only rendered in demo mode and contains synthetic fixture rows.
    const header = ['call_id', 'created_at', 'status', 'channel', 'intent', 'route_decision', 'turn_count'];
    const rows = calls.map((call) => [call.call_id, call.created_at, call.status, call.channel, call.intent, call.route_decision, call.turn_count]);
    const csv = [header, ...rows].map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\r\n');
    const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'demo-call-history.csv'; anchor.click(); URL.revokeObjectURL(url);
  }

  return (
    <div className="track-page">
      <SectionHeading eyebrow="Звонки" title="История звонков" description={`Входящие обращения · ${tenantName}. Номера и личные данные скрываются.`} action={<div className="track-heading-actions"><Link className="button button--secondary button--small" to="/voice/permission"><Headphones size={15} /> Голосовой помощник</Link><Link className="button button--primary button--small" to="/onboarding"><PhoneCall size={15} /> Тестовый вызов</Link></div>} />

      {env.demoMode && <div className="track-demo-banner"><span className="track-demo-dot" /><div><strong>Синтетическая история</strong><p>В демо видны только записи активного tenant. Mock/test-call не означает подключение к телефонной сети МТС.</p></div><StatusBadge tone="demo">DEMO</StatusBadge></div>}

      <div className="track-mini-metrics">
        <div className="track-mini-metric"><span>Звонков в выборке</span><strong>{stats.total}</strong><small>Текущие фильтры</small></div>
        <div className="track-mini-metric"><span>Предложен чат</span><strong>{stats.chat}</strong><small>Перевод в текстовый чат</small></div>
        <div className="track-mini-metric"><span>Передача человеку</span><strong>{stats.human}</strong><small>Перевод сотруднику</small></div>
        <div className="track-mini-metric"><span>Активный профиль</span><strong className="track-mini-metric__tenant">{tenantName}</strong><small><span className="track-tenant-lock">Только эта компания</span></small></div>
      </div>

      <section className="track-panel">
        <div className="track-panel__heading"><div><span className="track-eyebrow">Поиск</span><h2>Фильтры звонков</h2></div><div className="track-panel__actions">{env.demoMode && <button className="button button--secondary button--small" onClick={downloadCsv}><ArrowDownToLine size={14} /> Экспорт синтетических данных</button>}<button className="button button--secondary button--small" onClick={() => void load()} disabled={loading}><RefreshCw size={14} /> Обновить</button></div></div>
        <div className="track-filters">
          <label className="track-search"><Search size={16} /><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="Номер, тема или имя звонящего" aria-label="Поиск звонков" /></label>
          <label className="track-field"><span>Статус</span><select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="all">Все статусы</option><option value="active">Активен</option><option value="completed">Завершён</option><option value="degraded">Деградация</option><option value="handoff">Передан</option><option value="failed">Ошибка</option></select></label>
          <label className="track-field"><span>Маршрут</span><select value={route} onChange={(event) => { setRoute(event.target.value); setPage(1); }}><option value="all">Все маршруты</option><option value="voice">Голос</option><option value="chat_offer">Предложен чат</option><option value="human_handoff">Человек</option><option value="fallback">Уточнение</option></select></label>
          <label className="track-field"><span>Канал</span><select value={channel} onChange={(event) => { setChannel(event.target.value); setPage(1); }}><option value="all">Все каналы</option><option value="telephone">Телефон</option><option value="test_call">Тестовый вызов</option><option value="browser_test">Браузер</option></select></label>
          <label className="track-field"><span>Тип обращения</span><select value={intent} onChange={(event) => { setIntent(event.target.value); setPage(1); }}><option value="all">Все темы</option>{[...new Set(calls.map((call) => call.intent))].sort().map((value) => <option value={value} key={value}>{intentLabels[value] ?? value}</option>)}</select></label>
          <label className="track-field"><span>С даты</span><input type="date" value={from} max={to || undefined} onChange={(event) => { setFrom(event.target.value); setPage(1); }} /></label>
          <label className="track-field"><span>По дату</span><input type="date" value={to} min={from || undefined} onChange={(event) => { setTo(event.target.value); setPage(1); }} /></label>
        </div>
        {error && <div className="track-form-error" role="alert">{error}</div>}
      </section>

      <section className="track-panel">
        <div className="track-panel__heading"><div><span className="track-eyebrow">Обращения</span><h2>Журнал обращений</h2></div><span className="track-result-count">{loading ? 'Загрузка…' : `${total} записей`}</span></div>
        {loading ? <div className="track-empty-state"><span className="loading-dot" />Загружаем звонки выбранной компании…</div> : calls.length === 0 ? <div className="track-empty-state"><Filter size={25} /><strong>Звонки не найдены</strong><span>Измените фильтры или запустите тестовый вызов из подключения.</span></div> : <div className="track-table-wrap"><table className="track-table"><thead><tr><th>Звонок / время</th><th>Звонящий</th><th>Тема</th><th>Маршрут</th><th>Согласие</th><th>Ходы</th><th>До ответа</th><th>Статус</th><th /></tr></thead><tbody>{calls.map((call) => <tr key={call.call_id}>
          <td><Link className="track-call-id" to={callDetailHref(call)}>{call.call_id}<ArrowUpRight size={13} /></Link><small>{new Date(call.created_at).toLocaleString('ru-RU', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: 'short' })}</small></td>
          <td>{call.caller_alias}<small>{call.channel === 'telephone' ? 'Входящий телефон' : call.channel === 'test_call' ? 'Тестовый вызов' : 'Браузер'}</small></td>
          <td><span className="track-intent-chip">{intentLabels[call.intent] ?? call.intent}</span></td><td><RoutePill decision={call.route_decision} /></td>
          <td><span className={`track-consent track-consent--${call.consent_state}`}>{call.consent_state === 'accepted' ? 'Согласие есть' : call.consent_state === 'declined' ? 'Отказ' : call.consent_state === 'pending' ? 'Ожидание' : 'Demo'}</span></td><td>{call.turn_count}</td><td>{call.ttfa_ms == null ? '—' : `${call.ttfa_ms} мс`}</td><td><StatusPill status={call.status} /></td><td><Link className="track-table-link" to={callDetailHref(call)} aria-label={`Открыть звонок ${call.call_id}`}><ArrowUpRight size={17} /></Link></td>
        </tr>)}</tbody></table></div>}
        <div className="track-table-foot"><span>Номера показываются в скрытом виде. Полный транскрипт доступен только сотрудникам вашей компании.{!env.demoMode ? ' Экспорт появится после отдельного согласования.' : ' Экспорт содержит только демонстрационные записи.'} Фильтры по маршруту, каналу и дате применяются на клиенте к не более чем 100 последним сессиям.</span></div>
        <div className="track-pagination" aria-label="Страницы истории звонков"><span>Страница {page} из {pageCount}</span><div><button type="button" className="button button--secondary button--small" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={page <= 1 || loading}>Назад</button><button type="button" className="button button--secondary button--small" onClick={() => setPage((value) => Math.min(pageCount, value + 1))} disabled={page >= pageCount || loading}>Далее</button></div></div>
      </section>
    </div>
  );
}
