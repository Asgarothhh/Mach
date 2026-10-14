import { Eye, LockKeyhole, Save, ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import { SectionHeading } from '../../../shared/components/SectionHeading';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { AdminPanel } from '../components/AdminPrimitives';
import { env } from '../../../shared/config/env';
import { useTenant } from '../../tenant/model/TenantContext';

type LlmCheck = { provider?: string; model_id?: string };

export function ConfigurationPage() {
  const [temperature, setTemperature] = useState('0.2');
  const [maxTokens, setMaxTokens] = useState('300');
  const [guardrails, setGuardrails] = useState(true);
  const [notice, setNotice] = useState(false);
  const [llm, setLlm] = useState<LlmCheck | null>(null);
  const { tenantName, tenantId } = useTenant();
  const externalLlmAllowed = llm?.provider === 'openrouter';

  useEffect(() => {
    const origin = env.apiBaseUrl.replace(/\/api\/v1$/i, '');
    void fetch(`${origin}/health/ready`, { headers: { Accept: 'application/json' } })
      .then((response) => (response.ok ? response.json() : null))
      .then((body: { checks?: { llm?: LlmCheck } } | null) => {
        if (body?.checks?.llm) setLlm(body.checks.llm);
      })
      .catch(() => undefined);
  }, []);

  return (
    <div className="admin-page-stack">
      <SectionHeading
        eyebrow="Настройки"
        title="Конфигурация и безопасность"
        description={`Версии сценариев, voice/chat/human routing, политики согласия и privacy для ${tenantName}.`}
        action={<StatusBadge tone="warning">Read-only demo</StatusBadge>}
      />
      <div className="inline-alert inline-alert--warning">
        <LockKeyhole size={18} />
        <div>
          <strong>Настройки не сохраняются на сервер</strong>
          <p>Tenant ID: <code>{tenantId}</code>. Изменение рабочих настроек требует серверной роли, versioning и audit event. OpenRouter API key здесь не показывается и не должен попадать в браузер.</p>
        </div>
      </div>
      <AdminPanel title="Политика обработки реальных звонков" eyebrow="Безопасность">
        <div className="track-info-panel track-info-panel--privacy"><ShieldCheck size={19} /><div><strong>Внешняя модель для реальных звонков выключена</strong><p>Для телефонных звонков внешняя модель не используется без отдельного согласования. Этот переключатель относится только к демонстрации и не сохраняет настройку на сервере.</p></div></div>
        <label className="toggle-row"><span><strong>Внешний LLM для synthetic demo</strong><small>Включён, когда /health/ready сообщает provider=openrouter. Не относится к реальному телефонному трафику.</small></span><input type="checkbox" checked={externalLlmAllowed} readOnly disabled /></label>
        <div className="policy-detail"><strong>Обязательные ограничения</strong><div><span>tenant_id</span><code>{tenantId}</code></div><div><span>External LLM for real calls</span><code>false until approval</code></div><div><span>Raw audio storage</span><code>false</code></div><div><span>Provider fallback</span><code>fail closed</code></div></div>
      </AdminPanel>

      <div className="admin-grid-two">
        <AdminPanel title="Модель для демонстрации" eyebrow="Разрешённые модели">
          <div className="form-stack">
            <label>
              <span>Основная модель (model ID)</span>
              <input value={llm?.model_id || 'google/gemma-4-26b-a4b-it'} readOnly />
              <small>Провайдер: {llm?.provider || 'неизвестно'}</small>
            </label>
            <label>
              <span>Резервная модель</span>
              <input value="нет внешнего fallback" readOnly />
            </label>
            <div className="form-grid-two">
              <label><span>Temperature</span><input value={temperature} onChange={(event) => setTemperature(event.target.value)} inputMode="decimal" /></label>
              <label><span>Max tokens</span><input value={maxTokens} onChange={(event) => setMaxTokens(event.target.value)} inputMode="numeric" /></label>
            </div>
            <div className="policy-detail">
              <strong>Provider policy</strong>
              <div><span>data_collection</span><code>deny</code></div>
              <div><span>require ZDR</span><code>true</code></div>
              <div><span>Unknown route</span><code>fail closed</code></div>
            </div>
          </div>
        </AdminPanel>

        <AdminPanel title="Правила проверки" eyebrow="Вход и выход">
          <label className="toggle-row">
            <span><strong>Входная проверка</strong><small>PII detection, prompt injection, scope</small></span>
            <input type="checkbox" checked={guardrails} onChange={(event) => setGuardrails(event.target.checked)} />
          </label>
          <label className="toggle-row">
            <span><strong>Выходная проверка</strong><small>Grounding, citations, PII leakage, forbidden claims</small></span>
            <input type="checkbox" defaultChecked />
          </label>
          <label className="toggle-row">
            <span><strong>Логирование содержимого</strong><small>Полные prompts / completions запрещены в обычных логах</small></span>
            <input type="checkbox" defaultChecked={false} disabled />
          </label>
          <div className="policy-detail">
            <strong>Параметры</strong>
            <div><span>Policy version</span><code>guardrails-v1</code></div>
            <div><span>Allowed tools</span><code>read-only RAG</code></div>
            <div><span>PII outbound</span><code>masked / minimized</code></div>
          </div>
        </AdminPanel>
      </div>

      <AdminPanel title="Таймауты и лимиты" eyebrow="Ограничения">
        <div className="form-grid-two">
          <label><span>LLM connect timeout</span><input defaultValue="800 мс" /></label>
          <label><span>Max answer tokens</span><input defaultValue="300" /></label>
          <label><span>Context chunks</span><input defaultValue="6" /></label>
          <label><span>Rerank candidates</span><input defaultValue="20" /></label>
        </div>
      </AdminPanel>

      <AdminPanel title="Версия конфигурации" eyebrow="Версии">
        <div className="config-version-row">
          <div>
            <strong>assistant-config-v1</strong>
            <p>Последнее изменение: демонстрационная версия · изменённые настройки не сохраняются.</p>
          </div>
          <button className="button button--primary" onClick={() => setNotice(true)}><Save size={15} /> Проверить изменения</button>
        </div>
        {notice && <div className="inline-success inline-success--block"><ShieldCheck size={17} /><span>Локальная проверка: параметры отображаются корректно. Серверное сохранение не выполнялось.</span></div>}
        <p className="admin-footnote"><Eye size={13} /> Скрытые системные промпты и секреты не отображаются в UI.</p>
      </AdminPanel>
    </div>
  );
}
