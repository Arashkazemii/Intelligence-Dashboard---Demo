async page => {
  // Replay outputs captured from the real provider; no synthetic analysis here.
  const cases = [
    ['overview', 'live-final/overview.json'], ['management', 'live/management.json'],
    ['shipping', 'live-final/shipping.json'], ['strengths', 'live/strengths.json'],
    ['revenue', 'live/revenue.json'], ['compare', 'live/compare.json'],
    ['unavailable', 'live/unavailable.json'], ['bridge', 'live-repair/bridge.json'],
  ];
  const results = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  for (const [key, path] of cases) {
    const response = await (await fetch(`http://127.0.0.1:8765/${path}`)).json();
    await page.unroute('**/api/demo-finance/question');
    await page.route('**/api/demo-finance/question', route => route.fulfill({ json: response }));
    for (const [viewport, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.goto(`http://127.0.0.1:8081/?sample=${key}-${viewport}-${Date.now()}#question`);
      await page.getByLabel('پرسش فارسی', { exact: true }).fill(key === 'shipping' ? 'داشبورد حمل بده' : 'بررسی پاسخ ثبت‌شده');
      await page.getByRole('button', { name: 'تحلیل پرسش', exact: true }).click();
      await page.locator('.question-answer').waitFor();
      const chartCount = await page.locator('[data-chart-type]').count();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      const expected = response.spec?.charts.length ?? 0;
      if (chartCount !== expected || overflow || await page.locator('.state-notice').count()) {
        throw new Error(JSON.stringify({ key, viewport, chartCount, expected, overflow }));
      }
      if (['management', 'overview', 'strengths'].includes(key)) {
        await page.screenshot({ path: `artifacts/dashboard-v2-${key}-${viewport}.png`, fullPage: true });
      }
      results.push({ key, viewport, status: response.status, chartCount, overflow });
    }
  }
  await page.unroute('**/api/demo-finance/question');
  if (errors.length) throw new Error(JSON.stringify(errors));
  return { results, pageErrors: errors };
}
