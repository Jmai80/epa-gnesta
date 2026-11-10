// väderbilder: node vader_test.js prefix '[["namn","regn",0], ["namn","sno",[kx,kh,kz],[mx,mh,mz]], ...]'
// tredje värdet är kameraläget (0 bakom, 1 förare, 2 drönare) eller en fri kamera som i vyer3.js. BIL='x,z,h' flyttar bilen. (PORT, UT)
require('fs').mkdirSync(process.env.UT || '/tmp/epa-bilder', { recursive: true });
const { chromium } = require('playwright');
const pre = process.argv[2] || 'v';
const vyer = JSON.parse(process.argv[3] || '[["regn","regn",0]]');
(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1300, height: 560 } });
  const logs = []; page.on('pageerror', e => logs.push(`[pageerror] ${e.message}`)); page.on('console', m => { if (m.type() === 'error') logs.push(m.text()); });
  await page.goto(`http://localhost:${process.env.PORT || 8772}/index.html?test`); await page.waitForSelector('#start.visa', { timeout: 120000 });
  await page.click('#startKnapp'); await page.waitForTimeout(2500);
  const bil = process.env.BIL ? process.env.BIL.split(',').map(Number) : null;
  for (const [n, typ, kam, mal] of vyer) {
    const info = await page.evaluate(([typ, kam, mal, bil]) => { const e = __epa; if (bil) e.teleport(bil[0], bil[1], bil[2]);
      e.sattVader(typ, true);
      if (Array.isArray(kam)) { const hp = e.H(kam[0], kam[2]), hl = e.H(mal[0], mal[2]); e.camAt(kam[0], hp + kam[1], kam[2], mal[0], hl + mal[1], mal[2]); } else e.setCam(kam);
      e.testStep(45); return { typ: e.vader.typ, regn: e.vader.nu.regn, sno: e.vader.nu.sno, snoT: e.vader.snoT, vat: e.vader.vat, bil: [e.car.x, e.car.z, e.car.h] }; }, [typ, kam, mal, bil]);
    await page.waitForTimeout(600); await page.screenshot({ path: `${process.env.UT || '/tmp/epa-bilder'}/${pre}_${n}.png`, timeout: 120000 });
    console.log(n, JSON.stringify(info));
  }
  console.log(logs.join('\n') || 'inga fel'); await browser.close();
})();
