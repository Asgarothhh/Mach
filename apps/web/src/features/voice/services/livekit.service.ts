import {
  ConnectionState,
  Room,
  RoomEvent,
  Track,
  type RemoteTrack,
  type TranscriptionSegment,
} from 'livekit-client';
import type { TranscriptEvent, VoiceState } from '../../../shared/types/voice';

type LiveKitHandlers = {
  onState: (state: VoiceState) => void;
  onTranscript: (event: TranscriptEvent) => void;
  onError: (message: string) => void;
};

/** Owns the WebRTC room and translates low-level LiveKit events into app-level events. */
export class LiveKitVoiceClient {
  private room: Room | null = null;
  private readonly attachedAudio = new Set<HTMLMediaElement>();

  constructor(private readonly handlers: LiveKitHandlers) {}

  async connect(serverUrl: string, token: string): Promise<void> {
    if (!serverUrl) throw new Error('VITE_LIVEKIT_URL не задан.');

    const room = new Room({ adaptiveStream: true, dynacast: true });
    this.room = room;

    room.on(RoomEvent.ConnectionStateChanged, (state: ConnectionState) => {
      if (state === ConnectionState.Connected) this.handlers.onState('listening');
      if (state === ConnectionState.Reconnecting) this.handlers.onState('connecting');
      if (state === ConnectionState.Disconnected) this.handlers.onState('ended');
    });

    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind !== Track.Kind.Audio) return;
      const audioElement = track.attach();
      audioElement.autoplay = true;
      audioElement.setAttribute('data-livekit-audio', track.sid ?? '');
      document.body.appendChild(audioElement);
      this.attachedAudio.add(audioElement);
    });

    room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
      if (speakers.some((participant) => !participant.isLocal)) {
        this.handlers.onState('speaking');
      } else if (speakers.some((participant) => participant.isLocal)) {
        this.handlers.onState('processing');
      } else if (room.state === ConnectionState.Connected) {
        this.handlers.onState('listening');
      }
    });

    room.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
      track.detach().forEach((element) => {
        this.attachedAudio.delete(element);
        element.remove();
      });
    });

    // LiveKit Agent transcription support depends on the server-side agent publishing transcripts.
    room.on(RoomEvent.TranscriptionReceived, (segments: TranscriptionSegment[], participant) => {
      for (const segment of segments) {
        this.handlers.onTranscript({
          id: segment.id,
          text: segment.text,
          final: segment.final,
          role: participant?.isLocal ? 'user' : 'assistant',
          language: segment.language,
          turnId: segment.id,
        });
      }
    });

    room.on(RoomEvent.Disconnected, () => this.handlers.onState('ended'));

    try {
      await room.connect(serverUrl, token);
      await room.localParticipant.setMicrophoneEnabled(true);
      this.handlers.onState('listening');
    } catch (error) {
      await this.disconnect();
      const message = error instanceof Error ? error.message : 'Не удалось подключиться к LiveKit.';
      this.handlers.onError(message);
      throw error;
    }
  }

  async setMicrophoneEnabled(enabled: boolean): Promise<void> {
    if (!this.room) throw new Error('Голосовой канал уже отключён.');
    await this.room.localParticipant.setMicrophoneEnabled(enabled);
  }

  async disconnect(): Promise<void> {
    const room = this.room;
    this.room = null;

    if (room) {
      try {
        await room.disconnect();
      } finally {
        room.removeAllListeners();
      }
    }

    for (const element of this.attachedAudio) {
      element.pause();
      element.remove();
    }
    this.attachedAudio.clear();
  }
}
