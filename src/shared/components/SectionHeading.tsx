import type { ReactNode } from 'react';

export function SectionHeading({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="section-heading">
      <div>{eyebrow && <div className="section-eyebrow">{eyebrow}</div>}<h1>{title}</h1>{description && <p>{description}</p>}</div>
      {action && <div className="section-heading__action">{action}</div>}
    </div>
  );
}
