# MTS Inbound Voice Agent — frontend (Track 1)

Normative documents live at the repository root, not in this tree:

- SSOT: [`docs/SPEC_MTS_VOICE_AGENT_TRACK1.md`](../../docs/SPEC_MTS_VOICE_AGENT_TRACK1.md) (v1.1)
- Spec #2 (ownership/stages): [`docs/MTS_VOICE_AGENT_4_DEVELOPERS.md`](../../docs/MTS_VOICE_AGENT_4_DEVELOPERS.md)

Frontend portal for the Track 1 product: an onboarding portal and control plane for a business client's **inbound voice agent**. It is no longer the public-consumer “ask MTS about roaming” application. The browser microphone/LiveKit experience remains available as a clearly labelled test console; the product call channel is a SIP/VoIP integration or an explicitly labelled mock/test-call adapter.

> **Demo mode is on by default.** The UI uses synthetic call, transcript, scenario and knowledge fixtures. It does not connect to the phone network, run real ASR/TTS/RAG ingestion, call an LLM, or produce real telemetry. Mock test calls must never be presented as proof of SIP/PSTN connectivity.

> **Frontend-only handoff:** this archive contains only the web frontend. It does not include or modify backend source code. Keep demo mode enabled until the backend owner confirms the current API/OpenAPI and WebSocket contracts. `VITE_BACKEND_TEXT_TEST` is an optional experimental adapter and remains disabled by default; it must not be treated as a guarantee that the supplied backend's text pipeline is end-to-end ready. See `docs/FRONTEND_ONLY_HANDOFF.md`.

## Stack

- React 19 + TypeScript (strict) + Vite 8
- React Router 7; separate public/tenant and administrative layouts
- Direct dependency versions are pinned in `package.json`; generate and commit `package-lock.json` after the first successful install for transitive reproducibility.
- `livekit-client` for browser WebRTC test mode only
- `lucide-react` icons and a small CSS-token design system based on the Figma MTS look
- Feature-based folders; shared UI, domain types and service adapters separated

**Prerequisite:** Node.js `22.12+` and npm. Vite 8 and `@vitejs/plugin-react` 6 are paired in `package.json`; Vite 8's current Node requirement is higher than older Vite 6 versions. See the official Vite release information before changing versions: https://vite.dev/releases.

## Run locally (PowerShell)

```powershell
npm install
Copy-Item .env.example .env
npm run dev
```

For the available frontend checks:

```powershell
npm test
npm run typecheck
npm run build
# or run all three sequentially:
npm run check
```

`npm test` runs dependency-free contract smoke tests for demo-safe defaults, route placement, transcript permission gating and browser-test labeling. It is not a substitute for UI component/E2E testing once backend OpenAPI and auth contracts are available.

Vite usually serves `http://localhost:5173`. If npm reports `vite@undefined` or `ERESOLVE`, first verify the configured registry/network and package metadata rather than using `--force`:

```powershell
node -v
npm -v
npm config get registry
npm view vite@8.3.4 version
npm view @vitejs/plugin-react@6.1.2 peerDependencies
```

`.npmrc` selects the official public npm registry. If it is unreachable, fix DNS/proxy/network before retrying. Only generated dependency data may be removed if the install itself was interrupted:

```powershell
Remove-Item -Recurse -Force node_modules -ErrorAction SilentlyContinue
Remove-Item -Force package-lock.json -ErrorAction SilentlyContinue
npm cache clean --force
npm install
```

Do not commit `.env`, API keys, SIP credentials or any server secret. All `VITE_*` values are public browser configuration.

## Product routes

| Route | Screen | Purpose |
|---|---|---|
| `/` | Tenant workspace overview | Entry point for inbound-call operations, setup progress, last calls and control-plane links |
| `/onboarding` | Onboarding wizard | Company profile, greeting/scenario, voice/chat/human routing choice, test channel, notice/consent policy, validation and test call; target ≤5 minutes |
| `/calls` | Call history | Filters by text/status/route/channel; masked caller alias; status, route, consent state, turns and TTFA |
| `/calls/:callId` | Call detail | Transcript timeline, routing audit, source evidence, consent/storage status and transcript correction workflow |
| `/admin/calls` and `/admin/calls/:sessionId` | Administrative call history/detail | Uses admin session APIs while retaining call detail display; preserves admin layout and original-transcript permission flag |
| `/admin/scenarios` | Scenario editor under admin layout | Draft, deterministic routing rules, validation, publish and rollback UI |
| `/scenarios` | Scenario & routing editor | Drafting and publishing scenarios, deterministic rules, route decisions and revisions |
| `/voice/permission` | Browser test console | Requests microphone permission only for test mode |
| `/voice/connecting` | Browser test console | Creates a test session and attempts to connect to LiveKit |
| `/voice/live` | Browser test console | Listening/processing/speaking states, partial/final transcript, playback and barge-in UI |
| `/text` | Text fallback test screen | Preserves a browser test transcript; real text endpoint requires backend contract confirmation |
| `/ended` | Test session ended | Final test transcript / new test conversation |

## Admin routes

| Route | Screen | Purpose |
|---|---|---|
| `/admin` | Overview | Call counts, voice/chat/human routing rates, errors, TTFA p50/p95, latency and top intents |
| `/admin/knowledge` | Tenant sources | Sources/approval/freshness fixture for selected tenant; legacy MTS public corpus is explicitly identified as isolated regression fixture `mts-public-demo` |
| `/admin/sync` | Knowledge sync | Dry-run → diff → smoke tests → promote/rollback UI; mock only until backend adapter is connected |
| `/admin/rag` | RAG inspector | Tenant-labelled query, candidate scores, RRF/rerank and evidence fixture; not a live Qdrant query yet |
| `/admin/quality` | Quality review | ASR, source, routing, handoff and latency annotations |
| `/admin/configuration` | Configuration/privacy | Tenant policy, consent and external-LLM gate; OpenRouter is disabled for real calls by default |
| `/admin/audit` | Audit/security | Synthetic audit/security UI; server-side audit is authoritative |
| `/admin/evaluations` | Evaluation | Synthetic evaluation visualisation |
| `/admin/sessions` | Compatibility route | Redirects to `/admin/calls`; `/admin/sessions/:sessionId` redirects to the admin call list rather than guessing that a session ID equals a call ID. Backend still validates ownership and tenant scope. |

## Structure

```text
src/
  app/
    App.tsx                       # route map + application providers
    layouts/PublicLayout.tsx      # tenant portal, shared header/footer, explicit browser-test banner
  features/
    tenant/model/TenantContext.tsx
    home/pages/HomePage.tsx       # Track 1 workspace dashboard
    onboarding/
      pages/OnboardingPage.tsx
      services/onboarding.service.ts
    calls/
      pages/CallHistoryPage.tsx
      pages/CallDetailPage.tsx
      services/calls.service.ts
      data/demoCalls.ts
    scenarios/
      pages/ScenarioEditorPage.tsx
      services/scenarios.service.ts
      data/demoScenarios.ts
    voice/
      pages/                       # retained browser test console
      model/                       # voice state and conversation context
      services/                    # session API + LiveKit adapter
    chat/services/                 # text-fallback adapter; endpoint remains unconfirmed
    knowledge/data/
      demoSources.ts               # generic, unapproved synthetic tenant fixtures
      legacyMtsDemoSources.ts      # isolated legacy corpus; not loaded in default tenant
    admin/
      components/AdminLayout.tsx
      pages/                       # overview, knowledge, RAG, sync, quality, configuration, audit, eval
      services/admin.service.ts    # calls analytics and legacy-compatible admin adapters
      data/demoData.ts             # legacy latency/event demo helpers only
  shared/
    api/http.ts                    # common HTTP errors and JSON transport
    config/env.ts                  # browser-safe environment values only
    components/                    # Brand, Header/Footer, Waveform, StatusBadge, MessageBubble, SourceCard
    i18n/                          # RU/BE UI preference
    types/                         # API, voice and Track 1 domain/event contracts
  styles/
    tokens.css                     # design tokens
    global.css                     # Figma-inspired shared styles + responsive Track 1 component styles
```

## Architecture rules

1. **Layout**: tenant portal and admin console have separate layouts. Page components compose screens; shared components stay feature-agnostic.
2. **Feature modules**: onboarding, calls, scenarios, voice test mode and admin pages own their view/model/services. Add business behaviour in a feature, not in a giant `App.tsx`.
3. **Services**: HTTP calls live in `src/features/*/services`; pages/hooks should not build endpoint URLs or call `fetch` directly.
4. **Contracts**: API field mapping is typed in `src/shared/types`. When backend publishes OpenAPI/Pydantic schemas, generate/validate these types against it; do not silently invent event payloads.
5. **Tenant isolation**: in demo mode, fixtures filter by the active tenant in UI. This is not security. In live mode the server must derive tenant from authenticated identity and authorize each resource/action; a browser-supplied ID never proves access.
6. **Audio**: SIP/VoIP/mock inbound call belongs to backend `TelephonyAdapter`. Browser WebRTC/mic is explicitly test-only. Never claim SIP connection from a browser permission result.
7. **Privacy**: caller/transcript/source snippets are untrusted text. Do not use `dangerouslySetInnerHTML`. Do not place transcripts in URLs or console logs. The raw audio storage default is off.
8. **External LLM**: no OpenRouter calls from the frontend. Backend must keep `external_llm_allowed=false` for real calls until legal/security approval, even if synthetic demo calls can use a mock/provider.
9. **Audit/versioning**: transcript correction preserves prior revision + diff/reason/actor/time; scenario publication and ingestion changes need server audit events and rollback support.
10. **Demo labels**: all synthetic data are visibly marked. Demo values are not telemetry, approvals, successful provider deliveries or production status.

## Backend integration points

| File | Integration | Current status |
|---|---|---|
| `src/shared/config/env.ts` | `VITE_API_BASE_URL`, `VITE_LIVEKIT_URL`, `VITE_DEMO_MODE` | Ready for public config |
| `src/shared/api/http.ts` | Common HTTP request/error handling | Implemented |
| `src/features/onboarding/services/onboarding.service.ts` | `POST /tenants`, `POST /tenants/{id}/onboarding/validate`, `POST /tenants/{id}/test-calls` | Paths from Track 1 spec; payload/response types should be cross-checked with backend OpenAPI |
| `src/features/calls/services/calls.service.ts` | `GET /calls`, `GET /calls/{id}`, `GET /admin/sessions`, `GET /admin/sessions/{id}`, `POST /calls/{id}/transcript-corrections` | Call list/detail schemas need confirmation against OpenAPI. Original transcript must not be included unless backend grants `can_view_original`. |
| `src/features/scenarios/services/scenarios.service.ts` | `POST /tenants/{id}/scenarios`, `POST /tenants/{id}/scenarios/{revision}/publish` | POST paths specified; `GET /tenants/{id}/scenarios` is inferred for the editor and must be confirmed |
| `src/features/admin/services/admin.service.ts` | `GET /admin/analytics/calls` | Path specified; aggregate response shape must match backend OpenAPI |
| `src/features/voice/services/session.service.ts` | `POST /sessions`, `POST /sessions/{id}/end` | Legacy browser/test session flow retained |
| `src/features/voice/services/livekit.service.ts` | LiveKit room/mic/remote audio/transcription events | Requires compatible server-side worker events and a short-lived token |
| `src/features/chat/services/chat.service.ts` | Text continuation | Message endpoint/transport not yet defined in Track 1 SSOT; remains an explicitly marked integration gap |

Before wiring production event streams, backend/ML-Flow must confirm partial/final transcript ordering, stable `tenant_id`/`call_id`/`turn_id`/`generation_id`, consent events, route decisions, handoff outcome and cancellation events.

## Important security and scope notes

- The UI's active tenant context is only a selector for demo fixtures. It is not authentication or authorization.
- A role chip or disabled button is not an RBAC implementation. Backend must enforce access for call history, transcript correction, scenario changes, source activation, exports and audit data.
- SIP trunk and human-transfer targets need server-side provider credentials; they must never be browser environment variables.
- `mts-public-demo` is preserved as legacy regression context only. Default tenant knowledge uses generic unapproved placeholders until the business owner provides approved sources.
- Production telephony, consent/legal policy, messenger delivery, human transfer, source approval and OpenRouter route are not verified by this frontend archive.

## Reference documents

- `docs/track1-frontend-scope.md` — frontend requirements extracted from the Track 1 brief.
- `docs/integration-contracts.md` — paths, event mapping and unresolved backend contracts.
- `docs/ui-screen-map.md` — routes and reusable component mapping.
- `docs/tomorrow-checklist.md` — suggested implementation and integration sequence.
- `SPEC_MTS_VOICE_AGENT_TRACK1.md` — canonical Track 1 SSOT supplied with this archive.
- `MTS_VOICE_AGENT_4_DEVELOPERS_TRACK1.md` — supplied team task plan 1.1, frontend ownership and DoD.
- `docs/Лекции_ТЗ_МТС_трек_1.pdf` — source lecture/competition brief.
- `MTS_VOICE_AGENT_4_DEVELOPERS_LEGACY.md` — previous task-plan revision kept for history only.
- `SPEC_MTS_VOICE_AGENT_LEGACY_BROWSER_ASSISTANT.md` — previous consumer browser-helper spec, kept for history only. It is **not** the Track 1 SSOT.

Use `SPEC_MTS_VOICE_AGENT_TRACK1.md` as the normative product/API/security source. The task-plan file assigns ownership but does not override the SSOT.
