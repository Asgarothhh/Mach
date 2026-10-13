import type { TenantProfile } from '../../../shared/types/track1';

/** Synthetic tenant seed. This fixture never authenticates a user or grants access. */
export const defaultDemoTenant: TenantProfile = {
  tenant_id: 'demo-business-01',
  display_name: 'Демо-компания',
  status: 'active',
  created_at: '2026-10-13T08:30:00+03:00',
  settings_revision: 'tenant-config-r3',
  greeting: 'Здравствуйте! Вы позвонили в компанию. Я голосовой помощник. Чем могу помочь?',
  route_policy: 'chat_for_complex',
  complexity_threshold_seconds: 40,
  chat_provider: 'mock',
  chat_destination_label: 'Демо-чат компании',
  inbound_adapter: 'mock',
  inbound_endpoint_label: 'Mock incoming call',
  human_transfer_label: 'Тестовая очередь сотрудников',
  human_transfer_enabled: true,
  consent_notice: 'Разговор может обрабатываться для подготовки ответа. Если вы не согласны, попросите соединить вас с сотрудником.',
  consent_notice_version: 'notice-r1',
};

const demoTenants = new Map<string, TenantProfile>([[defaultDemoTenant.tenant_id, defaultDemoTenant]]);

export function listDemoTenants(): TenantProfile[] {
  return [...demoTenants.values()].map((tenant) => ({ ...tenant }));
}

export function getDemoTenantProfile(tenantId: string): TenantProfile | undefined {
  const tenant = demoTenants.get(tenantId);
  return tenant ? { ...tenant } : undefined;
}

export function registerDemoTenant(tenant: TenantProfile): void {
  demoTenants.set(tenant.tenant_id, { ...tenant });
}
