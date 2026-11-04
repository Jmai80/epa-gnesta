// mäter minne och geometri efter laddning: node test/minne.js port
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-precise-memory-info', '--js-flags=--expose-gc'] });
  const { devices } = require('playwright'); const page = process.env.ENHET ? await (await browser.newContext({ ...devices[process.env.ENHET], deviceScaleFactor: 1 })).newPage() : await browser.newPage({ viewport: { width: 900, height: 500 } });
  const logs = []; page.on('pageerror', e => logs.push(`[pageerror] ${e.message}`));
  // toppminne under laddningen: prova var 100:e ms
  await page.addInitScript(() => { window.__topp = 0; setInterval(() => { if (performance.memory) window.__topp = Math.max(window.__topp, performance.memory.usedJSHeapSize); }, 50); });
  const t0 = Date.now();
  await page.goto(`http://localhost:${process.argv[2] || 8772}/index.html?test`); await page.waitForSelector('#start.visa', { timeout: 180000 });
  const ms = Date.now() - t0;
  const r = await page.evaluate(() => { const E = window.__epa; let v = 0, meshes = 0, tex = new Set(), texPx = 0; const per = {};
    E.scene.traverse(o => { if (o.isMesh && o.geometry) { const n = o.geometry.attributes.position.count; v += n; meshes++; const m = o.material; if (m && m.map && m.map.source && !tex.has(m.map.source.uuid)) { tex.add(m.map.source.uuid); const im = m.map.image; if (im) texPx += (im.width || 0) * (im.height || 0); } } });
    if (window.gc) window.gc();
    return { vertiser: v, meshar: meshes, texturkallor: tex.size, texturMpx: +(texPx / 1e6).toFixed(1), heapMB: +(performance.memory.usedJSHeapSize / 1e6).toFixed(0), toppMB: +(window.__topp / 1e6).toFixed(0), gl: E.renderer.info.memory };
  });
  console.log(JSON.stringify({ ms, ...r })); if (logs.length) console.log(logs.join('\n')); await browser.close();
})();
