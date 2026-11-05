// testar hastighetsvisaren: bilen körs mot skylten i 25 och 60 km/h, skärmbild från sidan
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 1300, height: 560 } }); const logs = []; p.on('pageerror', e => logs.push(e.message));
  await p.goto('http://localhost:8772/index.html?test'); await p.waitForSelector('#start.visa', { timeout: 120000 }); await p.click('#startKnapp'); await p.waitForTimeout(2000);
  const ut = [];
  for (const [kmh, namn] of [[25, 'glad'], [60, 'arg']]) {
    if (kmh > 30) { await p.keyboard.press('u'); await p.waitForTimeout(200); }
    const r = await p.evaluate(([kmh]) => { const e = __epa; const s = e.car; const f = e.fartskyltar[0];
      // 45 m före skylten på vägen, riktad mot den, i jämn fart
      const d = [0.609, 0.793]; s.x = 532.2 - d[0] * 55; s.z = 198.5 - d[1] * 55; s.h = Math.atan2(d[0], d[1]); s.v = kmh / 3.6;
      e.setCam(0); e.testStep(15); s.v = kmh / 3.6; e.testStep(2);
      return { lage: f.lage, kmh: Math.round(s.v * 3.6), x: Math.round(s.x), z: Math.round(s.z) }; }, [kmh]); console.log('mätt', JSON.stringify(r));
    await p.evaluate(() => { const e = __epa; const f = e.fartskyltar[0]; const H = e.H(f.x, f.z); e.camAt(f.x + f.nx * 4.5 - f.nz * 1.5, H + 2.6, f.z + f.nz * 4.5 + f.nx * 1.5, f.x, H + 2.6, f.z); e.fartskyltar[0].t = 0; e.testStep(1); });
    await p.waitForTimeout(800); await p.screenshot({ path: `/tmp/epa-bilder/fart_${namn}.png`, timeout: 120000 }); console.log(JSON.stringify(r)); ut.push({ kmh, ...r });
  }
  console.log(JSON.stringify(ut), logs.join(' | ') || 'inga fel'); await b.close();
})();
