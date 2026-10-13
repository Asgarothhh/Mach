import { env } from '../config/env';

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
    public readonly method?: string,
    public readonly path?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
}

/** Shared HTTP entry point. Keep endpoint paths and response mapping in feature services. */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = `${env.apiBaseUrl}${path.startsWith('/') ? path : `/${path}`}`;
  const method = (options.method || (options.body === undefined ? 'GET' : 'POST')).toUpperCase();
  let pathname = path;
  try {
    pathname = new URL(url).pathname;
  } catch {
    // The fetch call below will return the more useful network error.
  }

  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');

  let body: BodyInit | undefined;
  if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json');
    body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(url, { ...options, headers, body });
  } catch {
    throw new ApiError(
      `Не удалось связаться с API (${method} ${pathname}). Проверьте сервер и VITE_API_BASE_URL.`,
      0,
      'NETWORK_ERROR',
      method,
      pathname,
    );
  }

  if (!response.ok) {
    let code: string | undefined;
    let detail: string | undefined;
    try {
      const payload = (await response.json()) as { code?: unknown; detail?: unknown; message?: unknown };
      if (typeof payload.code === 'string') code = payload.code;
      if (typeof payload.detail === 'string') detail = payload.detail;
      else if (typeof payload.message === 'string') detail = payload.message;
    } catch {
      // A server can return an empty/non-JSON error response.
    }
    const suffix = detail ? ` ${detail}` : '';
    throw new ApiError(
      `API вернул ошибку (${response.status}) для ${method} ${pathname}.${suffix}`,
      response.status,
      code,
      method,
      pathname,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
