// närbilder: node vyer3.js prefix '[["namn",[kx,kh,kz],[mx,mh,mz]], ...]'  (kamera/mål: x, höjd över mark, z; PORT, UT)
require('fs').mkdirSync(process.env.UT || '/tmp/epa-bilder', { recursive: true });
const { chromium } = require('playwright');
const pre = process.argv[2] || 'n';
const vyer = JSON.parse(process.argv[3]);
(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1300, height: 560 } });
  const logs = []; page.on('pageerror', e => logs.push(`[pageerror] ${e.message}`)); page.on('console', m => { if (m.type() === 'error') logs.push(m.text()); });
  await page.goto(`http://localhost:${process.env.PORT || 8772}/index.html?test`); await page.waitForSelector('#start.visa', { timeout: 120000 });
  await page.click("#startKnapp"); await page.waitForTimeout(2500); await page.waitForTimeout(300);
  for (const [n, p, l] of vyer) {
    await page.evaluate(([p, l]) => { const e = __epa; const hp = e.H(p[0], p[2]), hl = e.H(l[0], l[2]); e.camAt(p[0], hp + p[1], p[2], l[0], hl + l[1], l[2]); e.testStep(3); }, [p, l]);
    await page.waitForTimeout(800); await page.screenshot({ path: `${process.env.UT || '/tmp/epa-bilder'}/${pre}_${n}.png`, timeout: 120000 });
  }
  console.log(logs.join('\n') || 'inga fel'); await browser.close();
})();
