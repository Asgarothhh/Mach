/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DEMO_MODE?: string;
  readonly VITE_BACKEND_TEXT_TEST?: string;
  readonly VITE_BACKEND_TEST_TENANT_ID?: string;
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_LIVEKIT_URL?: string;
  readonly VITE_APP_NAME?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
