// fördelning av geometri och ritanrop: node test/fordelning.js port
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-precise-memory-info'] });
  const page = await browser.newPage({ viewport: { width: 900, height: 500 } });
  await page.goto(`http://localhost:${process.argv[2] || 8772}/index.html?test`); await page.waitForSelector('#start.visa', { timeout: 180000 });
  await page.click('#startKnapp'); await page.waitForTimeout(1500);
  const r = await page.evaluate(() => { const E = __epa; let inst = 0, instVert = 0, instMesh = 0, statVert = 0, stor = [];
    E.scene.traverse(o => { if (!o.isMesh || !o.geometry) return; const n = o.geometry.attributes.position.count;
      if (o.isInstancedMesh) { instMesh++; inst = Math.max(inst, 0); instVert += n * o.count; } else { statVert += n; stor.push(n); } });
    stor.sort((a, b) => b - a);
    E.testStep(2); const info = E.renderer.info.render;
    return { statiskaVertiser: statVert, bilVertiserPerBild: instVert, bilMeshar: instMesh, storstaMeshar: stor.slice(0, 8), ritanrop: info.calls, trianglar: info.triangles, heapMB: Math.round(performance.memory.usedJSHeapSize / 1e6) }; });
  console.log(JSON.stringify(r)); await browser.close();
})();
