import { useCallback, useEffect, useRef, useState } from 'react';
import { env, liveVoiceConfigured } from '../../../shared/config/env';
import type { TranscriptEvent, VoiceState } from '../../../shared/types/voice';
import { createVoiceSession, endVoiceSession } from '../services/session.service';
import { LiveKitVoiceClient } from '../services/livekit.service';

type Options = {
  onTranscript: (event: TranscriptEvent) => void;
};

export function useVoiceSession({ onTranscript }: Options) {
  const [state, setState] = useState<VoiceState>('idle');
  const [notice, setNotice] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [clockNow, setClockNow] = useState(Date.now());

  useEffect(() => {
    if (!startedAt) return;
    const timer = window.setInterval(() => setClockNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  const clientRef = useRef<LiveKitVoiceClient | null>(null);
  const demoTimerRef = useRef<number | null>(null);
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  const start = useCallback(async () => {
    setNotice(null);
    if (env.demoMode) {
      // Explicitly simulated UI flow; no audio is sent and no backend session is created.
      setState('connecting');
      setNotice(null);
      if (demoTimerRef.current !== null) window.clearTimeout(demoTimerRef.current);
      demoTimerRef.current = window.setTimeout(() => {
        setStartedAt(Date.now());
        setState('listening');
        demoTimerRef.current = null;
      }, 1200);
      return;
    }
    if (!liveVoiceConfigured) {
      setState('degraded');
      setNotice('Не задан VITE_LIVEKIT_URL. Проверьте frontend .env и перезапустите Vite.');
      return;
    }

    setState('requesting_microphone');
    let createdSessionId: string | null = null;
    try {
      const session = await createVoiceSession();
      createdSessionId = session.session_id;
      setSessionId(session.session_id);
      // The browser asks for microphone permission when LiveKit enables its microphone.
      setState('connecting');
      const client = new LiveKitVoiceClient({
        onState: setState,
        onTranscript: (event) => onTranscriptRef.current(event),
        onError: setNotice,
      });
      clientRef.current = client;
      await client.connect(env.liveKitUrl, session.token);
      setStartedAt(Date.now());
      setState('listening');
    } catch (error) {
      await clientRef.current?.disconnect().catch(() => undefined);
      clientRef.current = null;
      if (createdSessionId) {
        await endVoiceSession(createdSessionId).catch(() => undefined);
      }
      setSessionId(null);
      setState('degraded');
      setNotice(
        error instanceof Error
          ? error.message
          : 'Не удалось начать голосовую сессию. Проверьте API и LiveKit.',
      );
    }
  }, []);

  const stop = useCallback(async () => {
    setNotice(null);
    if (demoTimerRef.current !== null) { window.clearTimeout(demoTimerRef.current); demoTimerRef.current = null; }
    await clientRef.current?.disconnect().catch(() => undefined);
    clientRef.current = null;
    if (sessionId && !env.demoMode) {
      try {
        await endVoiceSession(sessionId);
      } catch {
        // The media connection has already been closed; expose a safe message rather than raw details.
        setNotice('Голос отключён, но API не подтвердил завершение сессии. Проверьте журнал backend.');
      }
    }
    setSessionId(null);
    setStartedAt(null);
    setState('ended');
  }, [sessionId]);

  const switchToText = useCallback(async () => {
    setNotice(null);
    if (env.demoMode) {
      setState('degraded');
      return;
    }
    try {
      if (clientRef.current) await clientRef.current.setMicrophoneEnabled(false);
      setState('degraded');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Не удалось отключить микрофон.');
      setState('degraded');
    }
  }, []);

  const resumeVoiceInput = useCallback(async (): Promise<boolean> => {
    setNotice(null);
    if (env.demoMode) {
      setState('listening');
      return true;
    }
    try {
      if (clientRef.current && sessionId) {
        await clientRef.current.setMicrophoneEnabled(true);
        setState('listening');
        return true;
      }
      return false;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Не удалось восстановить микрофон.');
      return false;
    }
  }, [sessionId]);

  const reset = useCallback(() => {
    if (demoTimerRef.current !== null) { window.clearTimeout(demoTimerRef.current); demoTimerRef.current = null; }
    setNotice(null);
    setStartedAt(null);
    setSessionId(null);
    setState('idle');
  }, []);

  useEffect(() => () => {
    if (demoTimerRef.current !== null) window.clearTimeout(demoTimerRef.current);
    void clientRef.current?.disconnect();
  }, []);

  return {
    state,
    notice,
    sessionId,
    startedAt,
    elapsedSeconds: startedAt ? Math.floor((clockNow - startedAt) / 1000) : 0,
    isConnected: state === 'listening' || state === 'processing' || state === 'speaking',
    start,
    stop,
    switchToText,
    resumeVoiceInput,
    reset,
  };
}
