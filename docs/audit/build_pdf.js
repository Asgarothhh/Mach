// Сборка PDF из report.html и PNG-превью страниц. Запуск: electron --no-sandbox build_pdf.js
const { app, BrowserWindow } = require('electron');
const fs = require('fs'), path = require('path');
app.disableHardwareAcceleration();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1280, height: 720, show: false, webPreferences: { offscreen: true } });
  await win.loadFile(path.join(__dirname, 'report.html'));
  await sleep(2000);
  const pdf = await win.webContents.printToPDF({ pageSize: { width: 1280 / 96, height: 720 / 96 }, printBackground: true, margins: { marginType: 'none' } });
  fs.writeFileSync(path.join(__dirname, 'UI_AUDIT_CONCEPT.pdf'), pdf);
  // превью каждого слайда
  const n = await win.webContents.executeJavaScript('document.querySelectorAll(".slide").length');
  win.setContentSize(1280, 720);
  for (let i = 0; i < n; i++) {
    await win.webContents.executeJavaScript(`window.scrollTo(0, ${i * 720})`); await sleep(300);
    const img = await win.webContents.capturePage();
    fs.writeFileSync(`/tmp/audit/slide${i + 1}.png`, img.toPNG());
  }
  console.log('slides', n);
  app.quit();
});
