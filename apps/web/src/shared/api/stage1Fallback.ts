import { env } from '../config/env';
import { ApiError } from './http';

/**
 * Stage-1 demo stand gap: the control-plane routes (`/tenants`,
 * `/tenants/{id}/onboarding/validate`, `/tenants/{id}/test-calls`,
 * `/tenants/{id}/scenarios*`) are not implemented by the Stage-1 backend yet —
 * `docs/runbook.md` §7 keeps those screens in demo/disabled. In the hosted build
 * (`VITE_DEMO_MODE=false`) such screens would otherwise answer with a raw 404.
 *
 * Two guards, in order:
 *   1. a cached capability probe of the published OpenAPI schema ("must be
 *      confirmed against backend OpenAPI" from the service contracts) — so no
 *      failing request is made at all while the routes are missing;
 *   2. a 404 fallback on the call itself, in case the probe is unavailable.
 *
 * Only a missing route (404) degrades to demo fixtures. Business errors
 * (400/403/409/422), server errors (5xx) and network failures propagate.
 */
export function isRouteNotImplemented(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

type OpenApiSchema = {
  paths?: Record<string, unknown>;
};

function apiOrigin(): string {
  return env.apiBaseUrl.replace(/\/api\/v1$/, '');
}

let controlPlaneProbe: Promise<boolean> | null = null;

/** True when the backend publishes the Track-1 control-plane routes. Result is cached per page load. */
export function stage1ControlPlaneAvailable(): Promise<boolean> {
  controlPlaneProbe ??= fetch(`${apiOrigin()}/openapi.json`, { headers: { Accept: 'application/json' } })
    .then((response) => (response.ok ? (response.json() as Promise<OpenApiSchema>) : null))
    .then((schema) => Boolean(schema && schema.paths && '/api/v1/tenants' in schema.paths))
    .catch(() => true);
  return controlPlaneProbe;
}

export type DemoFallbackSource = 'api' | 'local';

export async function withDemoFallbackSource<T>(
  apiCall: () => Promise<T>,
  demoCall: () => T | Promise<T>,
): Promise<{ value: T; source: DemoFallbackSource }> {
  if (!(await stage1ControlPlaneAvailable())) {
    return { value: await demoCall(), source: 'local' };
  }
  try {
    return { value: await apiCall(), source: 'api' };
  } catch (error) {
    if (!isRouteNotImplemented(error)) throw error;
    return { value: await demoCall(), source: 'local' };
  }
}

export async function withDemoFallback<T>(
  apiCall: () => Promise<T>,
  demoCall: () => T | Promise<T>,
): Promise<T> {
  const { value } = await withDemoFallbackSource(apiCall, demoCall);
  return value;
}
