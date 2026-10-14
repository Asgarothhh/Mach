// Рендер макетов в PNG. Запуск: electron --no-sandbox shoot.js
const { app, BrowserWindow } = require('electron');
const fs = require('fs'), path = require('path');
app.disableHardwareAcceleration();
const pages = ['overview', 'calls', 'stub', 'scenarios', 'tokens'];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1440, height: 900, show: false, webPreferences: { offscreen: true } });
  for (const p of pages) {
    win.setContentSize(1440, 900); await sleep(300);
    await win.loadFile(path.join(__dirname, 'mockups', p + '.html'));
    await sleep(900);
    await win.webContents.insertCSS('html,body{overflow:hidden!important} ::-webkit-scrollbar{display:none}');
    const h = await win.webContents.executeJavaScript("Math.ceil((document.querySelector('.app')||document.body).getBoundingClientRect().height)");
    win.setContentSize(1440, Math.max(900, h)); await sleep(500);
    console.log('h', h);
    const img = await win.webContents.capturePage();
    fs.writeFileSync(path.join(__dirname, 'mockups', p + '.png'), img.toPNG());
    console.log('ok', p, img.getSize());
  }
  app.quit();
});
