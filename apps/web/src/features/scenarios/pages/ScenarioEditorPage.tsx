import { useCallback, useEffect, useState } from 'react';
import { ArrowDownRight, CheckCircle2, GitBranch, Plus, RotateCcw, Save, ShieldCheck, SlidersHorizontal, Sparkles, Volume2, History, GitCompare, AlertTriangle } from 'lucide-react';
import { SectionHeading } from '../../../shared/components/SectionHeading';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { env } from '../../../shared/config/env';
import { useTenant } from '../../tenant/model/TenantContext';
import type { ChannelChoice, ScenarioDraftInput, ScenarioProfile, ScenarioRule, ScenarioVersionRecord } from '../../../shared/types/track1';
import { listScenarios, listScenarioVersions, publishScenario, rollbackScenario, saveScenarioDraft, validateScenarioDraft } from '../services/scenarios.service';

const decisionOptions: { value: ChannelChoice; label: string }[] = [
  { value: 'voice', label: 'Ответ голосом' },
  { value: 'chat_offer', label: 'Предложить чат' },
  { value: 'human_handoff', label: 'Перевод человеку' },
  { value: 'fallback', label: 'Безопасный fallback' },
];

const emptyDraft: ScenarioDraftInput = {
  name: 'Новый сценарий', description: '', intent: 'general_question', instructions: 'Отвечай кратко и профессионально. Используй только подтверждённые источники текущего tenant. Если доказательств недостаточно — уточни, предложи чат или передачу сотруднику.', greeting: 'Здравствуйте! Чем могу помочь?', fallback_text: 'Не могу надёжно подтвердить этот ответ. Предложить чат или соединить с сотрудником?', rules: [],
};

function makeRule(): ScenarioRule {
  return { rule_id: `rule-${Date.now().toString(36)}`, label: 'Новое правило', match_description: 'Условие срабатывания правила', decision: 'chat_offer', enabled: true, priority: 10 };
}

export function ScenarioEditorPage() {
  const { tenantId, tenantName } = useTenant();
  const [scenarios, setScenarios] = useState<ScenarioProfile[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [draft, setDraft] = useState<ScenarioDraftInput>(emptyDraft);
  const [currentRevision, setCurrentRevision] = useState('');
  const [currentStatus, setCurrentStatus] = useState<'draft' | 'published' | 'archived'>('draft');
  const [isNew, setIsNew] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [versions, setVersions] = useState<ScenarioVersionRecord[]>([]);
  const [compareRevision, setCompareRevision] = useState('');
  const [validationMessages, setValidationMessages] = useState<string[]>([]);
  const [validationWarnings, setValidationWarnings] = useState<string[]>([]);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const list = await listScenarios(tenantId);
      setScenarios(list);
      if (list.length > 0) {
        const chosen = list.find((item) => item.scenario_id === selectedId) ?? list[0];
        selectScenario(chosen);
      } else {
        setSelectedId(''); setDraft(emptyDraft); setCurrentRevision(''); setCurrentStatus('draft'); setIsNew(false);
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось загрузить сценарии.'); }
    finally { setLoading(false); }
  // selectedId is intentionally omitted; loading only follows tenant changes and explicit refresh.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId]);

  useEffect(() => { void load(); }, [load]);

  async function refreshVersions(scenarioId: string) {
    try {
      const items = await listScenarioVersions(tenantId, scenarioId);
      setVersions(items);
      setCompareRevision(items.find((item) => item.revision_id !== currentRevision)?.revision_id ?? items[0]?.revision_id ?? '');
    } catch {
      setVersions([]);
      setCompareRevision('');
    }
  }

  function selectScenario(scenario: ScenarioProfile) {
    setSelectedId(scenario.scenario_id);
    setCurrentRevision(scenario.revision_id);
    setCurrentStatus(scenario.status);
    setDraft({ name: scenario.name, description: scenario.description, intent: scenario.intent, instructions: scenario.instructions, greeting: scenario.greeting, fallback_text: scenario.fallback_text, rules: scenario.rules.map((rule) => ({ ...rule })) });
    setIsNew(false); setMessage(null); setError(null); setValidationMessages([]); setValidationWarnings([]);
    void refreshVersions(scenario.scenario_id);
  }

  function update<K extends keyof ScenarioDraftInput>(key: K, value: ScenarioDraftInput[K]) {
    setValidationMessages([]); setValidationWarnings([]);
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function updateRule(ruleId: string, patch: Partial<ScenarioRule>) {
    setValidationMessages([]); setValidationWarnings([]);
    setDraft((current) => ({ ...current, rules: current.rules.map((rule) => rule.rule_id === ruleId ? { ...rule, ...patch } : rule) }));
  }

  async function validateDraft(): Promise<boolean> {
    setSaving(true); setError(null); setMessage(null);
    try {
      const result = await validateScenarioDraft(tenantId, draft);
      setValidationMessages(result.errors);
      setValidationWarnings(result.warnings);
      if (!result.valid) return false;
      setMessage('Предварительная проверка пройдена. Публикация всё равно должна быть повторно проверена backend.');
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось проверить сценарий.');
      return false;
    } finally { setSaving(false); }
  }

  async function saveDraft() {
    if (!draft.name.trim() || !draft.instructions.trim()) { setError('Название и инструкции сценария обязательны.'); return; }
    setSaving(true); setError(null); setMessage(null);
    try {
      const saved = await saveScenarioDraft(tenantId, draft, selectedId || undefined);
      setScenarios((current) => [saved, ...current.filter((item) => item.scenario_id !== saved.scenario_id)]);
      selectScenario(saved);
      setMessage(env.demoMode ? 'Черновик сохранён в демо-памяти. Backend/production запись не выполнялась.' : 'Черновик отправлен в backend. Проверьте его версию и права доступа.');
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось сохранить черновик.'); }
    finally { setSaving(false); }
  }

  async function publish() {
    const valid = await validateDraft();
    if (!valid) return;
    if (!selectedId || isNew || !currentRevision) { setError('Сначала сохраните сценарий как черновик.'); return; }
    setSaving(true); setError(null); setMessage(null);
    try {
      const scenario = scenarios.find((item) => item.scenario_id === selectedId);
      if (!scenario) throw new Error('Сценарий не найден. Сохраните черновик повторно.');
      await publishScenario(tenantId, scenario);
      setCurrentStatus('published');
      setScenarios((current) => current.map((item) => item.scenario_id === selectedId ? { ...item, status: 'published', revision_id: `${item.revision_id}-published`, updated_at: new Date().toISOString() } : item));
      setMessage(env.demoMode ? 'Публикация демонстрационная; реальный routing policy не менялся.' : 'Запрос публикации принят. Проверьте ответ backend и audit log.');
      await refreshVersions(selectedId);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось опубликовать сценарий.'); }
    finally { setSaving(false); }
  }

  async function rollbackToRevision(revisionId: string) {
    if (!selectedId || !window.confirm(`Восстановить ревизию ${revisionId}? Действие должно быть зааудировано backend.`)) return;
    setSaving(true); setError(null); setMessage(null);
    try {
      const restored = await rollbackScenario(tenantId, selectedId, revisionId);
      setScenarios((current) => [restored, ...current.filter((item) => item.scenario_id !== restored.scenario_id)]);
      selectScenario(restored);
      setMessage(env.demoMode ? 'Демо rollback выполнен. Production-сценарий не менялся.' : 'Запрос rollback выполнен backend. Проверьте audit event и active revision.');
      await refreshVersions(restored.scenario_id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось восстановить ревизию.'); }
    finally { setSaving(false); }
  }

  function newScenario() {
    setSelectedId(''); setDraft({ ...emptyDraft, rules: [makeRule()] }); setCurrentRevision(''); setCurrentStatus('draft'); setIsNew(true); setVersions([]); setCompareRevision(''); setValidationMessages([]); setValidationWarnings([]); setMessage(null); setError(null);
  }

  const compareVersion = versions.find((item) => item.revision_id === compareRevision);
  const compareRows = compareVersion ? [
    { label: 'Название', before: compareVersion.snapshot.name, after: draft.name },
    { label: 'Intent', before: compareVersion.snapshot.intent, after: draft.intent },
    { label: 'Приветствие', before: compareVersion.snapshot.greeting, after: draft.greeting },
    { label: 'Инструкции', before: compareVersion.snapshot.instructions, after: draft.instructions },
    { label: 'Fallback', before: compareVersion.snapshot.fallback_text, after: draft.fallback_text },
    { label: 'Правила маршрутизации', before: JSON.stringify(compareVersion.snapshot.rules), after: JSON.stringify(draft.rules) },
  ].filter((item) => item.before !== item.after) : [];

  return (
    <div className="track-page">
      <SectionHeading eyebrow="SCENARIO & ROUTING EDITOR" title="Сценарии и маршрутизация" description={`Настройте поведение агента для ${tenantName}. Изменения должны версионироваться, проходить проверку и публиковаться с аудитом.`} action={<button className="button button--primary button--small" onClick={newScenario}><Plus size={15} /> Новый сценарий</button>} />
      {env.demoMode && <div className="track-demo-banner"><span className="track-demo-dot" /><div><strong>Демо-режим редактора</strong><p>Черновики хранятся в памяти вкладки/сборки. Для реального применения нужны API, RBAC, server-side validation, version diff и audit events.</p></div><StatusBadge tone="demo">DEMO</StatusBadge></div>}
      {error && <div className="track-form-error" role="alert">{error}</div>}
      {message && <div className="track-inline-message is-success" role="status">{message}</div>}
      {validationMessages.length > 0 && <div className="track-form-error" role="alert"><strong>Сценарий не прошёл проверку</strong><ul>{validationMessages.map((item) => <li key={item}>{item}</li>)}</ul></div>}
      {validationWarnings.length > 0 && <div className="track-notice-list">{validationWarnings.map((item) => <p key={item}>{item}</p>)}</div>}
      <div className="track-scenario-workspace">
        <aside className="track-panel track-scenario-list"><div className="track-panel__heading"><div><span className="track-eyebrow">TENANT SCENARIOS</span><h2>Список сценариев</h2></div><span className="track-result-count">{scenarios.length}</span></div>
          {loading ? <div className="track-empty-state"><span className="loading-dot" />Загружаем…</div> : scenarios.length === 0 ? <div className="track-empty-state"><SlidersHorizontal size={23} /><strong>Пока нет сценариев</strong><span>Создайте базовый сценарий для вашего tenant.</span><button className="button button--primary button--small" onClick={newScenario}><Plus size={14} /> Создать сценарий</button></div> : scenarios.map((scenario) => <button type="button" className={`track-scenario-option ${selectedId === scenario.scenario_id ? 'is-selected' : ''}`} key={scenario.scenario_id} onClick={() => selectScenario(scenario)}><span className="track-scenario-option__top"><strong>{scenario.name}</strong><StatusBadge tone={scenario.status === 'published' ? 'success' : 'warning'}>{scenario.status === 'published' ? 'Опубликован' : scenario.status === 'draft' ? 'Черновик' : 'Архив'}</StatusBadge></span><small>{scenario.intent}</small><span className="track-scenario-option__meta"><GitBranch size={13} /> {scenario.revision_id}</span></button>)}
          <div className="track-list-footnote"><ShieldCheck size={14} /> Данные сценариев фильтруются по текущему tenant на backend. Demo store разделён по tenant ID.</div>
        </aside>

        <section className="track-panel track-scenario-editor"><div className="track-panel__heading"><div><span className="track-eyebrow">{isNew ? 'NEW DRAFT' : currentRevision || 'SCENARIO CONFIG'}</span><h2>{draft.name || 'Новый сценарий'}</h2></div><StatusBadge tone={currentStatus === 'published' ? 'success' : 'warning'}>{currentStatus === 'published' ? 'Опубликованная ревизия' : 'Черновик'}</StatusBadge></div>
          <div className="track-info-panel"><Sparkles size={19} /><div><strong>Управляемый сценарий, не свободный агент</strong><p>Модель не определяет права доступа и не вызывает произвольные инструменты. Маршрут выбирается контролируемыми правилами.</p></div></div>
          <div className="track-form-stack">
            <div className="track-field-row"><label className="track-field"><span>Название</span><input value={draft.name} onChange={(event) => update('name', event.target.value)} maxLength={120} /></label><label className="track-field"><span>Intent / классификация</span><input value={draft.intent} onChange={(event) => update('intent', event.target.value)} maxLength={80} /></label></div>
            <label className="track-field"><span>Описание</span><input value={draft.description} onChange={(event) => update('description', event.target.value)} maxLength={240} placeholder="Когда этот сценарий используется" /></label>
            <label className="track-field"><span>Приветствие</span><textarea rows={3} value={draft.greeting} onChange={(event) => update('greeting', event.target.value)} maxLength={700} /></label>
            <label className="track-field"><span>Инструкции сценария</span><textarea rows={6} value={draft.instructions} onChange={(event) => update('instructions', event.target.value)} maxLength={5000} /><small>Не добавляйте в сценарий секреты, ключи или инструкции по выполнению действий, которых нет в интеграциях.</small></label>
            <label className="track-field"><span>Fallback при нехватке доказательств</span><textarea rows={3} value={draft.fallback_text} onChange={(event) => update('fallback_text', event.target.value)} maxLength={900} /></label>
          </div>

          <div className="track-rule-editor"><div className="track-panel__heading"><div><span className="track-eyebrow">DETERMINISTIC ROUTER</span><h2>Правила маршрутизации</h2></div><button className="button button--secondary button--small" onClick={() => update('rules', [...draft.rules, makeRule()])}><Plus size={14} /> Добавить правило</button></div>
            <p className="track-helper-text">Правила идут по приоритету. Для chat handoff нужно отдельное согласие звонящего; результат считается успешным только после подтверждения adapter.</p>
            {draft.rules.length === 0 && <div className="track-empty-inline">Добавьте первое правило. Пока правил нет, сценарий не определяет маршрут.</div>}
            {draft.rules.map((rule, index) => <div className={`track-rule-card ${!rule.enabled ? 'is-disabled' : ''}`} key={rule.rule_id}><div className="track-rule-card__index">{index + 1}</div><div className="track-rule-card__body"><div className="track-field-row"><label className="track-field"><span>Название правила</span><input value={rule.label} onChange={(event) => updateRule(rule.rule_id, { label: event.target.value })} /></label><label className="track-field"><span>Решение</span><select value={rule.decision} onChange={(event) => updateRule(rule.rule_id, { decision: event.target.value as ChannelChoice })}>{decisionOptions.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}</select></label></div><label className="track-field"><span>Условие срабатывания</span><textarea rows={2} value={rule.match_description} onChange={(event) => updateRule(rule.rule_id, { match_description: event.target.value })} /></label><div className="track-rule-card__footer"><label className="track-check track-check--compact"><input type="checkbox" checked={rule.enabled} onChange={(event) => updateRule(rule.rule_id, { enabled: event.target.checked })} /><span><strong>Правило включено</strong></span></label><label className="track-priority"><span>Приоритет</span><input type="number" value={rule.priority} onChange={(event) => updateRule(rule.rule_id, { priority: Number(event.target.value) })} /></label></div></div></div>)}
          </div>

          <div className="track-version-box"><div><span className="track-eyebrow">CHANGE CONTROL</span><strong>{currentRevision || 'Новая ревизия при сохранении'}</strong><p>Публикация не должна незаметно перезаписывать предыдущую версию. Backend должен валидировать правила и записать audit event.</p></div><div className="track-version-actions"><button className="button button--secondary" onClick={() => { const scenario = scenarios.find((item) => item.scenario_id === selectedId); if (scenario) selectScenario(scenario); else { setDraft(emptyDraft); setIsNew(false); } }}><RotateCcw size={15} /> Сбросить</button><button className="button button--secondary" onClick={() => void validateDraft()} disabled={saving}><CheckCircle2 size={15} /> Проверить</button><button className="button button--secondary" onClick={saveDraft} disabled={saving}><Save size={15} /> {saving ? 'Сохранение…' : 'Сохранить черновик'}</button><button className="button button--primary" onClick={() => void publish()} disabled={saving || isNew || !selectedId}><CheckCircle2 size={15} /> Опубликовать</button></div></div>
          <section className="track-version-history">
            <div className="track-panel__heading"><div><span className="track-eyebrow">VERSION HISTORY</span><h2><History size={17} /> История версий и сравнение</h2></div><span className="track-result-count">{versions.length} ревизий</span></div>
            {versions.length <= 1 ? <div className="track-empty-inline">История появится после сохранения новых ревизий. В production список должен включать автора, timestamp и audit reference.</div> : <>
              <div className="track-version-compare-toolbar"><label className="track-field"><span>Сравнить текущий черновик с версией</span><select value={compareRevision} onChange={(event) => setCompareRevision(event.target.value)}>{versions.filter((item) => item.revision_id !== currentRevision).map((item) => <option value={item.revision_id} key={item.revision_id}>{item.revision_id} · {item.status} · {new Date(item.updated_at).toLocaleString('ru-RU')}</option>)}</select></label><button className="button button--secondary button--small" disabled={!compareVersion || compareVersion.revision_id === currentRevision || saving} onClick={() => void rollbackToRevision(compareRevision)}><RotateCcw size={14} /> Восстановить версию</button></div>
              {compareVersion && <div className="track-version-diff"><div className="track-version-diff__header"><GitCompare size={16} /><strong>{compareVersion.revision_id} → текущая конфигурация</strong><span>{compareRows.length} отличий</span></div>{compareRows.length === 0 ? <p className="track-empty-inline">Различий между выбранной версией и текущей конфигурацией не найдено.</p> : compareRows.map((row) => <div className="track-version-diff__row" key={row.label}><strong>{row.label}</strong><div><span>Выбранная ревизия</span><p>{row.before}</p></div><div><span>Текущая конфигурация</span><p>{row.after}</p></div></div>)}</div>}
            </>}
            <p className="track-helper-text"><AlertTriangle size={14} /> В демо версионирование хранится в памяти. В live-режиме publish и rollback должны проходить server-side RBAC и создавать audit events.</p>
          </section>
          <p className="track-page-footnote"><Volume2 size={14} /> Chat route · {draft.rules.filter((rule) => rule.enabled && rule.decision === 'chat_offer').length} активных правил · Human handoff · {draft.rules.filter((rule) => rule.enabled && rule.decision === 'human_handoff').length} активных правил <ArrowDownRight size={14} /></p>
        </section>
      </div>
      {!env.demoMode && <p className="track-page-footnote">Доступ к редактированию/публикации должен проверяться сервером по tenant RBAC. UI не является механизмом авторизации.</p>}
    </div>
  );
}
