// kontrollerar att vädret växlar av sig självt, att övertoningen går mjukt och att blixten syns: node vader_auto.js  (PORT, UT)
require('fs').mkdirSync(process.env.UT || '/tmp/epa-bilder', { recursive: true });
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1300, height: 560 } });
  const logs = []; page.on('pageerror', e => logs.push(`[pageerror] ${e.message}`)); page.on('console', m => { if (m.type() === 'error') logs.push(m.text()); });
  await page.goto(`http://localhost:${process.env.PORT || 8772}/index.html?test`); await page.waitForSelector('#start.visa', { timeout: 120000 });
  await page.click('#startKnapp'); await page.waitForTimeout(2500);
  const r = await page.evaluate(() => { const e = __epa, v = e.vader; const ut = []; v.auto = true; v.kvar = 0.5;
    for (let i = 0; i < 12; i++) { e.testStep(30, 1 / 3); ut.push(`${v.typ} regn ${v.nu.regn.toFixed(2)} snö ${v.nu.sno.toFixed(2)} täcke ${v.snoT.toFixed(2)} väta ${v.vat.toFixed(2)} dis ${v.nu.dis.toFixed(4)}`); v.kvar = 0.1; }
    v.auto = false; e.sattVader('skyfall', true); e.setCam(0); e.testStep(20); v.nastaBlixt = 0; e.testStep(2); ut.push('blixt ' + v.blixt.toFixed(2)); return ut; });
  await page.waitForTimeout(500); await page.screenshot({ path: `${process.env.UT || '/tmp/epa-bilder'}/auto_blixt.png`, timeout: 120000 });
  await page.keyboard.press('KeyV'); const knapp = await page.textContent('#btnVader');
  console.log(r.join('\n')); console.log('knapp efter V:', knapp); console.log(logs.join('\n') || 'inga fel'); await browser.close();
})();
