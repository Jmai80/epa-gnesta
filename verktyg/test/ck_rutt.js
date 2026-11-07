const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 800, height: 500 } }); const logs = []; p.on('pageerror', e => logs.push(e.message));
  await p.goto('http://localhost:8772/index.html?test'); await p.waitForSelector('#start.visa', { timeout: 120000 }); await p.click('#startKnapp'); await p.waitForTimeout(500);
  console.log(await p.evaluate(() => { const e = __epa; const t = e.hittaSok('circle')[0]; const r = e.natRutt(t, false);
    return JSON.stringify({ traff: e.hittaSok('circle k').slice(0, 3).map(x => x.titel + ' / ' + x.under), L: Math.round(r.L), fri: Math.round(r.fri), n: r.pts.length }); }));
  console.log(logs.join(' | ') || 'inga fel'); await b.close();
})();
