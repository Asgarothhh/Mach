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

test('optional backend text-test bridge uses current REST text-turn contract', async () => {
  const envExample = await read('.env.example');
  const bridge = await read('src/features/chat/services/backendTextTest.service.ts');
  const chatService = await read('src/features/chat/services/chat.service.ts');
  assert.match(envExample, /VITE_BACKEND_TEXT_TEST=false/);
  assert.match(bridge, /method: 'POST'/);
  assert.match(bridge, /\/sessions\/\$\{encodeURIComponent\(sessionId\)\}\/turns\/text/);
  assert.match(bridge, /body: \{ text: input.text \}/);
  assert.doesNotMatch(bridge, /new WebSocket/);
  assert.match(chatService, /return sendBackendTextTest\(input\)/);
});
