// rena bilder utan HUD: node test/ogbild.js prefix '[[namn,[cx,cy,cz],[lx,ly,lz],[bilx,bilz,bilh]]]'
require('fs').mkdirSync(process.env.UT || '/tmp/epa-bilder', { recursive: true });
const { chromium } = require('playwright');
const pre = process.argv[2] || 'og'; const vyer = JSON.parse(process.argv[3]);
(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: +(process.env.DSF || 1) });
  const logs = []; page.on('pageerror', e => logs.push(`[pageerror] ${e.message}`));
  await page.goto(`http://localhost:${process.env.PORT || 8772}/index.html?test`); await page.waitForSelector('#start.visa', { timeout: 120000 });
  await page.click('#startKnapp'); await page.waitForTimeout(2500);
  await page.addStyleTag({ content: '#hud, #etiketter, .touchpad { display: none !important; }' });
  for (const [n, p, l, b] of vyer) {
    await page.evaluate(([p, l, b]) => { const e = __epa; if (b) { e.teleport(b[0], b[1], b[2]); e.testStep(2); } const hp = e.H(p[0], p[2]), hl = e.H(l[0], l[2]); e.camAt(p[0], hp + p[1], p[2], l[0], hl + l[1], l[2]); e.testStep(3); }, [p, l, b]);
    await page.waitForTimeout(900); await page.screenshot({ path: `${process.env.UT || '/tmp/epa-bilder'}/${pre}_${n}.png`, timeout: 120000 });
  }
  console.log(logs.join('\n') || 'inga fel'); await browser.close();
})();
