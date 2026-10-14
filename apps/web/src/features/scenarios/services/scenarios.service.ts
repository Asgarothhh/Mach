import { apiRequest } from '../../../shared/api/http';
import { withDemoFallback } from '../../../shared/api/stage1Fallback';
import { env } from '../../../shared/config/env';
import type { ScenarioDraftInput, ScenarioProfile, ScenarioVersionRecord } from '../../../shared/types/track1';
import { demoScenarioStore } from '../data/demoScenarios';

const cloneScenario = (scenario: ScenarioProfile): ScenarioProfile => ({ ...scenario, rules: scenario.rules.map((rule) => ({ ...rule })) });
const demoScenarioHistory: ScenarioVersionRecord[] = demoScenarioStore.map((scenario) => ({ scenario_id: scenario.scenario_id, revision_id: scenario.revision_id, status: scenario.status, updated_at: scenario.updated_at, change_summary: 'Начальная демонстрационная ревизия', snapshot: cloneScenario(scenario) }));

function validDemoDraft(): ScenarioValidationResult {
  return { valid: true, errors: [], warnings: ['Проверка выполнена локально на синтетической конфигурации. Backend не запускал server-side validation.'] };
}

function listDemoScenarios(tenantId: string): ScenarioProfile[] {
  return demoScenarioStore.filter((scenario) => scenario.tenant_id === tenantId);
}

function listDemoScenarioVersions(tenantId: string, scenarioId: string): ScenarioVersionRecord[] {
  const current = demoScenarioStore.find((scenario) => scenario.tenant_id === tenantId && scenario.scenario_id === scenarioId);
  const history = demoScenarioHistory.filter((item) => item.scenario_id === scenarioId && item.snapshot.tenant_id === tenantId);
  const currentRecord = current ? [{ scenario_id: current.scenario_id, revision_id: current.revision_id, status: current.status, updated_at: current.updated_at, change_summary: 'Текущая ревизия', snapshot: cloneScenario(current) }] : [];
  return [...currentRecord, ...history].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

function saveDemoScenarioDraft(tenantId: string, input: ScenarioDraftInput, scenarioId?: string): ScenarioProfile {
  const existing = demoScenarioStore.find((scenario) => scenario.tenant_id === tenantId && (scenario.scenario_id === scenarioId || (!scenarioId && scenario.name === input.name)));
  if (existing) demoScenarioHistory.unshift({ scenario_id: existing.scenario_id, revision_id: existing.revision_id, status: existing.status, updated_at: existing.updated_at, change_summary: 'Предыдущая версия до сохранения черновика', snapshot: cloneScenario(existing) });
  const saved: ScenarioProfile = {
    ...input,
    scenario_id: existing?.scenario_id ?? `scenario-${Date.now().toString(36)}`,
    tenant_id: tenantId,
    revision_id: `draft-r${Date.now()}`,
    status: 'draft',
    updated_at: new Date().toISOString(),
  };
  if (existing) Object.assign(existing, saved);
  else demoScenarioStore.unshift(saved);
  return saved;
}

function publishDemoScenario(scenario: ScenarioProfile): void {
  const current = demoScenarioStore.find((item) => item.scenario_id === scenario.scenario_id);
  if (current) {
    demoScenarioHistory.unshift({ scenario_id: current.scenario_id, revision_id: current.revision_id, status: current.status, updated_at: current.updated_at, change_summary: 'Версия до публикации', snapshot: cloneScenario(current) });
    current.status = 'published';
    current.updated_at = new Date().toISOString();
    current.revision_id = `${current.revision_id}-published`;
  }
}

function rollbackDemoScenario(tenantId: string, scenarioId: string, revisionId: string): ScenarioProfile {
  const target = demoScenarioHistory.find((item) => item.scenario_id === scenarioId && item.snapshot.tenant_id === tenantId && item.revision_id === revisionId);
  const current = demoScenarioStore.find((item) => item.tenant_id === tenantId && item.scenario_id === scenarioId);
  if (!target || !current) throw new Error('Выбранная ревизия больше недоступна. Обновите список версий.');
  demoScenarioHistory.unshift({ scenario_id: current.scenario_id, revision_id: current.revision_id, status: current.status, updated_at: current.updated_at, change_summary: 'Ревизия перед rollback', snapshot: cloneScenario(current) });
  const restored: ScenarioProfile = { ...cloneScenario(target.snapshot), revision_id: `rollback-${target.revision_id}-${Date.now().toString(36)}`, status: 'published', updated_at: new Date().toISOString() };
  Object.assign(current, restored);
  demoScenarioHistory.unshift({ scenario_id: restored.scenario_id, revision_id: restored.revision_id, status: restored.status, updated_at: restored.updated_at, change_summary: `Восстановлена ревизия ${target.revision_id}`, snapshot: cloneScenario(restored) });
  return cloneScenario(restored);
}

export interface ScenarioValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export async function validateScenarioDraft(tenantId: string, input: ScenarioDraftInput): Promise<ScenarioValidationResult> {
  if (!input.name.trim()) return { valid: false, errors: ['Укажите название сценария.'], warnings: [] };
  if (!input.intent.trim()) return { valid: false, errors: ['Укажите intent для классификации обращения.'], warnings: [] };
  if (input.greeting.trim().length < 8) return { valid: false, errors: ['Приветствие слишком короткое.'], warnings: [] };
  if (!input.instructions.trim()) return { valid: false, errors: ['Заполните инструкции сценария.'], warnings: [] };
  if (!input.rules.some((rule) => rule.enabled)) return { valid: false, errors: ['Включите хотя бы одно правило маршрутизации.'], warnings: [] };
  if (input.rules.some((rule) => !rule.label.trim() || !rule.match_description.trim())) return { valid: false, errors: ['У каждого правила должны быть название и условие.'], warnings: [] };
  if (env.demoMode) return validDemoDraft();
  // Proposed validation path; align with backend OpenAPI before leaving demo mode.
  return withDemoFallback(
    () => apiRequest<ScenarioValidationResult>(`/tenants/${encodeURIComponent(tenantId)}/scenarios/validate`, { method: 'POST', body: input }),
    () => validDemoDraft(),
  );
}

export async function listScenarios(tenantId: string): Promise<ScenarioProfile[]> {
  if (env.demoMode) return listDemoScenarios(tenantId);
  // GET collection path is inferred for the editor and must be confirmed against backend OpenAPI.
  return withDemoFallback(
    () => apiRequest<ScenarioProfile[]>(`/tenants/${encodeURIComponent(tenantId)}/scenarios`),
    () => listDemoScenarios(tenantId),
  );
}

export async function listScenarioVersions(tenantId: string, scenarioId: string): Promise<ScenarioVersionRecord[]> {
  if (env.demoMode) return listDemoScenarioVersions(tenantId, scenarioId);
  // Version history endpoint is implied by the Track 1 version/diff requirement; confirm its schema in OpenAPI.
  return withDemoFallback(
    () => apiRequest<ScenarioVersionRecord[]>(`/tenants/${encodeURIComponent(tenantId)}/scenarios/${encodeURIComponent(scenarioId)}/versions`),
    () => listDemoScenarioVersions(tenantId, scenarioId),
  );
}

export async function saveScenarioDraft(tenantId: string, input: ScenarioDraftInput, scenarioId?: string): Promise<ScenarioProfile> {
  if (env.demoMode) return saveDemoScenarioDraft(tenantId, input, scenarioId);
  return withDemoFallback(
    () => apiRequest<ScenarioProfile>(`/tenants/${encodeURIComponent(tenantId)}/scenarios`, { method: 'POST', body: { ...input, ...(scenarioId ? { scenario_id: scenarioId } : {}) } }),
    () => saveDemoScenarioDraft(tenantId, input, scenarioId),
  );
}

export async function publishScenario(tenantId: string, scenario: ScenarioProfile): Promise<void> {
  if (env.demoMode) return publishDemoScenario(scenario);
  await withDemoFallback(
    () => apiRequest<unknown>(`/tenants/${encodeURIComponent(tenantId)}/scenarios/${encodeURIComponent(scenario.revision_id)}/publish`, { method: 'POST', body: {} }),
    () => publishDemoScenario(scenario),
  );
}


export async function rollbackScenario(tenantId: string, scenarioId: string, revisionId: string): Promise<ScenarioProfile> {
  if (env.demoMode) return rollbackDemoScenario(tenantId, scenarioId, revisionId);
  // Proposed control-plane route; align with backend OpenAPI before switching out of demo mode.
  return withDemoFallback(
    () => apiRequest<ScenarioProfile>(`/tenants/${encodeURIComponent(tenantId)}/scenarios/${encodeURIComponent(revisionId)}/rollback`, { method: 'POST', body: { scenario_id: scenarioId } }),
    () => rollbackDemoScenario(tenantId, scenarioId, revisionId),
  );
}
