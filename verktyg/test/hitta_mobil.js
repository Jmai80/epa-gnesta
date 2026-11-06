// Hitta på mobil (utkast 48): liggande och stående iPhone, tryck Hitta, skriv, välj mål, skärmbilder
const { chromium, devices } = require('playwright');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const logs = [];
  for (const [enhet, pre] of [['iPhone 13 landscape', 'mobL'], ['iPhone 13', 'mobS']]) {
    const ctx = await b.newContext({ ...devices[enhet], deviceScaleFactor: 1 }); const p = await ctx.newPage();
    p.on('pageerror', e => logs.push(e.message)); p.on('console', m => { if (m.type() === 'error') logs.push(m.text()); });
    await p.goto('http://localhost:8772/index.html?test'); await p.waitForSelector('#start.visa', { timeout: 120000 }); await p.tap('#startKnapp'); await p.waitForTimeout(1500);
    await p.tap('#btnHitta'); await p.waitForTimeout(300); await p.keyboard.type('sam'); await p.waitForTimeout(300);
    await p.screenshot({ path: `/tmp/epa-bilder/hitta_${pre}_sok.png`, timeout: 120000 });
    await p.tap('#hittaLista .traff'); await p.evaluate(() => __epa.testStep(2)); await p.waitForTimeout(300);
    await p.screenshot({ path: `/tmp/epa-bilder/hitta_${pre}_mal.png`, timeout: 120000 });
    console.log(enhet, await p.evaluate(() => document.getElementById('mal').innerText.replace(/\n/g, ' | ')));
    await ctx.close();
  }
  console.log(logs.join(' | ') || 'inga fel'); await b.close();
})();
