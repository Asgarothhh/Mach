import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { LocaleProvider } from '../shared/i18n/LocaleContext';
import { VoiceExperienceProvider } from '../features/voice/model/VoiceExperienceContext';
import { TenantProvider } from '../features/tenant/model/TenantContext';
import { PublicLayout } from './layouts/PublicLayout';
import { HomePage } from '../features/home/pages/HomePage';
import { OnboardingPage } from '../features/onboarding/pages/OnboardingPage';
import { CallHistoryPage } from '../features/calls/pages/CallHistoryPage';
import { CallDetailPage } from '../features/calls/pages/CallDetailPage';
import { ScenarioEditorPage } from '../features/scenarios/pages/ScenarioEditorPage';
import { PermissionPage } from '../features/voice/pages/PermissionPage';
import { ConnectingPage } from '../features/voice/pages/ConnectingPage';
import { ConversationPage } from '../features/voice/pages/ConversationPage';
import { TextModePage } from '../features/voice/pages/TextModePage';
import { EndedPage } from '../features/voice/pages/EndedPage';
import { AdminLayout } from '../features/admin/components/AdminLayout';
import { AdminOverviewPage } from '../features/admin/pages/AdminOverviewPage';
import { AdminSessionsPage } from '../features/admin/pages/AdminSessionsPage';
import { AdminSessionDetailPage } from '../features/admin/pages/AdminSessionDetailPage';
import { RagInspectorPage } from '../features/admin/pages/RagInspectorPage';
import { KnowledgePage } from '../features/admin/pages/KnowledgePage';
import { IngestionPage } from '../features/admin/pages/IngestionPage';
import { QualityPage } from '../features/admin/pages/QualityPage';
import { ConfigurationPage } from '../features/admin/pages/ConfigurationPage';
import { AuditPage } from '../features/admin/pages/AuditPage';
import { EvaluationsPage } from '../features/admin/pages/EvaluationsPage';

export function App() {
  return (
    <BrowserRouter>
      <LocaleProvider>
        <TenantProvider>
          <VoiceExperienceProvider>
            <Routes>
              <Route element={<PublicLayout />}>
                <Route path="/" element={<HomePage />} />
                <Route path="/onboarding" element={<OnboardingPage />} />
                <Route path="/calls" element={<CallHistoryPage />} />
                <Route path="/calls/:callId" element={<CallDetailPage />} />
                <Route path="/scenarios" element={<ScenarioEditorPage />} />
                <Route path="/voice/permission" element={<PermissionPage />} />
                <Route path="/voice/connecting" element={<ConnectingPage />} />
                <Route path="/voice/live" element={<ConversationPage />} />
                <Route path="/text" element={<TextModePage />} />
                <Route path="/ended" element={<EndedPage />} />
              </Route>
              <Route path="/admin" element={<AdminLayout />}>
                <Route index element={<AdminOverviewPage />} />
                <Route path="sessions" element={<AdminSessionsPage />} />
                <Route path="sessions/:sessionId" element={<AdminSessionDetailPage />} />
                <Route path="calls" element={<CallHistoryPage />} />
                <Route path="calls/:callId" element={<CallDetailPage />} />
                <Route path="scenarios" element={<ScenarioEditorPage />} />
                <Route path="rag" element={<RagInspectorPage />} />
                <Route path="knowledge" element={<KnowledgePage />} />
                <Route path="sync" element={<IngestionPage />} />
                <Route path="quality" element={<QualityPage />} />
                <Route path="configuration" element={<ConfigurationPage />} />
                <Route path="audit" element={<AuditPage />} />
                <Route path="evaluations" element={<EvaluationsPage />} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </VoiceExperienceProvider>
        </TenantProvider>
      </LocaleProvider>
    </BrowserRouter>
  );
}
