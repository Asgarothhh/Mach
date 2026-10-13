import { ArrowUpRight, CheckCircle2, Clock3, Globe2, RefreshCw, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { SectionHeading } from '../../../shared/components/SectionHeading';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { env } from '../../../shared/config/env';
import { useTenant } from '../../tenant/model/TenantContext';
import { demoSources } from '../../knowledge/data/demoSources';
import { legacyMtsDemoTenant } from '../../knowledge/data/legacyMtsDemoSources';
import { AdminPanel, MetricCard } from '../components/AdminPrimitives';

export function KnowledgePage() {
  const { tenantId, tenantName } = useTenant();
  const hasDemoFixture = env.demoMode && tenantId === 'demo-business-01';
  const docs = hasDemoFixture ? demoSources : [];
  return (
    <div className="admin-page-stack">
      <SectionHeading eyebrow="TENANT KNOWLEDGE BASE" title="Источники знаний" description={`Одобренные документы компании ${tenantName}. Реестр и active index всегда должны быть привязаны к текущему tenant.`} action={<Link to="/admin/sync" className="button button--primary button--small"><RefreshCw size={15} /> Dry-run синхронизации</Link>} />
      {hasDemoFixture ? <div className="demo-data-callout"><ShieldCheck size={17} /><span>Показаны синтетические fixtures для tenant <code>{tenantId}</code>. Они не означают, что ingestion запускался или источники реально одобрены владельцем данных.</span></div> : <div className="inline-alert inline-alert--info"><ShieldCheck size={17} /><div><strong>{env.demoMode ? 'Для выбранного tenant нет source fixtures' : 'Источник данных API не подключён'}</strong><p>{env.demoMode ? 'Новый tenant начинается с пустой базой знаний. Legacy MTS corpus остаётся в отдельном regression tenant.' : 'Не показываем фиктивные документы как production данные. Подключите tenant-scoped Knowledge API.'}</p></div></div>}
      <div className="metric-grid metric-grid--four">
        <MetricCard label="Источники в fixtures" value={String(docs.length)} detail="Демо-примеры" icon={<Globe2 size={17} />} />
        <MetricCard label="Approved sources" value="0" detail="Нет реальных approvals в mock" icon={<CheckCircle2 size={17} />} />
        <MetricCard label="Требуют проверки" value={String(docs.length)} detail="Синтетические записи" icon={<Clock3 size={17} />} tone="amber" />
        <MetricCard label="Active index" value={hasDemoFixture ? "demo-r1" : "—"} detail={hasDemoFixture ? "Не результат реальной индексации" : "Нет подтверждённого индекса"} icon={<RefreshCw size={17} />} />
      </div>
      <AdminPanel title="Реестр источников текущего tenant" eyebrow={`TENANT · ${tenantId}`}>
        <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Источник</th><th>Тип</th><th>Approval</th><th>Свежесть</th><th>Revision</th><th /></tr></thead><tbody>{docs.map((doc) => <tr key={doc.id}>
          <td><strong>{doc.title}</strong><a className="table-url" href={doc.url} target="_blank" rel="noopener noreferrer">{doc.url}</a></td><td>Demo fixture</td><td><StatusBadge tone="warning">Не подтверждён</StatusBadge></td><td>Не проверено</td><td><code>{doc.revisionId}</code></td><td><a className="icon-link" href={doc.url} target="_blank" rel="noopener noreferrer" aria-label={`Открыть ${doc.title}`}><ArrowUpRight size={15} /></a></td>
        </tr>)}{docs.length === 0 && <tr><td colSpan={6}>Нет источников для отображения. Добавление и approval выполняются через tenant-scoped backend.</td></tr>}</tbody></table></div>
        <p className="admin-footnote">Для production-источника нужны owner, approval status, content hash, `tenant_id`, revision, дата получения и effective status. Пустое evidence — допустимый результат; бот не должен выдумывать ответ.</p>
      </AdminPanel>
      <div className="admin-grid-two">
        <AdminPanel title="Политика актуальности" eyebrow="FRESHNESS RULES"><div className="freshness-grid"><div><strong>Динамические цены и условия</strong><span>Интервал задаёт владелец tenant; стартовый ориентир — 4–6 часов</span></div><div><strong>FAQ и описание услуг</strong><span>Стартовый ориентир — раз в сутки</span></div><div><strong>Юридические документы</strong><span>Проверка ежедневно и по хэшу</span></div><div><strong>Статические страницы</strong><span>Стартовый ориентир — раз в 7 дней</span></div></div></AdminPanel>
        <AdminPanel title="Наследуемый corpus МТС" eyebrow="ISOLATED REGRESSION FIXTURE"><div className="track-info-panel"><ShieldCheck size={18} /><div><strong>{legacyMtsDemoTenant.display_name}</strong><p>Публичные материалы МТС сохранены только для регрессионных тестов прошлого прототипа. Они не входят в источники текущего tenant и не подключаются к его ответам.</p><span className="track-code-label">tenant_id: {legacyMtsDemoTenant.tenant_id}</span></div></div><ul className="track-legacy-source-list">{legacyMtsDemoTenant.sources.map((source) => <li key={source.url}><span>{source.title}</span><a href={source.url} target="_blank" rel="noopener noreferrer">Открыть <ArrowUpRight size={12} /></a></li>)}</ul></AdminPanel>
      </div>
    </div>
  );
}
