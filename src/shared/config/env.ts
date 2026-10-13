function readBoolean(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined || value.trim() === '') return fallback;
  return value.toLowerCase() === 'true';
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

/**
 * Normalize the API origin/prefix so both of these work:
 *   http://127.0.0.1:8000
 *   http://127.0.0.1:8000/api/v1
 * Avoids accidental 404s when the local .env contains only the origin.
 */
function normalizeApiBaseUrl(value: string | undefined): string {
  const configured = trimTrailingSlash(
    value?.trim() || 'http://127.0.0.1:8000/api/v1',
  );
  if (/\/api\/v1$/i.test(configured)) return configured;
  return `${configured}/api/v1`;
}

/**
 * Only values that are safe to expose to the browser belong here.
 * Never add OPENROUTER_API_KEY, DB credentials, or LiveKit secrets.
 */
export const env = {
  appName: import.meta.env.VITE_APP_NAME?.trim() || 'MTS Voice Assistant',
  demoMode: readBoolean(import.meta.env.VITE_DEMO_MODE, true),
  backendTextTest: readBoolean(import.meta.env.VITE_BACKEND_TEXT_TEST, false),
  backendTestTenantId: import.meta.env.VITE_BACKEND_TEST_TENANT_ID?.trim() || 'demo-business-01',
  apiBaseUrl: normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL),
  liveKitUrl: import.meta.env.VITE_LIVEKIT_URL?.trim() || '',
} as const;

export const liveVoiceConfigured = !env.demoMode && env.liveKitUrl.length > 0;
