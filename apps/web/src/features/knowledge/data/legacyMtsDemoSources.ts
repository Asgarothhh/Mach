/**
 * Legacy corpus preserved from the previous MTS public-information prototype.
 * It is intentionally not imported into the default tenant experience. If enabled for regression,
 * mount it only under the isolated tenant id `mts-public-demo`.
 */
export const legacyMtsDemoTenant = {
  tenant_id: 'mts-public-demo',
  display_name: 'MTS Public Corpus · isolated regression fixture',
  sources: [
    { title: 'Помощь МТС', url: 'https://www.mts.by/help/' },
    { title: 'Перед поездкой', url: 'https://www.mts.by/services/roaming/pered-poezdkoy/' },
    { title: 'Помощь: роуминг', url: 'https://www.mts.by/help/rouming/' },
    { title: 'Контакты МТС', url: 'https://www.mts.by/company/comp/contact/' },
  ],
} as const;
