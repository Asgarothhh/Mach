import { createContext, useContext, useEffect, useMemo, useRef, type ReactNode } from 'react';
import { resetBackendTextSession } from '../../chat/services/backendTextTest.service';
import { useTenant } from '../../tenant/model/TenantContext';
import { useConversation } from './useConversation';
import { useVoiceSession } from './useVoiceSession';

const VoiceExperienceContext = createContext<ReturnType<typeof useExperienceValue> | null>(null);

function useExperienceValue() {
  const { tenantId } = useTenant();
  const conversation = useConversation();
  const voice = useVoiceSession({ onTranscript: conversation.upsertTranscript });
  const previousTenant = useRef(tenantId);

  useEffect(() => {
    if (previousTenant.current === tenantId) return;
    previousTenant.current = tenantId;
    void voice.stop();
    conversation.clearConversation();
    void resetBackendTextSession();
  }, [tenantId, voice, conversation]);

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
