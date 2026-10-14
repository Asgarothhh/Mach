// Общая оболочка концепта: рейка, верхняя панель, иконки. Только для макетов.
const P = {
  gauge: '<path d="m12 14 4-4"/><path d="M3.3 19a10 10 0 1 1 17.4 0"/>',
  phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/>',
  route: '<circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/>',
  book: '<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  sliders: '<path d="M21 4h-7M10 4H3M21 12h-9M8 12H3M21 20h-5M12 20H3M14 2v4M8 10v4M16 18v4"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.7 9a1 1 0 0 1-.6 0C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.2-2.7a1.2 1.2 0 0 1 1.6 0C14.5 3.8 17 5 19 5a1 1 0 0 1 1 1z"/>',
  check: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
  db: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
  chart: '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="m19 9-5 5-4-4-3 3"/>',
  plus: '<path d="M5 12h14M12 5v14"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.8 9.8 0 0 1 6.7 2.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.8 9.8 0 0 1-6.7-2.7L3 16"/><path d="M8 16H3v5"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
  cal: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  alert: '<path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3z"/><path d="M12 9v4M12 17h.01"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  play: '<path d="M6 3l14 9-14 9z"/>',
  arrow: '<path d="M5 12h14M13 5l7 7-7 7"/>',
};
function icon(n) { return `<svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round">${P[n]}</svg>`; }
function nav(active, soonOn = true) {
  const items = [
    ['gauge', 'Обзор', 'overview'], ['phone', 'Звонки', 'calls', '12'], ['route', 'Сценарии', 'scen'],
    ['book', 'Источники знаний', 'know'], ['chart', 'Качество', 'quality'],
  ];
  const sys = [['sliders', 'Конфигурация', 'cfg'], ['shield', 'Аудит', 'audit'], ['db', 'Синхронизация', 'sync', 'скоро'], ['check', 'Оценка моделей', 'eval', 'скоро']];
  const row = ([i, t, k, x]) => `<a class="${k === active ? 'on' : ''} ${x === 'скоро' ? 'dim' : ''}">${icon(i)}${t}${x === 'скоро' ? '<span class="soon">скоро</span>' : x ? `<span class="cnt">${x}</span>` : ''}</a>`;
  return `<div class="nav">${items.map(row).join('')}<div class="grp">Система</div>${sys.map(row).join('')}</div>`;
}
function shell(active, crumb, body) {
  if (!document.body) document.documentElement.appendChild(document.createElement('body'));
  document.body.innerHTML = `<div class="app"><aside class="rail">
    <div class="brand"><b>МТС</b><span>Голосовой<br>помощник</span></div>
    <div class="tenant"><i>A</i><div><strong>Acme IT</strong><small>demo-стенд</small></div></div>
    ${nav(active)}
    <div class="rail-foot"><span class="dot"></span> Сервис работает</div>
  </aside><div class="main"><div class="top"><div class="crumbs">Админка / <b>${crumb}</b></div>
  <div class="r"><span class="muted">Europe/Minsk</span><span class="avatar">VA</span></div></div>${body}</div></div>`;
}
