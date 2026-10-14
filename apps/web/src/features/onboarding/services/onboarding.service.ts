import { apiRequest } from '../../../shared/api/http';
import { withDemoFallback } from '../../../shared/api/stage1Fallback';
import { env } from '../../../shared/config/env';
import type { OnboardingValidation, TenantCreateInput, TenantProfile, TestCallResult } from '../../../shared/types/track1';
import { addDemoTestCall } from '../../calls/data/demoCalls';
import { demoScenarioStore } from '../../scenarios/data/demoScenarios';
import { getDemoTenantProfile, listDemoTenants, registerDemoTenant } from '../../tenant/data/demoTenants';

function createDemoTenant(input: TenantCreateInput): TenantProfile {
  const tenantId = `demo-tenant-${Date.now().toString(36)}`;
  const profile: TenantProfile = { ...input, tenant_id: tenantId, status: 'needs_setup', created_at: new Date().toISOString(), settings_revision: 'tenant-config-draft-r1' };
  registerDemoTenant(profile);
  demoScenarioStore.push({
    scenario_id: `scenario-${tenantId}-welcome`, tenant_id: tenantId, revision_id: 'greeting-draft-r1', name: 'Приветствие и первичная классификация', description: 'Базовый маршрут для каждого нового входящего обращения.', intent: 'general_question', instructions: 'Выясни суть обращения одним уточняющим вопросом. Отвечай только на основе утверждённых источников текущего tenant. При недостатке данных предложи чат или передачу человеку.', greeting: input.greeting, fallback_text: 'Не могу надёжно подтвердить ответ. Предложить чат или соединить с сотрудником?', status: 'draft', updated_at: new Date().toISOString(), rules: [
      { rule_id: `${tenantId}-standard`, label: 'Стандартный вопрос', match_description: 'Короткий вопрос по утверждённым услугам и FAQ', decision: 'voice', enabled: true, priority: 1 },
      { rule_id: `${tenantId}-complex`, label: 'Сложное обращение', match_description: 'Длинный или сложный вопрос', decision: input.route_policy === 'human_for_complex' ? 'human_handoff' : input.route_policy === 'chat_for_complex' ? 'chat_offer' : 'voice', enabled: true, priority: 2 },
    ]
  });
  return profile;
}

export async function createTenant(input: TenantCreateInput): Promise<TenantProfile> {
  if (env.demoMode) return createDemoTenant(input);
  // Payload shape is provisional until backend OpenAPI/Pydantic schema is published.
  return withDemoFallback(
    () => apiRequest<TenantProfile>('/tenants', { method: 'POST', body: input }),
    () => createDemoTenant(input),
  );
}

export function getDemoTenant(tenantId: string): TenantProfile | undefined {
  return getDemoTenantProfile(tenantId);
}

function updateDemoTenantProfile(tenantId: string, input: TenantCreateInput): TenantProfile {
  const current = getDemoTenantProfile(tenantId);
  if (!current) throw new Error('Профиль не найден в выбранном demo tenant.');
  const updated: TenantProfile = { ...current, ...input, settings_revision: `tenant-config-${Date.now().toString(36)}` };
  registerDemoTenant(updated);
  const welcome = demoScenarioStore.find((scenario) => scenario.tenant_id === tenantId && scenario.intent === 'general_question');
  if (welcome) { welcome.greeting = input.greeting; welcome.updated_at = new Date().toISOString(); }
  return updated;
}

export async function updateTenantProfile(tenantId: string, input: TenantCreateInput): Promise<TenantProfile> {
  if (env.demoMode) return updateDemoTenantProfile(tenantId, input);
  // Tenant profile update route is inferred for the Track 1 wizard and must be confirmed in backend OpenAPI.
  return withDemoFallback(
    () => apiRequest<TenantProfile>(`/tenants/${encodeURIComponent(tenantId)}`, { method: 'PATCH', body: input }),
    () => updateDemoTenantProfile(tenantId, input),
  );
}

export async function listTenants(): Promise<TenantProfile[]> {
  if (env.demoMode) return listDemoTenants();
  // GET /tenants is implied by the onboarding requirement and must be confirmed against backend OpenAPI.
  return withDemoFallback(
    () => apiRequest<TenantProfile[]>('/tenants'),
    () => listDemoTenants(),
  );
}

function validateDemoOnboarding(displayName: string, greeting: string, elapsedMs: number): OnboardingValidation {
  const blockers: string[] = [];
  if (!displayName.trim()) blockers.push('Укажите название компании.');
  if (greeting.trim().length < 12) blockers.push('Приветствие должно содержать не менее 12 символов.');
  return { ready: blockers.length === 0, blockers, warnings: ['Mock-адаптер не подключает реальную телефонную сеть.'], elapsed_ms: elapsedMs };
}

export async function validateTenantOnboarding(tenantId: string, displayName: string, greeting: string, elapsedMs = 0): Promise<OnboardingValidation> {
  if (env.demoMode) return validateDemoOnboarding(displayName, greeting, elapsedMs);
  return withDemoFallback(
    () => apiRequest<OnboardingValidation>(`/tenants/${encodeURIComponent(tenantId)}/onboarding/validate`, { method: 'POST', body: { display_name: displayName, greeting, client_elapsed_ms: elapsedMs } }),
    () => validateDemoOnboarding(displayName, greeting, elapsedMs),
  );
}

function startDemoTenantTestCall(tenantId: string, adapter: 'mock' | 'sip', displayName: string): TestCallResult {
  if (adapter === 'sip') {
    return { call_id: '', session_id: '', status: 'failed', adapter, is_mock: true, message: 'SIP недоступен в demo mode. Выберите Mock/Test Call или подключите SIP backend.' };
  }
  const call = addDemoTestCall(tenantId, displayName, adapter);
  return { call_id: call.call_id, session_id: call.session_id, status: 'started', adapter, is_mock: true, message: 'Синтетический тестовый вызов создан. Реальная телефония не подключалась.' };
}

export async function startTenantTestCall(tenantId: string, adapter: 'mock' | 'sip', displayName: string): Promise<TestCallResult> {
  if (env.demoMode) return startDemoTenantTestCall(tenantId, adapter, displayName);
  return withDemoFallback(
    () => apiRequest<TestCallResult>(`/tenants/${encodeURIComponent(tenantId)}/test-calls`, { method: 'POST', body: { adapter } }),
    () => startDemoTenantTestCall(tenantId, adapter, displayName),
  );
}
