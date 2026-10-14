export type TenantStatus = 'draft' | 'active' | 'needs_setup';
export type InboundAdapter = 'mock' | 'sip';
export type RoutePolicy = 'voice_first' | 'chat_for_complex' | 'human_for_complex';
export type ChannelChoice = 'voice' | 'chat_offer' | 'human_handoff' | 'fallback';
export type CallStatus = 'active' | 'completed' | 'degraded' | 'handoff' | 'failed';
export type CallChannel = 'telephone' | 'test_call' | 'browser_test';
export type ConsentState = 'accepted' | 'declined' | 'pending' | 'not_required_demo';
export type TranscriptStatus = 'interim' | 'final' | 'corrected';
export type ScenarioStatus = 'draft' | 'published' | 'archived';

export interface TenantProfile {
  tenant_id: string;
  display_name: string;
  status: TenantStatus;
  created_at: string;
  settings_revision: string;
  greeting: string;
  route_policy: RoutePolicy;
  complexity_threshold_seconds: number;
  chat_provider: 'none' | 'mock';
  chat_destination_label: string;
  inbound_adapter: InboundAdapter;
  inbound_endpoint_label: string;
  human_transfer_label: string;
  human_transfer_enabled: boolean;
  consent_notice: string;
  consent_notice_version: string;
  support_url?: string;
}

export interface TranscriptTurn {
  turn_id: string;
  sequence_no: number;
  role: 'caller' | 'agent' | 'system';
  text: string;
  status: TranscriptStatus;
  started_at: string;
  confidence?: number;
  original_text?: string;
  correction_reason?: string;
  correction_audit?: { audit_event_id: string; actor_id: string; corrected_at: string; diff: { before: string; after: string } };
  citations?: SourceReference[];
}

export interface SourceReference {
  source_id: string;
  title: string;
  url: string;
  revision_id: string;
  approved: boolean;
  excerpt?: string;
}

export interface RoutingEvent {
  event_id: string;
  created_at: string;
  decision: ChannelChoice;
  reason: string;
  policy_revision: string;
  consent_state: ConsentState;
  outcome?: string;
}

export interface CallSummary {
  call_id: string;
  session_id: string;
  tenant_id: string;
  created_at: string;
  ended_at?: string;
  status: CallStatus;
  channel: CallChannel;
  caller_alias: string;
  language: 'ru' | 'be' | 'en';
  intent: string;
  route_decision: ChannelChoice;
  consent_state: ConsentState;
  duration_seconds?: number;
  turn_count: number;
  ttfa_ms?: number;
  error_code?: string;
}

export interface CallDetail {
  call: CallSummary;
  turns: TranscriptTurn[];
  routing_events: RoutingEvent[];
  sources: SourceReference[];
  audio_recorded: boolean;
  transcript_revision: string;
  permissions?: { can_correct_transcript: boolean; can_view_original?: boolean; can_export?: boolean };
}

export interface ScenarioRule {
  rule_id: string;
  label: string;
  match_description: string;
  decision: ChannelChoice;
  enabled: boolean;
  priority: number;
}

export interface ScenarioProfile {
  scenario_id: string;
  tenant_id: string;
  revision_id: string;
  name: string;
  description: string;
  intent: string;
  instructions: string;
  greeting: string;
  fallback_text: string;
  status: ScenarioStatus;
  updated_at: string;
  rules: ScenarioRule[];
}

export interface ScenarioVersionRecord {
  scenario_id: string;
  revision_id: string;
  status: ScenarioStatus;
  updated_at: string;
  change_summary: string;
  snapshot: ScenarioProfile;
}

export interface TenantCreateInput {
  display_name: string;
  greeting: string;
  route_policy: RoutePolicy;
  complexity_threshold_seconds: number;
  chat_provider: 'none' | 'mock';
  chat_destination_label: string;
  inbound_adapter: InboundAdapter;
  inbound_endpoint_label: string;
  human_transfer_label: string;
  human_transfer_enabled: boolean;
  consent_notice: string;
  consent_notice_version: string;
}

export interface OnboardingValidation {
  ready: boolean;
  blockers: string[];
  warnings: string[];
  elapsed_ms?: number;
}

export interface TestCallResult {
  call_id: string;
  session_id: string;
  status: 'created' | 'started' | 'failed';
  adapter: InboundAdapter;
  is_mock: boolean;
  message: string;
}

export interface TranscriptCorrectionInput {
  turn_id: string;
  corrected_text: string;
  reason: string;
  expected_revision: string;
}

export interface ScenarioDraftInput {
  name: string;
  description: string;
  intent: string;
  instructions: string;
  greeting: string;
  fallback_text: string;
  rules: ScenarioRule[];
}
