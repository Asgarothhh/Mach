import type { SourceCitation } from './api';

export type VoiceState =
  | 'idle'
  | 'requesting_microphone'
  | 'connecting'
  | 'listening'
  | 'processing'
  | 'speaking'
  | 'degraded'
  | 'ended';

export type MessageRole = 'user' | 'assistant' | 'system';
export type MessageOrigin = 'live' | 'demo';

export interface ConversationMessage {
  id: string;
  turnId?: string;
  role: MessageRole;
  text: string;
  createdAt: string;
  final: boolean;
  origin: MessageOrigin;
  citations?: SourceCitation[];
}

export interface TranscriptEvent {
  id: string;
  text: string;
  final: boolean;
  role: Exclude<MessageRole, 'system'>;
  language?: string;
  turnId?: string;
}

export interface VoiceStatusEvent {
  state: VoiceState;
  message?: string;
}
