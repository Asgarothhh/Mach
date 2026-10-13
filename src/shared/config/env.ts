function readBoolean(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined || value.trim() === '') return fallback;
  return value.toLowerCase() === 'true';
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

/**
 * Только значения, которые разрешено видеть браузеру.
 * НИКОГДА не добавляйте сюда OPENROUTER_API_KEY, DB credentials или LiveKit secret.
 */
export const env = {
  appName: import.meta.env.VITE_APP_NAME?.trim() || 'MTS Voice Assistant',
  demoMode: readBoolean(import.meta.env.VITE_DEMO_MODE, true),
  backendTextTest: readBoolean(import.meta.env.VITE_BACKEND_TEXT_TEST, false),
  // Allows the admin session list/detail/actions to use the current backend contract
  // while the remaining product areas stay in demo mode.
  backendAdminSessions: readBoolean(import.meta.env.VITE_BACKEND_ADMIN_SESSIONS, false),
  backendTestTenantId: import.meta.env.VITE_BACKEND_TEST_TENANT_ID?.trim() || 'demo-business-01',
  apiBaseUrl: trimTrailingSlash(
    import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
  ),
  liveKitUrl: import.meta.env.VITE_LIVEKIT_URL?.trim() || '',
} as const;

export const liveVoiceConfigured = !env.demoMode && env.liveKitUrl.length > 0;
