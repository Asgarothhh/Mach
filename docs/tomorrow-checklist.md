# Frontend Track 1 — integration checklist

## First local run

- [ ] Install Node.js 22.12+ and run `npm install`.
- [ ] Copy `.env.example` to `.env`; leave `VITE_DEMO_MODE=true` first.
- [ ] Run `npm run typecheck`, `npm run build`, `npm run dev`.
- [ ] Walk through `/onboarding` and run a clearly labelled synthetic test call.
- [ ] Open the test call in `/calls/:callId`; inspect transcript, route decision, consent and unapproved synthetic sources.
- [ ] Edit a caller transcript and verify the original/revision note is visible in demo mode.
- [ ] Open `/scenarios`, edit a draft routing rule, save and publish (demo-only).
- [ ] Open `/admin` and review the synthetic call analytics; check `/admin/knowledge` clearly separates active tenant fixtures from `mts-public-demo`.
- [ ] Open `/voice/permission`; confirm the persistent banner states this is browser test mode, not a telephone call.

## Contract meeting with backend/ML-Flow

- [ ] Verify Pydantic/OpenAPI shapes for `POST /tenants`, onboarding validate, test-calls and route/call detail.
- [ ] Confirm the `GET /calls` query/pagination contract and explicit `GET /calls/{id}` response.
- [ ] Agree role discovery/authorization response, especially `transcript_editor`, scenario editor/publisher, knowledge editor and export permission.
- [ ] Confirm correction payload: `turn_id`, corrected text, reason, expected revision; response carries previous/new revision and audit reference.
- [ ] Confirm scenario collection `GET`, draft save/upsert ID semantics, validation, publish/version diff and rollback API.
- [ ] Confirm `GET /admin/analytics/calls` structure and whether it is scoped through authenticated tenant context.
- [ ] Confirm LiveKit transcript event names/revisions/turn IDs and how assistant TTS chunks/interruptions arrive in UI.
- [ ] Agree text fallback transport. Do not assume `POST /sessions/{id}/messages` exists.
- [ ] Confirm consent notice/consent outcome event and safe path when caller refuses.
- [ ] Confirm how SIP/mock inbound test calls and human-transfer outcome are surfaced; no UI success without a positive adapter result.
- [ ] Confirm `external_llm_allowed=false` is enforced server-side for real calls until legal/security approval.

## Before disabling demo mode

- [ ] Backend auth is integrated; tenant isolation is proved server-side, not just filtered in UI.
- [ ] Live API payloads pass contract tests generated from the canonical Track 1 SSOT/OpenAPI.
- [ ] Call history and transcript details never expose another tenant, caller PII or original transcript to unauthorized roles.
- [ ] Transcript edit creates a new version and server audit event.
- [ ] Scenario publishing and ingestion require server-side RBAC, diff/validation and audit.
- [ ] SIP integration is verified by backend/telephony team separately from the browser mic.
- [ ] No real call reaches an external LLM before documented legal/security approval.
- [ ] Production metrics are backend/Prometheus aggregates, not browser fixtures.
