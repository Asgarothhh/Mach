import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import type { TenantProfile } from '../../../shared/types/track1';
import { env } from '../../../shared/config/env';
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
    env.demoMode || tenant.tenant_id === 'acme-it-demo' || tenant.tenant_id === 'mts-public-demo'
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
      resetBackendTextSession();
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
