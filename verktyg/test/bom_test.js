// utkast 55: kan EPA:n köra på Torggatan väster om Thulegatan och uppför Platåvägen?
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 800, height: 500 } }); const logs = []; p.on('pageerror', e => logs.push(e.message));
  await p.goto('http://localhost:8772/index.html?test'); await p.waitForSelector('#start.visa', { timeout: 120000 }); await p.click('#startKnapp'); await p.waitForTimeout(500);
  const r = await p.evaluate(() => { const e = __epa; const s = e.car; const ut = [];
    for (const [x, z, mx, mz] of [[-560, 66, -598, 68], [-820, 172, -830, 186]]) { e.teleport(x, z); s.h = Math.atan2(mx - x, mz - z); s.v = 8; const x0 = s.x, z0 = s.z;
      for (let i = 0; i < 40; i++) { s.v = 8; e.testStep(3); } ut.push({ fran: [Math.round(x0), Math.round(z0)], till: [Math.round(s.x), Math.round(s.z)], km: Math.hypot(s.x - x0, s.z - z0).toFixed(0) }); }
    return ut; });
  console.log(JSON.stringify(r)); console.log(logs.join(' | ') || 'inga fel'); await b.close();
})();
