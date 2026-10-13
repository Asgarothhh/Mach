import type { ReactNode } from 'react';
import { ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { StatusBadge } from '../../../shared/components/StatusBadge';

export function MetricCard({
  label,
  value,
  detail,
  icon,
  tone = 'default',
}: {
  label: string;
  value: string;
  detail: string;
  icon: ReactNode;
  tone?: 'default' | 'red' | 'green' | 'amber';
}) {
  return (
    <article className={`metric-card metric-card--${tone}`}>
      <div className="metric-card__top"><span>{label}</span><span className="metric-card__icon">{icon}</span></div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

export function AdminPanel({
  title,
  eyebrow,
  action,
  children,
  className = '',
}: {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`admin-panel ${className}`}>
      <div className="admin-panel__heading">
        <div>{eyebrow && <span className="section-eyebrow">{eyebrow}</span>}<h2>{title}</h2></div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function TableStatus({ value }: { value: string }) {
  const lower = value.toLowerCase();
  const tone = lower.includes('handoff')
    ? 'warning'
    : lower.includes('error') || lower.includes('failed') || lower.includes('ошиб')
      ? 'danger'
      : lower.includes('актив') || lower.includes('success') || lower.includes('заверш') || lower.includes('grounded')
        ? 'success'
        : 'neutral';
  return <StatusBadge tone={tone}>{value}</StatusBadge>;
}

export function ViewSessionLink({ sessionId }: { sessionId: string }) {
  return (
    <Link className="table-action-link" to={`/admin/sessions/${encodeURIComponent(sessionId)}`}>
      Детали <ArrowUpRight size={13} />
    </Link>
  );
}
