import { Activity, AudioLines, Database, Gauge, ShieldCheck } from 'lucide-react';
import { SectionHeading } from '../../../shared/components/SectionHeading';
import { env } from '../../../shared/config/env';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { useTenant } from '../../tenant/model/TenantContext';
import { AdminPanel, MetricCard } from '../components/AdminPrimitives';

const scores = [
  { name: 'ASR · Russian clean speech', metric: 'WER', value: '11,8%', target: '≤ 12%', status: 'Target met' },
  { name: 'RAG · gold set', metric: 'Recall@10', value: '0,91', target: '≥ 0,90', status: 'Target met' },
  { name: 'Grounding', metric: 'Valid source IDs', value: '100%', target: '100%', status: 'Target met' },
  { name: 'No-evidence set', metric: 'Correct abstention', value: '98,4%', target: '≥ 98%', status: 'Target met' },
  { name: 'Voice · warm short FAQ', metric: 'TTFA p50', value: '640 мс', target: '≤ 400 мс stretch', status: 'Stretch missed' },
];

export function EvaluationsPage() {
  const { tenantId } = useTenant();
  const hasDemoFixture = env.demoMode && tenantId === 'demo-business-01';
  return (
    <div className="admin-page-stack">
      <SectionHeading
        eyebrow="MODEL EVALUATION"
        title="Оценка моделей"
        description="История offline eval, качество распознавания, retrieval, grounding и задержки."
        action={<StatusBadge tone={hasDemoFixture ? 'demo' : 'neutral'}>{hasDemoFixture ? 'DEMO · eval-2026-10-11' : 'Evaluation API pending'}</StatusBadge>}
      />
      {hasDemoFixture ? <div className="demo-data-callout"><Activity size={17} /><span>Таблица ниже — пример отчёта для синтетических fixtures. Перед выбором моделей нужен реальный benchmark на закреплённых версиях и вашем тестовом наборе.</span></div> : <div className="inline-alert inline-alert--info"><Activity size={17} /><div><strong>{env.demoMode ? 'Для выбранного tenant нет evaluation fixtures' : 'Evaluation API не подключён'}</strong><p>Реальные результаты eval должны поступать из backend; пока не показываем примерные проценты как измерения.</p></div></div>}

      {hasDemoFixture && <><div className="metric-grid metric-grid--four">
        <MetricCard label="ASR WER" value="11,8%" detail="Чистая русская речь · demo" icon={<AudioLines size={17} />} tone="green" />
        <MetricCard label="RAG Recall@10" value="0,91" detail="Gold set · demo" icon={<Database size={17} />} tone="green" />
        <MetricCard label="Grounding" value="100%" detail="Валидные source IDs" icon={<ShieldCheck size={17} />} tone="green" />
        <MetricCard label="TTFA p50" value="640 мс" detail="Stretch goal не достигнут в примере" icon={<Gauge size={17} />} tone="amber" />
      </div>

      <AdminPanel title="Результаты набора тестов" eyebrow="REGRESSION REPORT">
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>Набор</th><th>Метрика</th><th>Результат</th><th>Target</th><th>Состояние</th></tr></thead>
            <tbody>
              {scores.map((score) => (
                <tr key={score.name}>
                  <td><strong>{score.name}</strong></td>
                  <td>{score.metric}</td>
                  <td>{score.value}</td>
                  <td>{score.target}</td>
                  <td><StatusBadge tone={score.status === 'Target met' ? 'success' : 'warning'}>{score.status}</StatusBadge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </AdminPanel>

      <div className="admin-grid-two">
        <AdminPanel title="Dataset registry" eyebrow="VERSIONED EVALS">
          <div className="dataset-list">
            <div><strong>ASR RU test set</strong><span>200+ utterances · digits, brands, noisy speech</span><small>asr-ru-v1 · synthetic/approved data only</small></div>
            <div><strong>RAG gold set</strong><span>150+ requests · expected source IDs</span><small>rag-mts-v1 · reviewed</small></div>
            <div><strong>Grounding / security</strong><span>No-evidence, stale-source, prompt-injection</span><small>guardrails-v1 · regression gate</small></div>
          </div>
        </AdminPanel>
        <AdminPanel title="Методика" eyebrow="REPRODUCIBILITY">
          <p className="muted-copy">Фиксируйте модель, provider route, hardware, active index revision, prompt hash и настройки для каждого запуска. Сравнивайте результаты только при одинаковых условиях.</p>
          <div className="test-gates">
            {['Unit / integration suite', 'Security regression suite', 'Retrieval and grounding report', 'Latency distribution p50 / p95 / p99'].map((item) => (
              <div key={item}><ShieldCheck size={16} />{item}</div>
            ))}
          </div>
        </AdminPanel>
      </div></>}
    </div>
  );
}
