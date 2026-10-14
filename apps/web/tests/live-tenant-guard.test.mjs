import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const read = (path) => readFile(resolve(root, path), 'utf8');

// Fixture-only tenants (created in the demo wizard) exist in the browser only:
// the Stage-1 backend has no `POST /tenants` and answers 404 tenant_not_available
// for unknown tenant IDs. Live sessions must always use a backend-known tenant.

test('live session tenant resolver only accepts backend-known tenants', async () => {
  const envSource = await read('src/shared/config/env.ts');
  assert.ok(envSource.includes("export const LIVE_DEMO_TENANTS = ['acme-it-demo', 'mts-public-demo'] as const"));
  assert.match(envSource, /export function resolveSessionTenantId\(/);
  assert.match(envSource, /return isLiveTenant\(candidate\) \? candidate : env\.backendTestTenantId/);
});

test('voice and text sessions resolve the tenant before POST /sessions', async () => {
  const voice = await read('src/features/voice/services/session.service.ts');
  const text = await read('src/features/chat/services/backendTextTest.service.ts');
  assert.match(voice, /tenant_id: resolveSessionTenantId\(tenantId\)/);
  assert.match(text, /const resolvedTenant = resolveSessionTenantId\(tenantId\)/);
  assert.match(text, /tenant_id: resolvedTenant/);
  assert.doesNotMatch(text, /tenant_id: tenantId \|\| env\.backendTestTenantId/);
});

test('fixture-only tenants cannot become active or appear in the live switcher', async () => {
  const context = await read('src/features/tenant/model/TenantContext.tsx');
  assert.match(context, /if \(!env\.demoMode && !isLiveTenant\(nextId\)\) return;/);
  assert.match(context, /if \(!env\.demoMode && !isLiveTenant\(tenant\.tenant_id\)\) return;/);
});
