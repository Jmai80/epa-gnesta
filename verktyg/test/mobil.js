// mobiltest: iPhone liggande, ratt + pedaler; vrider ratten med en simulerad tumme och läser av styrningen
require('fs').mkdirSync(process.env.UT || '/tmp/epa-bilder', { recursive: true });
const { chromium, devices } = require('playwright');
(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const dev = devices[process.env.ENHET || 'iPhone 13 landscape'];
  const ctx = await browser.newContext({ ...dev, deviceScaleFactor: 1 }); const page = await ctx.newPage();
  const logs = []; page.on('pageerror', e => logs.push(`[pageerror] ${e.message}`)); page.on('console', m => { if (m.type() === 'error') logs.push(m.text()); });
  await page.goto(`http://localhost:${process.env.PORT || 8772}/index.html?test`); await page.waitForSelector('#start.visa', { timeout: 120000 });
  await page.tap('#startKnapp'); await page.waitForTimeout(2500); await page.evaluate(() => __epa.testStep(3));
  const pre = process.env.PRE || 'mob';
  await page.screenshot({ path: `${process.env.UT || '/tmp/epa-bilder'}/${pre}_1_vila.png`, timeout: 120000 });
  const r = await page.locator('#ratt').boundingBox();
  const res = {};
  if (r) {
    const cx = r.x + r.width / 2, cy = r.y + r.height / 2, R = r.width * 0.42;
    // dra tummen medurs från klockan 12 till klockan 3 via pekhändelser
    const cdp = await ctx.newCDPSession(page);
    const pt = (a) => ({ x: cx + Math.cos(a) * R, y: cy + Math.sin(a) * R, id: 1 });
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [pt(-Math.PI / 2)] });
    for (let k = 1; k <= 12; k++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [pt(-Math.PI / 2 + k / 12 * Math.PI / 2)] });
    // håll gaspedalen samtidigt med en andra tumme
    const g = await page.locator('#tGas').boundingBox();
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [pt(0), { x: g.x + g.width / 2, y: g.y + g.height / 2, id: 2 }] });
    await page.evaluate(() => __epa.testStep(30));
    res.medan = await page.evaluate(() => ({ vinkel: +__epa.ratt.vinkel.toFixed(3), held: __epa.ratt.held, styr: +__epa.car.steer.toFixed(3), fart: +__epa.car.v.toFixed(2) }));
    await page.screenshot({ path: `${process.env.UT || '/tmp/epa-bilder'}/${pre}_2_vrid.png`, timeout: 120000 });
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await page.evaluate(() => __epa.testStep(40));
    res.efter = await page.evaluate(() => ({ vinkel: +__epa.ratt.vinkel.toFixed(3), held: __epa.ratt.held, styr: +__epa.car.steer.toFixed(3) }));
  }
  res.layout = await page.evaluate(() => { const b = (s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return r.width ? [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] : 'dold'; };
    return { ratt: b('#ratt'), pilar: b('#tvLeft'), pedaler: b('#tvRight'), mini: b('.mini'), matare: b('.matare'), knappar: b('.knappar'), vw: innerWidth, vh: innerHeight }; });
  console.log(JSON.stringify(res)); console.log(logs.join('\n') || 'inga fel'); await browser.close();
})();
