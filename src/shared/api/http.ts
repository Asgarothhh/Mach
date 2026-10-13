import { env } from '../config/env';

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
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
    throw new ApiError('Не удалось связаться с API. Проверьте сервер и адрес VITE_API_BASE_URL.', 0, 'NETWORK_ERROR');
  }

  if (!response.ok) {
    // Do not surface raw provider responses, stack traces, or request bodies in the UI.
    let code: string | undefined;
    try {
      const payload = (await response.json()) as { code?: unknown };
      if (typeof payload.code === 'string') code = payload.code;
    } catch {
      // A server can return an empty/non-JSON error response.
    }
    throw new ApiError(`API вернул ошибку (${response.status}).`, response.status, code);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
