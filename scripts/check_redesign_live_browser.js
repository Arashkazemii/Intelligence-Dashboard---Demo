async page => {
  // Explicit live-model browser checks. No mocked response enters this run.
  const questions = ['داشبورد بده', 'داشبورد حمل بده', 'نقاط قوت و ضعف را نشان بده', 'درآمد فصل سوم چقدر بود؟'];
  const index = await page.evaluate(() => window.__viraQaIndex || 0);
  if (index >= questions.length) throw new Error('All four live questions already checked. Reload #question to restart.');
  const errors = [];
  const onError = error => errors.push(error.message);
  page.on('pageerror', onError);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByLabel('پرسش فارسی', { exact: true }).fill(questions[index]);
  const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/demo-finance/question') && response.request().method() === 'POST', { timeout: 130000 });
  await page.getByRole('button', { name: 'تحلیل پرسش', exact: true }).click();
  await page.locator('.generation-state').waitFor();
  if (index === 0) await page.screenshot({ path: 'artifacts/after-loading.png' });
  const response = await responsePromise;
  const body = await response.json();
  if (!response.ok() || body.status !== 'answered' || !body.spec) throw new Error(JSON.stringify({ http: response.status(), status: body.status, detail: body.detail }));
  await page.locator('.question-answer').waitFor({ timeout: 15000 });
  await page.evaluate(({ index, body }) => { const answers = JSON.parse(sessionStorage.getItem('vira-qa-answers') || '{}'); answers[index] = body; sessionStorage.setItem('vira-qa-answers', JSON.stringify(answers)); }, { index, body });
  await page.evaluate(() => document.fonts.ready);
  // Inspect the same charts over time; final screenshots follow the internal reveal.
  const startMarks = await page.locator('.recharts-line-curve,.recharts-area-area,.recharts-rectangle,.recharts-sector').count();
  await page.waitForTimeout(1300);
  const result = { question: questions[index], http: response.status(), status: body.status, cards: body.spec.cards.length, charts: body.spec.charts.map(chart => chart.type), insights: body.spec.insights.length, viewports: [], source: null };
  for (const [name, width, height] of [['desktop', 1440, 1000], ['tablet', 834, 1112], ['mobile', 390, 844]]) {
    await page.setViewportSize({ width, height });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(250);
    const layout = await page.evaluate(() => ({ width: innerWidth, documentWidth: document.documentElement.scrollWidth, charts: [...document.querySelectorAll('.dashboard-chart-canvas')].map(node => Math.round(node.getBoundingClientRect().width)), marks: document.querySelectorAll('.recharts-line-curve,.recharts-area-area,.recharts-rectangle,.recharts-sector,.recharts-radar-polygon').length }));
    if (layout.documentWidth > width || layout.charts.some(value => value < 230) || (body.spec.charts.length > 0 && layout.marks === 0)) throw new Error(JSON.stringify({ name, ...layout }));
    await page.screenshot({ path: `artifacts/after-live-${index + 1}-${name}.png`, fullPage: true });
    if (index === 0 && name === 'mobile') await page.locator('.dashboard-chart').first().screenshot({ path: 'artifacts/after-chart-mobile.png' });
    if (index === 0 && name === 'desktop') await page.screenshot({ path: 'artifacts/after-workspace-desktop.png' });
    result.viewports.push({ name, ...layout });
  }
  if (index === 1) {
    await page.setViewportSize({ width: 1440, height: 1000 });
    const sourceToggle = page.locator('.dashboard-sources .disclosure-toggle').first();
    await sourceToggle.click();
    const sourceRequest = page.waitForResponse(response => response.url().includes('/api/demo-finance/lines?'));
    await page.locator('.dashboard-source-row button').first().click();
    const lines = await (await sourceRequest).json();
    await page.locator('.reconciled').waitFor();
    if (!lines.lines?.length) throw new Error('Expected actual ledger source rows');
    result.source = { rows: lines.lines.length, reconciled: true };
    await page.locator('.detail-panel').screenshot({ path: 'artifacts/after-source-rows.png' });
    await page.getByRole('button', { name: 'بستن جزئیات', exact: true }).click();
    await page.locator('.detail-panel').waitFor({ state: 'detached' });
  }
  result.startMarks = startMarks;
  result.pageErrors = errors;
  await page.evaluate(value => { window.__viraQaIndex = value; }, index + 1);
  page.off('pageerror', onError);
  if (errors.length) throw new Error(JSON.stringify(errors));
  return result;
}
