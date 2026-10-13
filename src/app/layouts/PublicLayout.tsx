import { useLocation, Outlet } from 'react-router-dom';
import { Headphones, Info } from 'lucide-react';
import { AppFooter } from '../../shared/components/AppFooter';
import { AppHeader } from '../../shared/components/AppHeader';

export function PublicLayout() {
  const location = useLocation();
  const isBrowserTest = location.pathname.startsWith('/voice/') || location.pathname === '/text' || location.pathname === '/ended';
  return <div className="public-shell"><AppHeader />{isBrowserTest && <div className="track-test-mode-banner"><Headphones size={16} /><div><strong>Browser test console</strong><span>Это проверка микрофона/WebRTC. Основной продуктовый канал — входящий телефонный звонок через SIP/VoIP или помеченный mock adapter.</span></div><Info size={16} /></div>}<main className="public-main"><Outlet /></main><AppFooter /></div>;
}
