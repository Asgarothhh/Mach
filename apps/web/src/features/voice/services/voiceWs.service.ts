import { mapAnswerEventCitations } from '../../../shared/lib/mapAnswerEventCitations';
import type { TranscriptEvent, VoiceState } from '../../../shared/types/voice';
import { env } from '../../../shared/config/env';

type VoiceWsHandlers = {
  onState: (state: VoiceState) => void;
  onTranscript: (event: TranscriptEvent) => void;
  onError: (message: string) => void;
};

const CAPTURE_RATE = 16000;

function apiBaseToWs(apiBaseUrl: string): string {
  const url = new URL(apiBaseUrl.endsWith('/') ? apiBaseUrl : `${apiBaseUrl}/`);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString().replace(/\/$/, '');
}

function downsampleToPcm16(input: Float32Array, inputRate: number): Int16Array {
  const ratio = inputRate / CAPTURE_RATE;
  const outLength = Math.max(1, Math.floor(input.length / ratio));
  const out = new Int16Array(outLength);
  for (let index = 0; index < outLength; index += 1) {
    const sample = input[Math.floor(index * ratio)] ?? 0;
    const clipped = Math.max(-1, Math.min(1, sample));
    out[index] = clipped < 0 ? clipped * 0x8000 : clipped * 0x7fff;
  }
  return out;
}

function pcm16ToAudioBuffer(ctx: AudioContext, base64: string, sampleRate: number): AudioBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  const samples = new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2));
  const buffer = ctx.createBuffer(1, Math.max(samples.length, 1), sampleRate || 24000);
  const channel = buffer.getChannelData(0);
  for (let index = 0; index < samples.length; index += 1) channel[index] = samples[index] / 32768;
  return buffer;
}

export function shouldDropTtsChunk(
  generationId: string | undefined,
  cancelled: ReadonlySet<string>,
): boolean {
  return Boolean(generationId && cancelled.has(generationId));
}

/**
 * Browser test channel: PCM16-LE @16 kHz over WS /api/v1/ws/sessions/{id}.
 * Not SIP, not LiveKit, not a production telephony path.
 */
export class VoiceWsClient {
  private socket: WebSocket | null = null;
  private mediaStream: MediaStream | null = null;
  private captureContext: AudioContext | null = null;
  private playbackContext: AudioContext | null = null;
  private processor: ScriptProcessorNode | null = null;
  private playHead = 0;
  private activeSources = new Set<AudioBufferSourceNode>();
  private cancelledGenerations = new Set<string>();
  private currentGeneration: string | null = null;
  private ttsBuffer = '';
  private lastTtsSegment = '';

  constructor(private readonly handlers: VoiceWsHandlers) {}

  async connect(sessionId: string): Promise<void> {
    const wsUrl = `${apiBaseToWs(env.apiBaseUrl)}/ws/sessions/${encodeURIComponent(sessionId)}`;
    this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    const capture = new AudioContext();
    this.captureContext = capture;
    const source = capture.createMediaStreamSource(this.mediaStream);
    const processor = capture.createScriptProcessor(4096, 1, 1);
    this.processor = processor;
    processor.onaudioprocess = (event) => {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return;
      const input = event.inputBuffer.getChannelData(0);
      const pcm = downsampleToPcm16(input, capture.sampleRate);
      this.socket.send(pcm.buffer);
    };
    source.connect(processor);
    processor.connect(capture.destination);

    await new Promise<void>((resolve, reject) => {
      const socket = new WebSocket(wsUrl);
      this.socket = socket;
      socket.binaryType = 'arraybuffer';
      socket.onopen = () => resolve();
      socket.onerror = () => reject(new Error('Не удалось подключить голос. Попробуйте ещё раз или напишите текстом.'));
      socket.onmessage = (event) => {
        if (typeof event.data !== 'string') return;
        try {
          this.handleEvent(JSON.parse(event.data) as { type?: string; payload?: Record<string, unknown> });
        } catch {
          this.handlers.onError('Получено некорректное WS-событие.');
        }
      };
      socket.onclose = () => this.handlers.onState('ended');
    });
  }

  interruptPlayback(): void {
    if (this.currentGeneration) this.cancelledGenerations.add(this.currentGeneration);
    for (const source of this.activeSources) {
      try { source.stop(); } catch { /* already stopped */ }
    }
    this.activeSources.clear();
    this.playHead = this.playbackContext?.currentTime ?? 0;
    this.ttsBuffer = '';
    this.lastTtsSegment = '';
  }

  async disconnect(): Promise<void> {
    this.interruptPlayback();
    this.processor?.disconnect();
    this.processor = null;
    await this.captureContext?.close().catch(() => undefined);
    this.captureContext = null;
    this.mediaStream?.getTracks().forEach((track) => track.stop());
    this.mediaStream = null;
    this.socket?.close();
    this.socket = null;
  }

  async setMicrophoneEnabled(enabled: boolean): Promise<void> {
    this.mediaStream?.getAudioTracks().forEach((track) => {
      track.enabled = enabled;
    });
  }

  private handleEvent(message: { type?: string; payload?: Record<string, unknown> }): void {
    const payload = message.payload ?? {};
    if (message.type === 'InterruptionEvent') {
      const turnId = this.currentGeneration ?? (typeof payload.interrupted_turn_id === 'string' ? payload.interrupted_turn_id : 'tts');
      if (this.ttsBuffer) {
        this.handlers.onTranscript({
          id: `${turnId}:tts`,
          text: this.ttsBuffer,
          final: true,
          role: 'assistant',
          turnId,
          interrupted: true,
        });
      }
      this.interruptPlayback();
      this.handlers.onState('listening');
      return;
    }
    if (message.type === 'AnswerEvent') {
      const text = typeof payload.answer_text === 'string' ? payload.answer_text : '';
      const turnId = typeof payload.turn_id === 'string' ? payload.turn_id : 'answer';
      const citations = mapAnswerEventCitations(payload);
      if (text) {
        this.handlers.onTranscript({
          id: `${turnId}:tts`,
          text,
          final: false,
          role: 'assistant',
          turnId,
          ...(citations.length ? { citations } : {}),
        });
      }
      this.handlers.onState('processing');
      return;
    }
    if (message.type === 'ASREvent') {
      const text = typeof payload.text === 'string' ? payload.text : '';
      const turnId = typeof payload.turn_id === 'string' ? payload.turn_id : 'turn';
      if (text) {
        this.handlers.onTranscript({
          id: turnId,
          text,
          final: payload.is_final !== false,
          role: 'user',
          turnId,
        });
      }
      if (payload.is_final) this.handlers.onState('processing');
      return;
    }
    if (message.type === 'VADEvent') {
      if (payload.is_speech) this.handlers.onState('listening');
      return;
    }
    if (message.type === 'TTSChunkEvent') {
      const generationId = typeof payload.generation_id === 'string' ? payload.generation_id : undefined;
      if (shouldDropTtsChunk(generationId, this.cancelledGenerations)) return;
      if (generationId) this.currentGeneration = generationId;
      const text = typeof payload.text === 'string' ? payload.text : '';
      const turnId = typeof payload.turn_id === 'string' ? payload.turn_id : generationId ?? 'tts';
      if (text && text !== this.lastTtsSegment) {
        this.ttsBuffer = this.ttsBuffer ? `${this.ttsBuffer} ${text}` : text;
        this.lastTtsSegment = text;
      }
      if (this.ttsBuffer) {
        this.handlers.onTranscript({
          id: `${turnId}:tts`,
          text: this.ttsBuffer,
          final: Boolean(payload.is_last_chunk),
          role: 'assistant',
          turnId,
        });
      }
      const audio = typeof payload.audio_base64 === 'string' ? payload.audio_base64 : '';
      if (audio) {
        this.handlers.onState('speaking');
        void this.enqueuePlayback(audio, Number(payload.sample_rate) || 24000);
      }
      if (payload.is_last_chunk) {
        this.ttsBuffer = '';
        this.lastTtsSegment = '';
        this.handlers.onState('listening');
      }
    }
  }

  private async enqueuePlayback(audioBase64: string, sampleRate: number): Promise<void> {
    this.playbackContext ??= new AudioContext();
    const ctx = this.playbackContext;
    const buffer = pcm16ToAudioBuffer(ctx, audioBase64, sampleRate);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    const startAt = Math.max(ctx.currentTime, this.playHead);
    source.start(startAt);
    this.playHead = startAt + buffer.duration;
    this.activeSources.add(source);
    source.onended = () => this.activeSources.delete(source);
  }
}
