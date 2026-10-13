import { ArrowUpRight, FileText } from 'lucide-react';
import type { SourceCitation } from '../types/api';

export function SourceCard({ source, compact = false }: { source: SourceCitation; compact?: boolean }) {
  return (
    <article className={`source-card ${compact ? 'source-card--compact' : ''}`}>
      <div className="source-card__icon"><FileText size={17} /></div>
      <div className="source-card__body">
        <div className="source-card__heading"><strong>{source.title}</strong><ArrowUpRight size={15} aria-hidden="true" /></div>
        <a href={source.url} target="_blank" rel="noopener noreferrer">{source.url}</a>
        {source.excerpt && <p className="source-card__excerpt">{source.excerpt}</p>}
        <span className="source-card__meta">{source.crawledAt ? `Демо-проверка: ${source.crawledAt}` : 'Публичный источник · версия не указана'}{source.revisionId ? ` · ${source.revisionId}` : ''}</span>
      </div>
    </article>
  );
}
