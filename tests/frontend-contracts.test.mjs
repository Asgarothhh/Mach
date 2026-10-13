import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const read = (path) => readFile(resolve(root, path), 'utf8');

test('demo mode is the safe default and browser env has no provider credentials', async () => {
  const envExample = await read('.env.example');
  const envSource = await read('src/shared/config/env.ts');
  assert.match(envExample, /VITE_DEMO_MODE=true/);
  assert.match(envSource, /readBoolean\(import\.meta\.env\.VITE_DEMO_MODE, true\)/);
  assert.doesNotMatch(envExample, /OPENROUTER_API_KEY|LIVEKIT_API_SECRET|DATABASE_URL|QDRANT_API_KEY/);
});

test('the Track 1 call history and scenario editor remain inside the admin layout', async () => {
  const app = await read('src/app/App.tsx');
  assert.match(app, /path="calls" element=\{<CallHistoryPage \/>\}/);
  assert.match(app, /path="calls\/:callId" element=\{<CallDetailPage \/>\}/);
  assert.match(app, /path="scenarios" element=\{<ScenarioEditorPage \/>\}/);
});

test('original ASR revisions are gated independently from transcript correction', async () => {
  const detail = await read('src/features/calls/pages/CallDetailPage.tsx');
  assert.match(detail, /permissions\?\.can_view_original/);
  assert.match(detail, /permissions\?\.can_correct_transcript/);
  assert.match(detail, /detail\.audio_recorded/);
});

test('live call export is not advertised before an audited endpoint exists', async () => {
  const history = await read('src/features/calls/pages/CallHistoryPage.tsx');
  assert.match(history, /env\.demoMode && <button[^>]*onClick=\{downloadCsv\}/);
});

test('browser microphone routes are clearly labelled as test mode', async () => {
  const layout = await read('src/app/layouts/PublicLayout.tsx');
  assert.match(layout, /Browser test console/);
  assert.match(layout, /SIP\/VoIP/);
});

test('admin call detail uses session-scoped API while transcript correction uses call ID', async () => {
  const calls = await read('src/features/calls/services/calls.service.ts');
  assert.match(calls, /scope === 'admin' \? '\/admin\/sessions' : '\/calls'/);
  assert.match(calls, /\/calls\/\$\{encodeURIComponent\(callId\)\}\/transcript-corrections/);
});

test('optional backend text-test bridge is explicit and uses the current ASR WebSocket contract', async () => {
  const envExample = await read('.env.example');
  const bridge = await read('src/features/chat/services/backendTextTest.service.ts');
  assert.match(envExample, /VITE_BACKEND_TEXT_TEST=false/);
  assert.match(bridge, /type: 'ASREvent'/);
  assert.match(bridge, /\/api\/v1\/ws\/sessions\//);
  assert.match(bridge, /is_last_chunk/);
});

test('backend admin sessions mode is opt-in and can coexist with demo fixtures', async () => {
  const envExample = await read('.env.example');
  const envSource = await read('src/shared/config/env.ts');
  assert.match(envExample, /VITE_BACKEND_ADMIN_SESSIONS=false/);
  assert.match(envSource, /backendAdminSessions: readBoolean\(import\.meta\.env\.VITE_BACKEND_ADMIN_SESSIONS, false\)/);
  assert.match(envSource, /demoMode: readBoolean\(import\.meta\.env\.VITE_DEMO_MODE, true\)/);
});

test('admin session service follows the supplied OpenAPI endpoints and query contract', async () => {
  const service = await read('src/features/admin/services/adminSessions.service.ts');
  assert.match(service, /checkBackendHealth/);
  assert.match(service, /health\/\$\{path\}/);
  assert.match(service, /apiRequest<BackendSessionSummary>\('\/sessions'/);
  assert.match(service, /createBackendSession/);
  assert.match(service, /\/admin\/sessions\?/);
  assert.match(service, /params\.set\('tenant_id'/);
  assert.match(service, /params\.set\('status'/);
  assert.match(service, /params\.set\('limit'/);
  assert.match(service, /params\.set\('offset'/);
  assert.match(service, /\/transcript-corrections/);
  assert.match(service, /\/handoff\/human/);
  assert.match(service, /\/handoff\/chat/);
  assert.match(service, /\/sessions\/\$\{encodeURIComponent\(sessionId\)\}\/end/);
});

test('admin session routes show real session details and expose the API actions', async () => {
  const sessions = await read('src/features/admin/pages/AdminSessionsPage.tsx');
  const detail = await read('src/features/admin/pages/AdminSessionDetailPage.tsx');
  const app = await read('src/app/App.tsx');
  const layout = await read('src/features/admin/components/AdminLayout.tsx');
  const health = await read('src/features/admin/components/BackendHealthIndicator.tsx');
  assert.match(layout, /BackendHealthIndicator/);
  assert.match(health, /checkBackendHealth/);
  assert.match(sessions, /listBackendSessions/);
  assert.match(sessions, /\/admin\/sessions\/\$\{encodeURIComponent\(session\.session_id\)\}/);
  assert.match(detail, /getBackendSession/);
  assert.match(detail, /correctBackendTranscript/);
  assert.match(detail, /handoffBackendSessionToHuman/);
  assert.match(detail, /handoffBackendSessionToChat/);
  assert.match(detail, /endBackendSession/);
  assert.match(app, /path="sessions" element=\{<AdminSessionsPage \/>\}/);
  assert.match(app, /path="sessions\/:sessionId" element=\{<AdminSessionDetailPage \/>\}/);
});

test('live admin overview reports only values available from the sessions API', async () => {
  const overview = await read('src/features/admin/pages/AdminOverviewPage.tsx');
  assert.match(overview, /BackendSessionsOverview/);
  assert.match(overview, /listBackendSessions/);
  assert.match(overview, /последними 100 сессиями/);
  assert.doesNotMatch(overview, /apiRequest<CallAnalytics>\('\/admin\/analytics\/calls'\)/);
});
