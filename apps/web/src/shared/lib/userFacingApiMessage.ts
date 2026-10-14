/** User-facing copy for API failures. Does not echo internal details for 429/5xx. */
export function userFacingApiMessage(status: number, detail?: string): string {
  if (status === 429) {
    return 'Слишком много запросов. Подождите немного и попробуйте снова.';
  }
  if (status >= 500) {
    return 'Сервис временно недоступен. Попробуйте позже.';
  }
  if (status === 404) {
    return detail?.trim() || 'Запись не найдена или недоступна.';
  }
  if (status === 401) {
    return 'Нет доступа. Войдите или откройте демо-стенд с ENVIRONMENT=demo.';
  }
  if (status === 403) {
    return 'Нет доступа к этой компании.';
  }
  if (detail?.trim()) return detail.trim();
  if (status <= 0) {
    return 'Не удалось связаться с сервисом. Проверьте соединение.';
  }
  return `Не удалось выполнить запрос (${status}).`;
}
