# Frontend scope notes — MTS Inbound Voice Agent, Track 1

This file is a frontend-focused extraction of the Track 1 requirements supplied by the team. It is **not a replacement for the canonical `SPEC_MTS_VOICE_AGENT_TRACK1.md` SSOT**.

## Product shift

The product is an inbound call agent for business tenants. The core browser product is the tenant onboarding/control portal; SIP/VoIP or an explicitly labelled mock/test-call adapter is the primary call ingress. Browser WebRTC remains a test console, not proof of a production telephone integration. The prior public MTS FAQ/roaming corpus is a legacy demo fixture under a separate tenant ID `mts-public-demo` and is not loaded into business tenants by default.

## Mandatory frontend gates

1. **Onboarding in ≤5 minutes**: create/select tenant, configure company greeting/scenario, choose routing policy, configure a test call channel and notice/consent text, validate the configuration, initiate a test inbound call. Show missing production credentials as a blocker. Frontend timer is for UX only; backend should own the authoritative measurement event.
2. **Call history**: filter by date/status/tenant/intent/route; show call ID, channel, masked caller alias, duration, turns, final transcript, route/handoff/fallback outcome and latency.
3. **Manual transcript correction**: show partial/final/corrected states and confidence where available. Editing requires a backend-granted `transcript_editor` permission and must preserve original revision, corrected revision, diff, reason, actor, timestamp and audit ID. Never represent a local-only edit as production persistence.
4. **Scenario/routing editor**: edit draft greeting/instructions/fallback and deterministic route rules. Support save draft, validate, publish a version and rollback when API support is present. Publishing must be permission-checked and audited server-side.
5. **Voice/chat/human routing**: show actual decision and outcome. Chat context is sent only after caller consent; human transfer is complete only after provider confirmation. Failed/unsupported adapters get explicit fallback states.
6. **Consent/privacy**: onboarding can configure the notice/version. Call details display consent state and raw-audio storage flag. Real raw audio recording is off by default. External LLM for real calls is disabled until legal/security approval.
7. **Tenant isolation**: every call, transcript, scenario, source, ingestion run and analytic belongs to a tenant. The active tenant selector and UI filters are not security controls; the backend derives identity and authorizes each request.
8. **Analytics**: display backend-sourced call counts, intent distribution, voice/chat/human handoff rates, errors, TTFA p50/p95 and stage latency. Browser-sampled values do not substitute for backend aggregation.

## Required routes in this frontend

- `/` — tenant workspace overview.
- `/onboarding` — onboarding wizard.
- `/calls` and `/calls/:callId` — call history and detail/transcript correction.
- `/scenarios` — scenario and routing editor.
- `/voice/*` — browser mic/WebRTC test console only.
- `/admin` — call analytics.
- `/admin/calls` and `/admin/calls/:sessionId` — administrative call list/detail using admin session APIs.
- `/admin/scenarios` — scenario/routing editor under the admin layout.
- `/admin/knowledge`, `/admin/sync`, `/admin/rag`, `/admin/quality`, `/admin/configuration`, `/admin/audit`, `/admin/evaluations` — tenant-scoped operational UI.
- `/voice/*` remains a browser microphone/WebRTC test console only; SIP/PSTN ingress belongs to the backend TelephonyAdapter.

## API contracts known from Track 1 brief

- `POST /tenants`
- `POST /tenants/{id}/onboarding/validate`
- `POST /tenants/{id}/test-calls`
- `GET /calls`
- `POST /calls/{id}/transcript-corrections`
- `POST /calls/{id}/human-transfer`
- `POST /calls/{id}/chat-handoff`
- `GET /admin/analytics/calls`
- `POST /tenants/{id}/scenarios`
- `POST /tenants/{id}/scenarios/{revision}/publish`
- `POST /sessions` and `POST /sessions/{id}/end` for browser test sessions
- The prior RAG/ingestion/evaluation/admin endpoints remain applicable, with tenant/RBAC scoping added.

`GET /calls/{id}` and `GET /tenants/{id}/scenarios` are needed for the frontend screens but should be confirmed against backend OpenAPI because the supplied endpoint table does not explicitly fix their request/response schemas. Text-message endpoint/transport remains an open contract. This frontend does not assume a live chat message endpoint exists.

## Demo limitations

Synthetic test calls are stored in an in-memory fixture, not PostgreSQL and not a SIP trunk. Scenario/source/analytics fixtures are similarly non-persistent. Admin authentication/RBAC is not implemented in React; the backend must enforce it. Do not demo synthetic model latency as a production measurement, don't send real caller content to OpenRouter, and don't show an action as complete without the corresponding adapter result.
