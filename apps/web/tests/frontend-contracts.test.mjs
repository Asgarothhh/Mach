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
  assert.match(envExample, /VITE_BACKEND_ADMIN_SESSIONS=true/);
  assert.match(bridge, /method: 'POST'/);
  assert.match(bridge, /\/sessions\/\$\{encodeURIComponent\(sessionId\)\}\/turns\/text/);
  assert.match(bridge, /body: \{ text: input.text \}/);
  assert.match(bridge, /payload\.sources/);
  assert.doesNotMatch(bridge, /new WebSocket/);
  assert.match(chatService, /return sendBackendTextTest\(input\)/);
});

test('compose and Dockerfile enable backend admin sessions on the demo stand', async () => {
  const dockerfile = await read('Dockerfile');
  const compose = await readFile(resolve(root, '../../docker-compose.yml'), 'utf8');
  assert.match(dockerfile, /ARG VITE_BACKEND_ADMIN_SESSIONS=true/);
  assert.match(compose, /VITE_BACKEND_ADMIN_SESSIONS:\s*"true"/);
  assert.match(compose, /VOICE_ASR_MODE:\s*live/);
  assert.match(compose, /VOICE_TTS_MODE:\s*real/);
  assert.doesNotMatch(compose, /VOICE_ASR_MODE:\s*mock/);
  assert.match(compose, /QDRANT_URL:\s*http:\/\/qdrant:6333/);
  assert.doesNotMatch(compose, /QDRANT_URL:\s*\$\{QDRANT_URL/);
});

test('clearing the text dialog ends the cached backend session', async () => {
  const bridge = await read('src/features/chat/services/backendTextTest.service.ts');
  const textPage = await read('src/features/voice/pages/TextModePage.tsx');
  const voiceCtx = await read('src/features/voice/model/VoiceExperienceContext.tsx');
  const tenantCtx = await read('src/features/tenant/model/TenantContext.tsx');
  assert.match(bridge, /export async function resetBackendTextSession/);
  assert.match(bridge, /\/sessions\/\$\{encodeURIComponent\(sessionId\)\}\/end/);
  assert.match(textPage, /await resetBackendTextSession\(\)/);
  assert.match(voiceCtx, /void resetBackendTextSession\(\)/);
  assert.match(tenantCtx, /void resetBackendTextSession\(\)/);
});

test('footer support link uses tenant supportUrl and keeps MTS documents', async () => {
  const footer = await read('src/shared/components/AppFooter.tsx');
  assert.match(footer, /useTenant\(\)/);
  assert.match(footer, /supportUrl/);
  assert.match(footer, /www\.mts\.by\/company\/comp\/doc/);
  assert.doesNotMatch(footer, /href="https:\/\/help\.mts\.by\/"/);
});

test('track1 header wraps by 1456px so 1281–1456 cannot overflow', async () => {
  const css = await read('src/styles/global.css');
  const wrapBlock = css.match(/@media \(max-width: 1456px\) \{[\s\S]*?\n\}/);
  assert.ok(wrapBlock, 'missing 1456px header breakpoint');
  assert.match(wrapBlock[0], /public-header--track1 \.public-header__inner \{[^}]*flex-wrap: wrap/);
  assert.match(wrapBlock[0], /height: auto/);
});

test('voice transcripts keep AnswerEvent citations across TTS partials', async () => {
  const conversation = await read('src/features/voice/model/useConversation.ts');
  const voiceWs = await read('src/features/voice/services/voiceWs.service.ts');
  const types = await read('src/shared/types/voice.ts');
  assert.match(types, /citations\?: SourceCitation\[\]/);
  assert.match(voiceWs, /mapAnswerEventCitations/);
  assert.match(conversation, /event\.citations\?\.length \? event\.citations : existing\?\.citations/);
});

test('voice WS mock client drops stale generations', async () => {
  const voiceWs = await read('src/features/voice/services/voiceWs.service.ts');
  assert.match(voiceWs, /shouldDropTtsChunk/);
  assert.match(voiceWs, /cancelledGenerations/);
  assert.match(voiceWs, /\/ws\/sessions\//);
  assert.match(voiceWs, /is_last_chunk/);
  assert.match(voiceWs, /activeSources/);
});
