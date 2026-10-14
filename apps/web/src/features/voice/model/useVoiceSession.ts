import { useCallback, useEffect, useRef, useState } from 'react';
import { env, liveVoiceConfigured, wsVoiceConfigured } from '../../../shared/config/env';
import type { TranscriptEvent, VoiceState } from '../../../shared/types/voice';
import { useTenant } from '../../tenant/model/TenantContext';
import { createVoiceSession, endVoiceSession } from '../services/session.service';
import { LiveKitVoiceClient } from '../services/livekit.service';
import { VoiceWsClient } from '../services/voiceWs.service';

type Options = {
  onTranscript: (event: TranscriptEvent) => void;
};

export function useVoiceSession({ onTranscript }: Options) {
  const { tenantId } = useTenant();
  const [state, setState] = useState<VoiceState>('idle');
  const [notice, setNotice] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionTenantId, setSessionTenantId] = useState<string | null>(null);
  const [textPreferred, setTextPreferred] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [clockNow, setClockNow] = useState(Date.now());
  const [channelLabel, setChannelLabel] = useState('Голосовой помощник в браузере');

  useEffect(() => {
    if (!startedAt) return;
    const timer = window.setInterval(() => setClockNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  const liveKitRef = useRef<LiveKitVoiceClient | null>(null);
  const wsRef = useRef<VoiceWsClient | null>(null);
  const demoTimerRef = useRef<number | null>(null);
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  const start = useCallback(async () => {
    setNotice(null);
    if (env.demoMode) {
      setChannelLabel('Демонстрационный разговор без микрофона');
      setState('connecting');
      if (demoTimerRef.current !== null) window.clearTimeout(demoTimerRef.current);
      demoTimerRef.current = window.setTimeout(() => {
        setStartedAt(Date.now());
        setState('listening');
        demoTimerRef.current = null;
      }, 1200);
      return;
    }
    if (liveVoiceConfigured) {
      setChannelLabel('Голосовой помощник в браузере');
      setState('requesting_microphone');
      let createdSessionId: string | null = null;
      try {
        const session = await createVoiceSession(tenantId);
        createdSessionId = session.session_id;
        setSessionId(session.session_id);
        setSessionTenantId(tenantId);
        if (session.opening_greeting) {
          onTranscriptRef.current({
            id: `${session.session_id}:opening`,
            text: session.opening_greeting,
            final: true,
            role: 'assistant',
            turnId: `${session.session_id}:opening`,
          });
        }
        if (!session.token) {
          throw new Error('Не удалось подключить голос. Попробуйте ещё раз или напишите текстом.');
        }
        setState('connecting');
        const client = new LiveKitVoiceClient({
          onState: setState,
          onTranscript: (event) => onTranscriptRef.current(event),
          onError: setNotice,
        });
        liveKitRef.current = client;
        await client.connect(env.liveKitUrl, session.token);
        setStartedAt(Date.now());
        setState('listening');
      } catch (error) {
        await liveKitRef.current?.disconnect().catch(() => undefined);
        liveKitRef.current = null;
        if (createdSessionId) {
          await endVoiceSession(createdSessionId).catch(() => undefined);
        }
        setSessionId(null);
        setSessionTenantId(null);
        setState('degraded');
        setNotice(error instanceof Error ? error.message : 'Не удалось подключить голос. Попробуйте ещё раз или напишите текстом.');
      }
      return;
    }

    setChannelLabel('Голосовой помощник в браузере');
    setState('requesting_microphone');
    let createdSessionId: string | null = null;
    try {
      const session = await createVoiceSession(tenantId);
      createdSessionId = session.session_id;
        setSessionId(session.session_id);
        setSessionTenantId(tenantId);
        if (session.opening_greeting) {
          onTranscriptRef.current({
            id: `${session.session_id}:opening`,
            text: session.opening_greeting,
            final: true,
            role: 'assistant',
            turnId: `${session.session_id}:opening`,
          });
        }
        setState('connecting');
        const client = new VoiceWsClient({
        onState: setState,
        onTranscript: (event) => onTranscriptRef.current(event),
        onError: setNotice,
      });
      wsRef.current = client;
      await client.connect(session.session_id);
      setStartedAt(Date.now());
      setState('listening');
    } catch (error) {
      await wsRef.current?.disconnect().catch(() => undefined);
      wsRef.current = null;
      if (createdSessionId) {
        await endVoiceSession(createdSessionId).catch(() => undefined);
      }
      setSessionId(null);
      setSessionTenantId(null);
      setState('degraded');
      setNotice(
        error instanceof Error
          ? error.message
          : 'Не удалось подключить голос. Попробуйте ещё раз или напишите текстом.',
      );
    }
  }, [tenantId]);

  const stop = useCallback(async () => {
    setNotice(null);
    if (demoTimerRef.current !== null) { window.clearTimeout(demoTimerRef.current); demoTimerRef.current = null; }
    await liveKitRef.current?.disconnect().catch(() => undefined);
    liveKitRef.current = null;
    await wsRef.current?.disconnect().catch(() => undefined);
    wsRef.current = null;
    if (sessionId && !env.demoMode) {
      try {
        await endVoiceSession(sessionId);
      } catch {
        setNotice('Голос отключён, но API не подтвердил завершение сессии. Проверьте журнал backend.');
      }
    }
    setSessionId(null);
    setSessionTenantId(null);
    setStartedAt(null);
    setState('ended');
  }, [sessionId]);

  const switchToText = useCallback(async () => {
    setNotice(null);
    setTextPreferred(true);
    if (env.demoMode) {
      setState('degraded');
      return;
    }
    try {
      if (liveKitRef.current) await liveKitRef.current.setMicrophoneEnabled(false);
      if (wsRef.current) await wsRef.current.setMicrophoneEnabled(false);
      setState('degraded');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Не удалось отключить микрофон.');
      setState('degraded');
    }
  }, []);

  const resumeVoiceInput = useCallback(async (): Promise<boolean> => {
    setNotice(null);
    setTextPreferred(false);
    if (env.demoMode) {
      setState('listening');
      return true;
    }
    try {
      if (liveKitRef.current && sessionId) {
        await liveKitRef.current.setMicrophoneEnabled(true);
        setState('listening');
        return true;
      }
      if (wsRef.current && sessionId) {
        await wsRef.current.setMicrophoneEnabled(true);
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
    setSessionTenantId(null);
    setTextPreferred(false);
    setState('idle');
  }, []);

  useEffect(() => () => {
    if (demoTimerRef.current !== null) window.clearTimeout(demoTimerRef.current);
    void liveKitRef.current?.disconnect();
    void wsRef.current?.disconnect();
  }, []);

  return {
    state,
    notice,
    sessionId,
    sessionTenantId,
    textPreferred,
    startedAt,
    channelLabel,
    wsMock: wsVoiceConfigured,
    elapsedSeconds: startedAt ? Math.floor((clockNow - startedAt) / 1000) : 0,
    isConnected: state === 'listening' || state === 'processing' || state === 'speaking',
    start,
    stop,
    switchToText,
    resumeVoiceInput,
    reset,
  };
}
