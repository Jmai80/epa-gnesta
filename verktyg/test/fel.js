const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage(); const logs = [];
  p.on('console', m => { if (m.type() === 'error' || m.type() === 'log') logs.push(`[${m.type()}] ${m.text()}`); }); p.on('pageerror', e => logs.push('pageerror ' + e.message + '\n' + (e.stack || '').split('\n').slice(0, 4).join('\n')));
  await p.goto(`http://localhost:${process.argv[2] || 8772}/index.html?test`); await p.waitForTimeout(40000);
  console.log(logs.slice(0, 10).join('\n') || 'inga fel'); await b.close();
})();
