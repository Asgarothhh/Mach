import { useState } from 'react';
import { CheckCircle2, CircleAlert, Database, FileSearch, RefreshCw, RotateCcw, ShieldCheck } from 'lucide-react';
import { SectionHeading } from '../../../shared/components/SectionHeading';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { env } from '../../../shared/config/env';
import { useTenant } from '../../tenant/model/TenantContext';
import { AdminPanel, MetricCard } from '../components/AdminPrimitives';

export function IngestionPage() {
  const { tenantId, tenantName } = useTenant();
  const hasDemoFixture = env.demoMode && tenantId === 'demo-business-01';
  const [started, setStarted] = useState(false);
  const [activeIndex, setActiveIndex] = useState('tenant-demo-r1');
  return (
    <div className="admin-page-stack">
      <SectionHeading eyebrow="TENANT KNOWLEDGE PIPELINE" title="Синхронизация знаний" description={`Dry-run → review diff → smoke tests → атомарная публикация индекса для ${tenantName}.`} action={<StatusBadge tone={hasDemoFixture ? 'demo' : 'neutral'}>{hasDemoFixture ? 'Demo fixture' : 'API не подключён'}</StatusBadge>} />
      <div className="inline-alert inline-alert--info"><CircleAlert size={17} /><div><strong>{hasDemoFixture ? "Публикация не выполняется в демо" : "Ingestion API ещё не подключён"}</strong><p>{hasDemoFixture ? "Кнопки меняют только локальный mock-state. Рабочий ingestion должен запускаться через защищённый backend API после tenant RBAC и approval checks." : "Реальный запуск, активация и rollback недоступны в UI до подключения защищённого backend API. Фиктивные результаты не показываются."}</p></div></div>
      <div className="metric-grid metric-grid--four"><MetricCard label="Последний run" value={hasDemoFixture ? 'dry-tenant-demo' : '—'} detail={hasDemoFixture ? 'Синтетическая запись' : 'Нет подтверждённых runs'} icon={<RefreshCw size={17} />} /><MetricCard label="Добавлено" value={hasDemoFixture ? '4' : '—'} detail={hasDemoFixture ? 'Demo result' : 'API ещё не подключён'} icon={<FileSearch size={17} />} /><MetricCard label="Изменено" value={hasDemoFixture ? '2' : '—'} detail={hasDemoFixture ? 'Demo result' : 'API ещё не подключён'} icon={<Database size={17} />} /><MetricCard label="Ошибки" value={hasDemoFixture ? '0' : '—'} detail={hasDemoFixture ? 'Demo fixture' : 'API ещё не подключён'} icon={<CircleAlert size={17} />} /></div>
      <AdminPanel title="Запуск синхронизации" eyebrow={`CONTROL PLANE · ${tenantId}`}><div className="sync-run-card"><div><strong>Одобренные источники текущего tenant</strong><p>Проверка allowlist, conditional GET, парсинг, нормализация, чанкинг и candidate index. Источники других tenants не должны попадать в этот run.</p><div className="sync-chips"><StatusBadge>HTML / PDF / DOCX</StatusBadge><StatusBadge>Respect robots.txt</StatusBadge><StatusBadge>Rate limit</StatusBadge></div></div><button className="button button--primary" type="button" onClick={() => { if (hasDemoFixture) setStarted(true); }} disabled={!hasDemoFixture} title={env.demoMode ? 'Локальный демонстрационный сценарий' : 'Нужно подключить защищённый ingestion API'}><RefreshCw size={16} /> Запустить dry-run</button></div>
        {started && hasDemoFixture && <div className="inline-success inline-success--block"><CheckCircle2 size={18} /><div><strong>Демо dry-run завершён</strong><p>Added 4 · changed 2 · unchanged 8 · failed 0. Это локальный пример, реальный crawler не запускался.</p></div></div>}
        <p className="admin-footnote">Все ingestion runs должны содержать `tenant_id`, owner/approval source metadata, current index revision и smoke-test report. Полная синхронизация требует роли knowledge_editor и audit event.</p>
      </AdminPanel>
      <AdminPanel title="Активная версия и rollback" eyebrow="INDEX LIFECYCLE"><div className="index-switch-row"><div><span>Текущий active index</span><strong>{hasDemoFixture ? activeIndex : '—'}</strong><small>Последняя зелёная ревизия в демо</small></div><button className="button button--secondary" type="button" onClick={() => { if (hasDemoFixture) setActiveIndex((value) => value === 'tenant-demo-r1' ? 'tenant-demo-r0' : 'tenant-demo-r1'); }} disabled={!hasDemoFixture} title={env.demoMode ? 'Изменить только demo fixture' : 'Нужно подключить защищённый rollback API'}><RotateCcw size={15} /> Демо rollback</button></div><div className="pipeline-steps">{['Fetch approved URLs', 'Parse & normalize', 'Chunk & embed', 'Candidate index', 'Smoke tests', 'Promote / rollback'].map((step, index) => <div key={step} className={`pipeline-step ${hasDemoFixture && index < 4 ? 'is-complete' : ''}`}><span>{index < 4 ? <CheckCircle2 size={15} /> : index + 1}</span><strong>{step}</strong></div>)}</div></AdminPanel>
      <div className="track-info-panel"><ShieldCheck size={18} /><div><strong>Legacy corpus изолирован</strong><p>Публичные материалы МТС предыдущего прототипа находятся в отдельном fixture <code>mts-public-demo</code> и не подключаются к текущему tenant автоматически.</p></div></div>
    </div>
  );
}
