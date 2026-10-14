import { AlertTriangle, CheckCircle2, ListChecks, ShieldCheck } from 'lucide-react';
import { SectionHeading } from '../../../shared/components/SectionHeading';
import { env } from '../../../shared/config/env';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { useTenant } from '../../tenant/model/TenantContext';
import { AdminPanel, MetricCard, TableStatus } from '../components/AdminPrimitives';

const annotations = [
  { id: 'QA-001', call: 'call-d7f3a', label: 'correct', detail: 'Ответ соответствует синтетическому approved fixture', status: 'Reviewed' },
  { id: 'QA-002', call: 'call-b92df', label: 'routing_error', detail: 'Проверить условие, по которому сложное обращение направлено в чат', status: 'Review needed' },
  { id: 'QA-003', call: 'call-c3e0f', label: 'no_evidence', detail: 'Корректный fallback при отсутствии подтверждённого источника', status: 'Reviewed' },
  { id: 'QA-004', call: 'call-c104a', label: 'handoff_failed', detail: 'Проверить результат transfer adapter и fallback', status: 'Review needed' },
];

export function QualityPage() {
  const { tenantId, tenantName } = useTenant();
  const hasDemoFixture = env.demoMode && tenantId === 'demo-business-01';
  return <div className="admin-page-stack">
    <SectionHeading eyebrow="Качество" title="Проверка качества" description={`ASR transcription, источники, routing и причины fallback для ${tenantName}.`} action={<StatusBadge tone="warning">Требует review</StatusBadge>} />
    {hasDemoFixture ? <div className="demo-data-callout"><ShieldCheck size={17} /><span>Список — synthetic fixtures только для tenant <code>{tenantId}</code>. Переключение review не создаёт production annotation или audit event.</span></div> : <div className="inline-alert inline-alert--info"><ShieldCheck size={17} /><div><strong>{env.demoMode ? 'Для этого tenant нет quality fixtures' : 'Quality review API не подключён'}</strong><p>Не отображаем вымышленные аннотации. Корректировки транскриптов доступны на странице деталей звонка, если backend выдаёт соответствующую роль.</p></div></div>}
    {hasDemoFixture && <><div className="metric-grid metric-grid--four"><MetricCard label="Reviewed" value="2" detail="Демо-записи" icon={<CheckCircle2 size={17} />} tone="green" /><MetricCard label="Review needed" value="2" detail="Требует ручной проверки" icon={<ListChecks size={17} />} tone="amber" /><MetricCard label="Routing issues" value="1" detail="Пример классификации" icon={<AlertTriangle size={17} />} tone="red" /><MetricCard label="Security checks" value="Synthetic" detail="Нет реальных клиентских данных" icon={<ShieldCheck size={17} />} /></div>
    <AdminPanel title="Аннотации качества" eyebrow="Проверка"><div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>ID</th><th>Call</th><th>Метка</th><th>Комментарий</th><th>Статус</th><th /></tr></thead><tbody>{annotations.map((item) => <tr key={item.id}><td><code>{item.id}</code></td><td>{item.call}</td><td><span className="intent-chip">{item.label}</span></td><td>{item.detail}</td><td><TableStatus value={item.status} /></td><td><button className="table-action-link" type="button" onClick={(event) => { if (hasDemoFixture) event.currentTarget.textContent = event.currentTarget.textContent === 'Review' ? 'Reviewed' : 'Review'; }} disabled={!hasDemoFixture} title="Демо: локальное переключение без audit backend">Review</button></td></tr>)}</tbody></table></div><p className="admin-footnote">Реальные исправления транскрипта должны сохранять исходную ревизию, diff, editor ID, reason, timestamp и audit event.</p></AdminPanel></>}
    <AdminPanel title="Проверяемые категории" eyebrow="Категории"><div className="quality-tags">{['correct', 'unsupported', 'wrong_source', 'stale_source', 'ASR_error', 'TTS_issue', 'routing_error', 'handoff_failed', 'latency_issue', 'privacy_issue', 'no_evidence'].map((tag) => <span key={tag}>{tag}</span>)}</div></AdminPanel>
  </div>;
}
