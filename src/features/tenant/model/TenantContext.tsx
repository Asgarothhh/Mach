import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import type { TenantProfile } from '../../../shared/types/track1';
import { env } from '../../../shared/config/env';
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
  const [tenantId, setTenantId] = useState(env.demoMode ? defaultDemoTenant.tenant_id : '');
  const [tenantName, setTenantName] = useState(env.demoMode ? defaultDemoTenant.display_name : 'Выберите компанию');
  const [availableTenants, setAvailableTenants] = useState<TenantProfile[]>(() => env.demoMode ? listDemoTenants() : []);
  const value = useMemo<TenantContextValue>(() => ({
    tenantId,
    tenantName,
    availableTenants,
    setActiveTenant: (nextId, nextName) => {
      setTenantId(nextId);
      setTenantName(nextName);
    },
    registerTenant: (tenant) => {
      if (env.demoMode) registerDemoTenant(tenant);
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
