async page => {
  // Run through playwright-cli run-code. Fixture server is local and read only.
  const fixture = await (await fetch('http://127.0.0.1:8765/chart-fixture.json')).json();
  const failures = [];
  page.on('pageerror', error => failures.push(error.message));
  const results = [];
  for (const [index, response] of fixture.pages.entries()) {
    await page.unroute('**/api/demo-finance/question');
    await page.route('**/api/demo-finance/question', route => route.fulfill({ json: response }));
    for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.goto(`http://127.0.0.1:8081/?renderer-check=${index}-${name}-${Date.now()}#question`);
      await page.getByLabel('پرسش فارسی', { exact: true }).fill('آزمون نمودارهای معتبر');
      await page.getByRole('button', { name: 'تحلیل پرسش', exact: true }).click();
      await page.locator('[data-chart-type]').first().waitFor();
      await page.evaluate(() => document.fonts.ready);
      await page.locator('[data-chart-type]').last().scrollIntoViewIfNeeded();
      await page.evaluate(() => window.scrollTo(0, 0));
      const charts = await page.locator('[data-chart-type]').evaluateAll(nodes => nodes.map(node => ({
        type: node.getAttribute('data-chart-type'),
        svg: node.querySelectorAll('svg.recharts-surface').length,
        marks: node.querySelectorAll('.recharts-line-curve,.recharts-area-area,.recharts-rectangle,.recharts-sector:not(.recharts-radial-bar-background-sector),.recharts-radar-polygon').length,
        width: Math.round(node.getBoundingClientRect().width),
      })));
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      if (charts.length !== 6 || charts.some(chart => !chart.svg || !chart.marks) || overflow) {
        throw new Error(JSON.stringify({ index, name, charts, overflow }));
      }
      await page.screenshot({ path: `artifacts/dashboard-v2-registry-${index + 1}-${name}.png`, fullPage: true });
      results.push({ index, viewport: name, charts, overflow });
    }
  }
  await page.unroute('**/api/demo-finance/question');
  if (failures.length) throw new Error(JSON.stringify(failures));
  return { results, pageErrors: failures };
}
