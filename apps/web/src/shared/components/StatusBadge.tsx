import type { ReactNode } from 'react';

type Tone = 'neutral' | 'success' | 'danger' | 'warning' | 'demo';
export function StatusBadge({ children, tone = 'neutral', dot = false }: { children: ReactNode; tone?: Tone; dot?: boolean }) {
  return <span className={`status-badge status-badge--${tone}`}>{dot && <span className="status-badge__dot" aria-hidden="true" />}{children}</span>;
}
