// söker på adresser i Hitta och väljer den första träffen: node adress_test.js '["Torggatan 11","Torggatan 13"]'  (PORT, UT)
const { chromium } = require('playwright');
const sok = JSON.parse(process.argv[2] || '["Torggatan 11"]');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 1300, height: 560 } }); const logs = []; p.on('pageerror', e => logs.push('[pageerror] ' + e.message)); p.on('console', m => { if (m.type() === 'error') logs.push(m.text()); });
  await p.goto(`http://localhost:${process.env.PORT || 8772}/index.html?test`); await p.waitForSelector('#start.visa', { timeout: 120000 }); await p.click('#startKnapp'); await p.waitForTimeout(1500);
  for (const q of sok) { const r = await p.evaluate((q) => { const t = __epa.hittaSok(q); return t.slice(0, 3).map(e => `${e.titel} (${e.under}) x ${Math.round(e.x)}, z ${Math.round(e.z)}`); }, q); console.log(q, '→', r.join(' | ') || 'ingen träff'); }
  await p.keyboard.press('KeyF'); await p.waitForTimeout(300); await p.keyboard.type(sok[0]); await p.waitForTimeout(500);
  await p.screenshot({ path: `${process.env.UT || '/tmp/epa-bilder'}/adress_sok.png`, timeout: 120000 });
  console.log(logs.join('\n') || 'inga fel'); await b.close();
})();
