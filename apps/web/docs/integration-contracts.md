# Frontend ↔ backend integration contracts (Track 1)

The normative source is `SPEC_MTS_VOICE_AGENT_TRACK1.md`. Track 1's supplied team plan is `MTS_VOICE_AGENT_4_DEVELOPERS_TRACK1.md`. The older `SPEC_MTS_VOICE_AGENT_LEGACY_BROWSER_ASSISTANT.md` describes the preceding consumer browser helper and is not the current SSOT.

## Paths specified in the Track 1 brief

| Method | Path | Frontend adapter | Notes |
|---|---|---|---|
| `POST` | `/tenants` | `onboarding.service.ts` | Creates a tenant profile; the Pydantic payload shape must match backend OpenAPI. |
| `POST` | `/tenants/{id}/onboarding/validate` | `onboarding.service.ts` | Returns validation blockers/warnings. Backend should emit an authoritative onboarding-duration measurement; `client_elapsed_ms` is only an optional UX signal. |
| `POST` | `/tenants/{id}/test-calls` | `onboarding.service.ts` | Requests a mock/test inbound call. A mock does not prove SIP/PSTN connectivity. |
| `GET` | `/calls` | `calls.service.ts` tenant scope | Backend derives tenant from authenticated identity; browser query cannot grant cross-tenant access. |
| `GET` | `/admin/sessions` | `calls.service.ts` admin scope | Paged admin call/session list. The frontend expects a call-list representation including masked caller, route/consent and timing fields; confirm/generate exact OpenAPI response. |
| `POST` | `/calls/{id}/transcript-corrections` | `calls.service.ts` | Preserve old revision, corrected revision, diff, reason, actor/time and audit reference. |
| `POST` | `/calls/{id}/human-transfer` | backend call flow (UI shows result) | Must report provider outcome; no false success state. |
| `POST` | `/calls/{id}/chat-handoff` | backend call flow (UI shows result) | Context passes only after caller consent; links/tokens short lived. |
| `GET` | `/admin/analytics/calls` | `admin.service.ts` | Aggregate call metrics from backend/Prometheus, never from a browser sample. Exact response shape must match OpenAPI. |
| `POST` | `/tenants/{id}/scenarios` | `scenarios.service.ts` | Save/edit draft; exact scenario ID/revision semantics require agreement. |
| `POST` | `/tenants/{id}/scenarios/{revision}/publish` | `scenarios.service.ts` | Server validates, permission-checks, creates version and audit event. |
| `POST` | `/sessions` | `voice/services/session.service.ts` | Legacy browser test session only; response contains session ID and short-lived LiveKit token. |
| `POST` | `/sessions/{id}/end` | `voice/services/session.service.ts` | End browser test session and cancel tasks. |
| `POST` | `/admin/knowledge/ingestion-runs` | planned admin adapter | Requires tenant role, dry-run/ingestion status and audit. |
| `GET` | `/admin/knowledge/ingestion-runs/{id}` | planned admin adapter | Run status/progress/diff. |
| `POST` | `/admin/knowledge/revisions/{id}/activate` | planned admin adapter | Permission + audit + candidate-index validation. |
| `POST` | `/admin/knowledge/rollback` | planned admin adapter | Permission + audit. |
| `GET` / `POST` | `/admin/evaluations` | planned admin adapter | Viewer+ for read, admin/developer for run. |

## Paths/schemas still requiring OpenAPI confirmation

1. `GET /calls/{id}` and `GET /admin/sessions/{id}` are required for tenant/admin detail pages. Their complete TS response is `CallDetail`; generate/validate this type against backend OpenAPI. Frontend adapter currently assumes `CallDetail`.
2. `GET /tenants/{id}/scenarios` is used to populate the scenario editor; confirm or add to SSOT/OpenAPI.
3. Response shape for `POST /tenants/{id}/onboarding/validate`, `POST /tenants/{id}/test-calls`, `GET /admin/analytics/calls`, call detail/corrections and scenario editing/publishing must be generated/validated from Pydantic models. Current TS interfaces are provisional mappings.
4. Text continuation has no agreed message route or transport. Existing `chat.service.ts` is explicitly a placeholder/test fallback. Agree whether messages use REST plus SSE, WebSocket or LiveKit data messages before turning off demo mode.
5. LiveKit application events must define partial/final ASR revision, turn/generation IDs, assistant transcript segments, TTS audio chunks, interruption/cancel and event ordering.
6. Admin login, auth cookie/session acquisition and permission discovery have not been specified here. Backend must authorize every route/action. A hidden React route or role label is not protection.
7. Scenario validation/version diff/rollback and transcript edit permission responses need exact schemas. The frontend looks for `permissions.can_correct_transcript` in call detail; only a backend-authenticated permission may enable edit actions. `permissions.can_view_original` separately controls original ASR revision display; backend must not send original text to callers without that permission.
8. Knowledge source listing/approval API and RAG inspection payload need their routes and schemas confirmed before replacing demo fixtures.

## LiveKit and test-channel responsibilities

`src/features/voice/services/livekit.service.ts` isolates `livekit-client`: connect using a short-lived token, toggle mic for browser test, attach remote audio, clean up tracks and map published transcript events. The LiveKit worker/backend must implement compatible events. The Browser mic flow is not the telephone ingress path. SIP/VoIP call setup, caller notice/consent, transfer and hangup are owned by server `TelephonyAdapter`.

## Privacy, tenant identity and external LLM

- `tenant_id` on a route is not proof of authorization. Backend checks identity/role for every call, transcript, source, scenario, export and ingestion action.
- PII masking and consent policy are enforced server-side, not by UI text only.
- External LLM for real calls is `false` until legal/security approval. Synthetic demo content only may use an allowed mock/provider route.
- Never send OpenRouter key, SIP credentials, private service tokens, raw audio, unredacted caller PII or original transcript to the browser.
- Tenant call history and source records in demo mode are synthetic/in-memory and are filtered in the UI only for demonstration, not as a security control.

## Public browser configuration

```dotenv
VITE_DEMO_MODE=true
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_LIVEKIT_URL=ws://localhost:7880
VITE_APP_NAME=MTS Inbound Voice Agent
```

Every `VITE_*` variable ships to the browser and is public. Never put `OPENROUTER_API_KEY`, `LIVEKIT_API_SECRET`, database/Redis/Qdrant credentials or telephony/messenger provider secrets in Vite env.

## UI navigation and export constraints

- Administrative call list/detail live at `/admin/calls` and `/admin/calls/:sessionId`; opening a call from the admin list must keep the `AdminLayout` shell. The UI calls `GET /admin/sessions` and `GET /admin/sessions/{id}`. The browser route `/admin/sessions` remains a compatibility redirect; the API path is separate under `/api/v1`.
- The routing/scenario editor is available at `/admin/scenarios` while `/scenarios` remains a public tenant-portal entry.
- CSV export is rendered only in demo mode and contains synthetic fixtures. In live mode, do not show an export button unless a server capability/permission and audited export endpoint are provided by OpenAPI.
- The UI does not provide its own auth protocol. Until backend publishes sign-in/session/permission discovery contracts, live admin API calls may return 401/403 and the UI should show a safe error.
