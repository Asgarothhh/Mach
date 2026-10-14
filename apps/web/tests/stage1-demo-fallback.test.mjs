import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const read = (path) => readFile(resolve(root, path), 'utf8');

// The Stage-1 backend has no control-plane routes (`/tenants`, `/tenants/*/scenarios`,
// `/tenants/*/test-calls`): docs/runbook.md §7 keeps those screens in demo/disabled.
// The hosted build runs with VITE_DEMO_MODE=false, so the screens must degrade to the
// local demo fixtures instead of showing a raw API error, and should not fire failing
// requests while the routes are missing.

test('control-plane capability is probed from the OpenAPI schema and cached', async () => {
  const helper = await read('src/shared/api/stage1Fallback.ts');
  assert.match(helper, /openapi\.json/);
  assert.match(helper, /controlPlaneProbe \?\?= fetch/);
  assert.ok(helper.includes("'/api/v1/tenants' in schema.paths"));
  // A failed probe must not hide the API: the real call is still attempted.
  assert.match(helper, /\.catch\(\(\) => true\)/);
});

test('only a missing route (404) triggers the demo fallback', async () => {
  const helper = await read('src/shared/api/stage1Fallback.ts');
  assert.match(helper, /error instanceof ApiError/);
  assert.match(helper, /error\.status === 404/);
  assert.doesNotMatch(helper, /error\.status === 405/);
});

test('onboarding screen falls back to demo fixtures on a missing route', async () => {
  const source = await read('src/features/onboarding/services/onboarding.service.ts');
  assert.match(source, /withDemoFallback\(/);
  // Explicit demo mode still short-circuits before any API call.
  assert.match(source, /if \(env\.demoMode\) return createDemoTenant\(input\)/);
  assert.match(source, /if \(env\.demoMode\) return listDemoTenants\(\)/);
  // The fallback reuses the same fixture implementation as demo mode.
  assert.match(source, /\(\) => createDemoTenant\(input\)/);
  assert.match(source, /\(\) => validateDemoOnboarding\(displayName, greeting, elapsedMs\)/);
});

test('scenarios screen falls back to demo fixtures on a missing route', async () => {
  const source = await read('src/features/scenarios/services/scenarios.service.ts');
  assert.match(source, /withDemoFallback\(/);
  assert.match(source, /if \(env\.demoMode\) return listDemoScenarios\(tenantId\)/);
  assert.match(source, /\(\) => saveDemoScenarioDraft\(tenantId, input, scenarioId\)/);
  assert.match(source, /\(\) => publishDemoScenario\(scenario\)/);
  assert.match(source, /\(\) => rollbackDemoScenario\(tenantId, scenarioId, revisionId\)/);
});
