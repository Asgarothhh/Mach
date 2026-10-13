import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

export type Locale = 'ru' | 'be';
type LocaleContextValue = { locale: Locale; setLocale: (locale: Locale) => void };
const LocaleContext = createContext<LocaleContextValue | null>(null);

function readInitialLocale(): Locale {
  try { return localStorage.getItem('mts-ui-locale') === 'be' ? 'be' : 'ru'; }
  catch { return 'ru'; }
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readInitialLocale);
  const setLocale = (next: Locale) => {
    setLocaleState(next);
    try { localStorage.setItem('mts-ui-locale', next); } catch { /* Storage is optional. */ }
  };
  const value = useMemo(() => ({ locale, setLocale }), [locale]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const value = useContext(LocaleContext);
  if (!value) throw new Error('useLocale must be used inside LocaleProvider.');
  return value;
}
