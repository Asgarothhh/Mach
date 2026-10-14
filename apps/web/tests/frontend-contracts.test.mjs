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
  assert.doesNotMatch(envSource, /import\.meta\.env\.(OPENROUTER_API_KEY|LIVEKIT_API_SECRET|VITE_OPENROUTER)/);
});

test('live API tenants are acme-it-demo and mts-public-demo', async () => {
  const envExample = await read('.env.example');
  const envSource = await read('src/shared/config/env.ts');
  const tenants = await read('src/features/tenant/data/demoTenants.ts');
  assert.match(envExample, /VITE_BACKEND_TEST_TENANT_ID=acme-it-demo/);
  assert.match(envSource, /'acme-it-demo'/);
  assert.match(tenants, /tenant_id: 'acme-it-demo'/);
  assert.match(tenants, /tenant_id: 'mts-public-demo'/);
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

test('browser microphone routes are labelled as an in-browser channel, not telephony', async () => {
  const layout = await read('src/app/layouts/PublicLayout.tsx');
  const footer = await read('src/shared/components/AppFooter.tsx');
  const envSource = await read('src/shared/config/env.ts');
  assert.match(layout, /Голосовой помощник в браузере/);
  assert.match(layout, /Разговор идёт через браузер\. Это не телефонный звонок\./);
  assert.doesNotMatch(layout, /Browser test console|LiveKit|PCM16|mock-канал/);
  assert.doesNotMatch(footer, /OPENROUTER_API_KEY|LIVEKIT_API_SECRET|frontend bundle|legal\/security/);
  assert.doesNotMatch(envSource, /import\.meta\.env\.(OPENROUTER_API_KEY|LIVEKIT_API_SECRET|VITE_OPENROUTER)/);
});

test('admin call detail and transcript correction use session-scoped admin API', async () => {
  const calls = await read('src/features/calls/services/calls.service.ts');
  assert.match(calls, /\/admin\/sessions/);
  assert.match(calls, /\/admin\/sessions\/\$\{encodeURIComponent\(callId\)\}\/transcript-corrections/);
  assert.doesNotMatch(calls, /\/calls\/\$\{encodeURIComponent\(callId\)\}\/transcript-corrections/);
});

test('optional backend text-test bridge uses current REST text-turn contract', async () => {
  const envExample = await read('.env.example');
  const bridge = await read('src/features/chat/services/backendTextTest.service.ts');
  const chatService = await read('src/features/chat/services/chat.service.ts');
  assert.match(envExample, /VITE_BACKEND_TEXT_TEST=false/);
  assert.match(bridge, /method: 'POST'/);
  assert.match(bridge, /\/sessions\/\$\{encodeURIComponent\(sessionId\)\}\/turns\/text/);
  assert.match(bridge, /body: \{ text: input.text \}/);
  assert.match(bridge, /payload\.sources/);
  assert.doesNotMatch(bridge, /new WebSocket/);
  assert.match(chatService, /return sendBackendTextTest\(input\)/);
});

test('voice WS mock client drops stale generations', async () => {
  const voiceWs = await read('src/features/voice/services/voiceWs.service.ts');
  assert.match(voiceWs, /shouldDropTtsChunk/);
  assert.match(voiceWs, /cancelledGenerations/);
  assert.match(voiceWs, /\/ws\/sessions\//);
  assert.match(voiceWs, /is_last_chunk/);
  assert.match(voiceWs, /activeSources/);
});
