# Frontend-only handoff

This folder contains only the web frontend. No backend files were included or changed.

## Local run

Prerequisites: Node.js 22.12+ and npm.

```powershell
npm install
Copy-Item .env.example .env
npm test
npm run typecheck
npm run build
npm run dev
```

The default `VITE_DEMO_MODE=true` should stay on until the backend owner confirms the API contract and authentication. All `VITE_*` values are browser-visible and must never contain API keys, SIP credentials, OpenRouter secrets, database passwords, or internal service credentials.

## Frontend-owned integration boundaries

- `src/shared/api/http.ts` — shared HTTP request/error handling.
- `src/shared/config/env.ts` — public browser configuration.
- `src/features/onboarding/services/onboarding.service.ts` — onboarding adapter. Endpoint paths are derived from Track 1 SSOT; request/response schemas must be checked against backend OpenAPI before live mode.
- `src/features/calls/services/calls.service.ts` — calls/history/details/correction adapter. Sensitive original transcript is displayed only when a server-provided permission allows it.
- `src/features/scenarios/services/scenarios.service.ts` — scenarios and routing policy adapter. List/detail/validation/publish/rollback schemas need backend confirmation.
- `src/features/admin/services/admin.service.ts` — analytics and admin-data adapter; synthetic fixtures remain demo-only.
- `src/features/voice/services/session.service.ts` and `livekit.service.ts` — browser WebRTC test console only. Real inbound telephone calls belong to the server TelephonyAdapter.
- `src/features/chat/services/chat.service.ts` — text fallback contract is intentionally not assumed to be a production endpoint until backend owner confirms it.
- `src/features/chat/services/backendTextTest.service.ts` — optional experimental text-WebSocket adapter; disabled by default. Use it only after backend owner confirms the exact WebSocket contract and server support. It is not a request to change backend.

## Known backend contract status from the supplied `Mach.zip`

The original archive exposed these route shapes in the checked source:

- `POST /api/v1/sessions`
- `POST /api/v1/sessions/{session_id}/end`
- `WS /api/v1/ws/sessions/{session_id}` with event types such as `ASREvent`, `VADEvent`, and `InterruptionEvent`
- `GET /api/v1/admin/sessions`
- `GET /api/v1/admin/sessions/{session_id}/turns`
- `GET /health/live` and `GET /health/ready`

These route shapes alone do not guarantee that the full end-to-end flow works. In the supplied backend source, the frontend cannot assume a LiveKit token response, real audio ingress, SIP/VoIP, full Track 1 onboarding/scenario APIs, correction persistence, or complete authentication/RBAC. The backend owner should confirm which endpoints and schemas are supported and send their changes when ready.

The Track 1 SSOT lists additional target APIs such as `/tenants`, `/calls`, `/tenants/{id}/scenarios`, `/admin/analytics/calls`, knowledge ingestion and audit APIs. They are product requirements, not proof those endpoints already exist in the current backend.

## Live integration rule

Do not switch the entire application to `VITE_DEMO_MODE=false` just because one API responds. Keep fixture-backed pages in demo mode until their specific services are wired and the backend confirms schemas, auth/session acquisition, tenant scope, permissions, pagination, errors, and WebSocket event ordering. Frontend tenant selection and UI role labels are not authorization.
