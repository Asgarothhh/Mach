import { Link } from 'react-router-dom';

export function Brand({ compact = false, admin = false }: { compact?: boolean; admin?: boolean }) {
  return (
    <Link className={`brand ${compact ? 'brand--compact' : ''} ${admin ? 'brand--admin' : ''}`} to="/" aria-label="МТС — ИИ-агент звонков, на главную">
      <span className="brand__mark" aria-hidden="true"><span className="brand__drop" />МТС</span>
      {!compact && <span className="brand__title">ИИ-агент звонков</span>}
    </Link>
  );
}
