import { Building2, ChevronDown } from 'lucide-react';
import { useTenant } from '../../features/tenant/model/TenantContext';

/** UI convenience only. Backend identity/RBAC remains the authorization boundary. */
export function TenantSwitcher() {
  const { tenantId, availableTenants, setActiveTenant } = useTenant();
  if (availableTenants.length === 0) return null;

  return (
    <label className="tenant-switcher" title="Выбранный tenant не является механизмом авторизации">
      <Building2 size={14} aria-hidden="true" />
      <span className="sr-only">Активный профиль компании</span>
      <select
        value={tenantId}
        aria-label="Активный профиль компании"
        onChange={(event) => {
          const tenant = availableTenants.find((item) => item.tenant_id === event.target.value);
          if (tenant) setActiveTenant(tenant.tenant_id, tenant.display_name);
        }}
      >
        {availableTenants.map((tenant) => (
          <option key={tenant.tenant_id} value={tenant.tenant_id}>{tenant.display_name}</option>
        ))}
      </select>
      <ChevronDown size={13} aria-hidden="true" />
    </label>
  );
}
