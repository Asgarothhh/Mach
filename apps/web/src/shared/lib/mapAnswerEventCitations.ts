import type { SourceCitation } from '../types/api';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Map AnswerEvent.sources using SourceRef field names onto SourceCitation. */
export function mapAnswerEventCitations(payload: Record<string, unknown>): SourceCitation[] {
  const raw = payload.sources;
  if (!Array.isArray(raw)) return [];
  const citations: SourceCitation[] = [];
  for (const item of raw) {
    if (!isRecord(item)) continue;
    const chunkId = item.chunk_id;
    const url = item.canonical_url;
    if (typeof chunkId !== 'string' || typeof url !== 'string' || !chunkId || !url) continue;
    const title = item.title;
    citations.push({
      id: chunkId,
      title: typeof title === 'string' && title ? title : chunkId,
      url,
      ...(typeof item.excerpt === 'string' ? { excerpt: item.excerpt } : {}),
    });
  }
  return citations;
}
