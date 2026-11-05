// avgasröken: bilen gasar iväg från starten, skärmbild snett bakifrån; sedan tomgång
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 1300, height: 560 } }); const logs = []; p.on('pageerror', e => logs.push(e.message)); p.on('console', m => { if (m.type() === 'error') logs.push(m.text()); });
  await p.goto(`http://localhost:${process.env.PORT || 8772}/index.html?test`); await p.waitForSelector('#start.visa', { timeout: 120000 }); await p.click('#startKnapp'); await p.waitForTimeout(2000);
  for (const [namn, gas] of [['gas', true], ['tomgang', false]]) {
    await p.evaluate(([gas]) => { const e = __epa; const s = e.car; e.keys.up = gas; if (!gas) { s.v = 0; } e.testStep(45);
      const fx = Math.sin(s.h), fz = Math.cos(s.h), lx = Math.cos(s.h), lz = -Math.sin(s.h); const y = e.H(s.x, s.z);
      e.camAt(s.x - fx * 4.2 + lx * 2.6, y + 1.6, s.z - fz * 4.2 + lz * 2.6, s.x - fx * 2.2, y + 0.6, s.z - fz * 2.2); e.testStep(1); }, [gas]);
    await p.waitForTimeout(800); await p.screenshot({ path: `/tmp/epa-bilder/rok_${namn}.png`, timeout: 120000 });
  }
  console.log(logs.join(' | ') || 'inga fel'); await b.close();
})();
