// kör autopilot längs en körbar rutt: node test/autopilot3.js <ruttindex> <sekunder>
const { chromium } = require('playwright');
const ri = +(process.argv[2] || 2), sek = +(process.argv[3] || 300);
(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 640, height: 400 } });
  const logs = []; page.on('pageerror', e => logs.push(e.message)); page.on('console', m => { if (m.type() === 'error') logs.push(m.text()); });
  await page.goto(`http://localhost:${process.env.PORT || 8772}/index.html?test`); await page.waitForSelector('#start.visa', { timeout: 120000 }); await page.click('#startKnapp');
  const res = await page.evaluate(([ri, sek]) => {
    const E = window.__epa; const routes = E.drivable.filter(d => !d.stub); const route = routes[ri].pts;
    E.teleport(route[2].x, route[2].z, Math.atan2(route[3].x - route[2].x, route[3].z - route[2].z));
    window.__preUpdate = () => { const c = E.car; let bi = 0, bd = 1e9; for (let i = 0; i < route.length; i++) { const d = Math.hypot(route[i].x - c.x, route[i].z - c.z); if (d < bd) { bd = d; bi = i; } }
      const t = route[Math.min(route.length - 1, bi + 4)]; const want = Math.atan2(t.x - c.x, t.z - c.z); let dh = want - c.h; while (dh > Math.PI) dh -= 2 * Math.PI; while (dh < -Math.PI) dh += 2 * Math.PI;
      E.keys.up = true; E.keys.left = dh > 0.04; E.keys.right = dh < -0.04; };
    const prog = []; for (let k = 0; k < sek; k++) { E.testStep(60); const c = E.car; if (k % 10 === 0) prog.push([Math.round(c.x), Math.round(c.z), Math.round(c.v * 3.6), Math.round(c.y)]); }
    window.__preUpdate = null; E.keys.up = false; const end = route[route.length - 1]; const c = E.car;
    return { antal: routes.length, langd: route.length, prog, slut: [Math.round(end.x), Math.round(end.z)], bil: [Math.round(c.x), Math.round(c.z)] };
  }, [ri, sek]);
  console.log(JSON.stringify(res)); console.log(logs.join('\n') || 'inga fel'); await browser.close();
})();
