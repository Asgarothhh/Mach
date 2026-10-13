import { useCallback, useEffect, useState } from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { checkBackendHealth, type BackendHealthStatus } from '../services/adminSessions.service';

export function BackendHealthIndicator() {
  const [health, setHealth] = useState<BackendHealthStatus | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setHealth(await checkBackendHealth());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const tone = health?.live && health.ready ? 'success' : health && (!health.live || !health.ready) ? 'danger' : 'neutral';
  const label = !health ? 'Проверка API…' : health.live && health.ready ? 'API готов' : !health.live ? 'API недоступен' : 'API не готов';

  return (
    <span className="backend-health-indicator" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }} title={`Liveness: ${health?.live ? 'OK' : health ? 'ERROR' : '…'} · Readiness: ${health?.ready ? 'OK' : health ? 'ERROR' : '…'}`}>
      <StatusBadge tone={tone} dot><Activity size={12} /> {label}</StatusBadge>
      <button type="button" className="button button--secondary button--small" onClick={() => void refresh()} disabled={loading} aria-label="Проверить состояние backend"><RefreshCw size={12} /></button>
    </span>
  );
}
