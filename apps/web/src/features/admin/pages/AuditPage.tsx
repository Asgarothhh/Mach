import { AlertTriangle, Fingerprint, LockKeyhole, ShieldCheck } from 'lucide-react';
import { SectionHeading } from '../../../shared/components/SectionHeading';
import { env } from '../../../shared/config/env';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { AdminPanel, MetricCard } from '../components/AdminPrimitives';
import { demoAuditEvents } from '../data/demoData';
import { useTenant } from '../../tenant/model/TenantContext';

export function AuditPage() {
  const { tenantId } = useTenant();
  const hasDemoFixture = env.demoMode && tenantId === 'demo-business-01';
  return (
    <div className="admin-page-stack">
      <SectionHeading
        eyebrow="Аудит"
        title="Аудит и безопасность"
        description="Доступ к сессиям, маскирование PII, попытки prompt injection и изменение политик."
        action={<StatusBadge tone={hasDemoFixture ? 'demo' : 'neutral'}>{hasDemoFixture ? 'Masked view · demo' : 'Audit API pending'}</StatusBadge>}
      />

      {hasDemoFixture ? <div className="metric-grid metric-grid--four">
        <MetricCard label="Security events" value="14" detail="Синтетические события" icon={<ShieldCheck size={17} />} tone="green" />
        <MetricCard label="PII masked" value="9" detail="Значения не отображаются" icon={<Fingerprint size={17} />} />
        <MetricCard label="Prompt injection flags" value="3" detail="Тестовые сценарии" icon={<AlertTriangle size={17} />} tone="amber" />
        <MetricCard label="Denied access" value="2" detail="Пример RBAC отказов" icon={<LockKeyhole size={17} />} tone="red" />
      </div> : <div className="inline-alert inline-alert--info"><ShieldCheck size={17} /><div><strong>{env.demoMode ? 'Для выбранного tenant нет audit fixtures' : 'Audit API не подключён'}</strong><p>Здесь не показываются фиктивные security events. Live-журнал должен приходить из авторизованного backend API.</p></div></div>}

      {hasDemoFixture && <AdminPanel title="Журнал аудита" eyebrow="Последние события">
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>Время</th><th>Actor</th><th>Event</th><th>Detail</th><th>Policy</th><th /></tr></thead>
            <tbody>
              {demoAuditEvents.map((item) => (
                <tr key={`${item.time}-${item.event}`}>
                  <td>{item.time}</td>
                  <td><code>{item.actor}</code></td>
                  <td><span className="intent-chip">{item.event}</span></td>
                  <td>{item.detail}</td>
                  <td><StatusBadge tone="success">masked</StatusBadge></td>
                  <td><span className="subtle-label">Demo</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="admin-footnote">Примеры содержат только метаданные и синтетические IDs. Реальные транскрипты и PII не должны попадать в общий audit log.</p>
      </AdminPanel>}

      <div className="admin-grid-two">
        <AdminPanel title="Границы доверия" eyebrow="Данные">
          <div className="trust-zones">
            <div><strong>A · Браузер</strong><span>Короткий ключ сессии, без серверных секретов.</span></div>
            <div><strong>B · Trusted services</strong><span>ASR, RAG, guardrails, БД и административный control plane.</span></div>
            <div><strong>C · External LLM</strong><span>Только минимизированный текст и публичные evidence.</span></div>
          </div>
        </AdminPanel>
        <AdminPanel title="Права доступа" eyebrow="Роли">
          <div className="role-list">
            <div><strong>viewer</strong><span>Агрегированные метрики и маскированные сессии</span></div>
            <div><strong>support_supervisor</strong><span>Чтение транскриптов и маркировка качества</span></div>
            <div><strong>knowledge_editor</strong><span>Dry-run и публикация индекса</span></div>
            <div><strong>security_auditor</strong><span>Security events и audit log</span></div>
          </div>
        </AdminPanel>
      </div>
    </div>
  );
}
