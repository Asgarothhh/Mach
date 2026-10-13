# UI screen map — Track 1

The visual language inherits the previous MTS Figma style (white canvas, MTS red accent, pale grey stage, round cards, fine blue-grey borders), but product information architecture is now for an inbound business calling agent.

## Tenant portal

| Screen | Route | Reusable parts | Main interaction |
|---|---|---|---|
| Tenant workspace | `/` | `AppHeader`, `AppFooter`, `Brand`, `Waveform`, overview cards | Go to onboarding, calls, scenarios or admin |
| Onboarding wizard · company | `/onboarding` step 1 | `SectionHeading`, `track-field`, `track-wizard-progress` | Tenant display name and basic profile |
| Onboarding wizard · scenario | `/onboarding` step 2 | `track-choice`, routing choices | Greeting, voice-first / chat-for-complex / human-for-complex policy |
| Onboarding wizard · channels | `/onboarding` step 3 | channel choices, fields/toggles | Mock/SIP endpoint reference, chat and human-transfer labels |
| Onboarding wizard · notice/test | `/onboarding` step 4 | notice editor, success/result card | Configure notice/version, validate, run test call and show limitations |
| Call history | `/calls` | filter controls, route/status pills, `track-table` | Search by call/alias/intent, filter route/channel/status, open detail |
| Call detail | `/calls/:callId` | transcript turn, routing timeline, source item, policy panel | Correct a final caller transcript if the backend grants permission; preserve original/version diff |
| Scenario & routing editor | `/scenarios` and `/admin/scenarios` | scenario list, fields, rule editor, version box | Draft/edit, enable/disable rules, route decision, save draft/publish |
| Browser mic test | `/voice/permission` | legacy voice stage | Request browser mic only for test mode |
| Browser test connecting/live/text/ended | `/voice/connecting`, `/voice/live`, `/text`, `/ended` | `Waveform`, `MessageBubble`, `SourceCard` | Test LiveKit session; the layout displays a persistent test-only banner |

## Admin/control plane

| Screen | Route | Main blocks |
|---|---|---|
| Call analytics overview | `/admin` | call counts, voice/chat/human rates, errors, TTFA p50/p95, latency spans, top intents |
| Administrative call history | `/admin/calls` and `/admin/calls/:sessionId` | Uses `/api/v1/admin/sessions` and `/api/v1/admin/sessions/{id}`; keeps admin layout and permissions |
| Tenant knowledge | `/admin/knowledge` | tenant ID, synthetic unapproved sources, freshness rules, isolated `mts-public-demo` fixture index |
| Ingestion | `/admin/sync` | dry-run/review/activate/rollback scaffold; disabled for live mode until API adapter is wired |
| RAG inspection | `/admin/rag` | query, tenant, candidate scores, evidence preview; fixture only until retrieval diagnostics API is agreed |
| Quality review | `/admin/quality` | ASR/routing/source/handoff categories; demo annotation state |
| Configuration/privacy | `/admin/configuration` | consent/privacy policy and external-LLM safety gate, synthetic model config |
| Audit/security | `/admin/audit` | synthetic audit and security events |
| Evaluation | `/admin/evaluations` | synthetic WER/RAG/grounding/latency metrics |

## Reusable design and responsiveness

- `PublicLayout` and `AdminLayout` are separate route shells; shared UI primitives live in `src/shared/components`.
- `track-*` CSS classes are namespaced for Track 1 pages so the legacy browser-test-console styles can remain during migration.
- Wide call/knowledge tables scroll inside a local wrapper instead of forcing the full page to overflow.
- On small screens, hero, forms, call-detail sections and scenario editor stack vertically; wizard labels and nav can scroll without clipping.
- Demo source/call/analytics values are always marked synthetic/unapproved. The legacy `mts.by` corpus is not loaded as a default tenant's knowledge.
