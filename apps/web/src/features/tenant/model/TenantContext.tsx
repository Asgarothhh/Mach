import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import type { TenantProfile } from '../../../shared/types/track1';
import { env, isLiveTenant } from '../../../shared/config/env';
import { resetBackendTextSession } from '../../chat/services/backendTextTest.service';
import { defaultDemoTenant, listDemoTenants, registerDemoTenant } from '../data/demoTenants';

interface TenantContextValue {
  tenantId: string;
  tenantName: string;
  setActiveTenant: (tenantId: string, tenantName: string) => void;
  registerTenant: (tenant: TenantProfile) => void;
  availableTenants: TenantProfile[];
}

const TenantContext = createContext<TenantContextValue | null>(null);

/** Stores only a demo selection in memory. Authentication and tenant authorization belong to the backend. */
export function TenantProvider({ children }: { children: ReactNode }) {
  const initialTenants = listDemoTenants().filter((tenant) => (
    env.demoMode || isLiveTenant(tenant.tenant_id)
  ));
  const [tenantId, setTenantId] = useState(env.backendTestTenantId || defaultDemoTenant.tenant_id);
  const [tenantName, setTenantName] = useState(
    initialTenants.find((item) => item.tenant_id === (env.backendTestTenantId || defaultDemoTenant.tenant_id))?.display_name
    || defaultDemoTenant.display_name,
  );
  const [availableTenants, setAvailableTenants] = useState<TenantProfile[]>(() => initialTenants);
  const value = useMemo<TenantContextValue>(() => ({
    tenantId,
    tenantName,
    availableTenants,
    setActiveTenant: (nextId, nextName) => {
      // Live sessions only start for backend-known tenants (404 tenant_not_available otherwise).
      if (!env.demoMode && !isLiveTenant(nextId)) return;
      resetBackendTextSession();
      setTenantId(nextId);
      setTenantName(nextName);
    },
    registerTenant: (tenant) => {
      if (env.demoMode) registerDemoTenant(tenant);
      // Fixture-only tenants stay out of the live switcher: the Stage-1 backend does not know them.
      if (!env.demoMode && !isLiveTenant(tenant.tenant_id)) return;
      setAvailableTenants((current) => [tenant, ...current.filter((item) => item.tenant_id !== tenant.tenant_id)]);
    },
  }), [tenantId, tenantName, availableTenants]);

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

export function useTenant() {
  const value = useContext(TenantContext);
  if (!value) throw new Error('useTenant must be used inside TenantProvider.');
  return value;
}
