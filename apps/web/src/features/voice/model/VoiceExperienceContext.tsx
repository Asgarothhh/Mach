import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useConversation } from './useConversation';
import { useVoiceSession } from './useVoiceSession';

const VoiceExperienceContext = createContext<ReturnType<typeof useExperienceValue> | null>(null);

function useExperienceValue() {
  const conversation = useConversation();
  const voice = useVoiceSession({ onTranscript: conversation.upsertTranscript });
  return { conversation, voice };
}

export function VoiceExperienceProvider({ children }: { children: ReactNode }) {
  const value = useExperienceValue();
  const stableValue = useMemo(() => value, [value.conversation, value.voice]);
  return <VoiceExperienceContext.Provider value={stableValue}>{children}</VoiceExperienceContext.Provider>;
}

export function useVoiceExperience() {
  const value = useContext(VoiceExperienceContext);
  if (!value) throw new Error('useVoiceExperience must be used inside VoiceExperienceProvider.');
  return value;
}
