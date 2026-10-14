import test from 'node:test';
import assert from 'node:assert/strict';
import { formatElapsed } from '../src/shared/lib/formatElapsed.ts';
import { mapAnswerEventCitations } from '../src/shared/lib/mapAnswerEventCitations.ts';
import { pluralRu } from '../src/shared/lib/pluralRu.ts';
import { userFacingApiMessage } from '../src/shared/lib/userFacingApiMessage.ts';

test('formatElapsed pads minutes and seconds', () => {
  assert.equal(formatElapsed(81), '01:21');
  assert.equal(formatElapsed(0), '00:00');
  assert.equal(formatElapsed(5), '00:05');
  assert.equal(formatElapsed(3600), '60:00');
});

test('pluralRu picks Russian inflections', () => {
  assert.equal(pluralRu(1, 'ход', 'хода', 'ходов'), 'ход');
  assert.equal(pluralRu(2, 'ход', 'хода', 'ходов'), 'хода');
  assert.equal(pluralRu(5, 'ход', 'хода', 'ходов'), 'ходов');
  assert.equal(pluralRu(21, 'сообщение', 'сообщения', 'сообщений'), 'сообщение');
  assert.equal(pluralRu(11, 'сообщение', 'сообщения', 'сообщений'), 'сообщений');
});

test('userFacingApiMessage hides 429 and 5xx details', () => {
  assert.equal(
    userFacingApiMessage(429, 'Rate limit exceeded for key xyz'),
    'Слишком много запросов. Подождите немного и попробуйте снова.',
  );
  assert.equal(
    userFacingApiMessage(503, 'traceback'),
    'Сервис временно недоступен. Попробуйте позже.',
  );
  assert.match(userFacingApiMessage(404, 'Session not found'), /не найдена|недоступна|Session not found/i);
});

test('mapAnswerEventCitations uses SourceRef field names', () => {
  const citations = mapAnswerEventCitations({
    sources: [
      {
        chunk_id: 'acme-hours-1',
        title: 'График офиса',
        canonical_url: 'https://acme-it.example/hours',
        excerpt: 'Пн–Пт 9:00–18:00',
      },
      { id: 'legacy', url: 'https://example.com' },
    ],
  });
  assert.equal(citations.length, 1);
  assert.deepEqual(citations[0], {
    id: 'acme-hours-1',
    title: 'График офиса',
    url: 'https://acme-it.example/hours',
    excerpt: 'Пн–Пт 9:00–18:00',
  });
});
