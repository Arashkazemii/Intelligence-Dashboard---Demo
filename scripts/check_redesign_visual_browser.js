async page => {
  // Replay the four actual provider responses captured by the live-browser check.
  // This final visual pass makes no additional model calls.
  const captured = JSON.parse(await page.evaluate(() => sessionStorage.getItem('vira-qa-answers') || '{}'));
  if ([0, 1, 2, 3].some(index => !captured[index]?.spec)) throw new Error('Run all four live questions before final visual replay');
  const errors = [];
  const onError = error => errors.push(error.message);
  page.on('pageerror', onError);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  const results = [];
  const questions = ['داشبورد بده', 'داشبورد حمل بده', 'نقاط قوت و ضعف را نشان بده', 'درآمد فصل سوم چقدر بود؟'];
  let chartMotion;
  for (const index of [0, 1, 2, 3]) {
    await page.unroute('**/api/demo-finance/question');
    await page.route('**/api/demo-finance/question', route => route.fulfill({ json: captured[index] }));
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`http://127.0.0.1:8081/?visual=${index}-${Date.now()}#question`);
    await page.getByLabel('پرسش فارسی', { exact: true }).fill(questions[index]);
    await page.getByRole('button', { name: 'تحلیل پرسش', exact: true }).click();
    await page.locator('.question-answer').waitFor();
    if (index === 0) {
      const mask = page.locator('mask[id$="-reveal-mask"] rect').first();
      await mask.waitFor({ state: 'attached' });
      const first = await mask.evaluate(node => node.outerHTML);
      await page.waitForTimeout(300);
      const second = await mask.evaluate(node => node.outerHTML);
      chartMotion = { first, second, changed: first !== second };
      if (!chartMotion.changed) throw new Error(`Expected internal chart reveal over time: ${JSON.stringify(chartMotion)}`);
    }
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(1300);
    for (const [name, width, height] of [['desktop', 1440, 1000], ['tablet', 834, 1112], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(250);
      const layout = await page.evaluate(() => ({ width: innerWidth, documentWidth: document.documentElement.scrollWidth, hiddenInsights: [...document.querySelectorAll('.dashboard-insight')].filter(node => Number(getComputedStyle(node).opacity) < .99).length }));
      if (layout.documentWidth > width || layout.hiddenInsights) throw new Error(JSON.stringify({ index, name, ...layout }));
      await page.screenshot({ path: `artifacts/after-live-${index + 1}-${name}.png`, fullPage: true });
      if (index === 0 && name === 'desktop') await page.screenshot({ path: 'artifacts/after-workspace-desktop.png' });
      if (index === 0 && name === 'mobile') await page.locator('.dashboard-chart').first().screenshot({ path: 'artifacts/after-chart-mobile.png' });
      results.push({ index, name, ...layout });
    }
    if (index === 0) {
      await page.setViewportSize({ width: 1440, height: 1000 });
      const canvas = page.locator('.dashboard-chart-canvas').first();
      await canvas.evaluate(node => { node.dataset.qaIdentity = 'preserved'; });
      await page.getByLabel('پرسش فارسی', { exact: true }).fill('تغییر متن بدون ارسال');
      await page.locator('.dashboard-data .disclosure-toggle').first().click();
      if (await canvas.getAttribute('data-qa-identity') !== 'preserved') throw new Error('Typing or disclosure remounted chart');
      await page.locator('.dashboard-data .disclosure-toggle').first().click();
      const box = await canvas.boundingBox();
      await canvas.hover({ position: { x: box.width * .55, y: box.height * .45 } });
      await page.locator('.dashboard-tooltip').first().waitFor();
      await page.locator('.dashboard-chart').first().screenshot({ path: 'artifacts/after-tooltip.png' });
    }
  }
  await page.unroute('**/api/demo-finance/question');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`http://127.0.0.1:8081/?sample-report=${Date.now()}#report`);
  await page.locator('.metric-card').first().waitFor();
  await page.locator('.report-header a[href="#trend"]').click();
  await page.locator('#trend').waitFor();
  if (await page.locator('.report').count() !== 1) throw new Error('Report section navigation changed route');
  await page.getByRole('button', { name: 'جزئیات درآمد فصل دوم', exact: true }).click();
  await page.locator('.reconciled').waitFor();
  await page.getByRole('button', { name: 'بستن جزئیات', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Sample report mobile overflow');
  await page.screenshot({ path: 'artifacts/after-report-mobile.png', fullPage: true });
  await page.goto(`http://127.0.0.1:8081/?landing-qa=${Date.now()}`);
  await page.locator('.preview-metric').first().waitFor();
  for (const [name, width, height] of [['desktop', 1440, 1000], ['reference-size', 1189, 753], ['tablet', 834, 1112], ['mobile', 390, 844]]) {
    await page.setViewportSize({ width, height });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(350);
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error(`Landing overflow: ${name}`);
    await page.screenshot({ path: `artifacts/after-landing-${name}.png`, fullPage: name === 'mobile' || name === 'tablet' });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('link', { name: 'نگاهی به محصول', exact: true }).click();
  if (await page.locator('.landing').count() !== 1) throw new Error('Preview anchor changed route');
  await page.getByRole('button', { name: 'شروع', exact: true }).click();
  await page.locator('.chat-panel').waitFor();
  await page.locator('.skip-link').focus();
  await page.keyboard.press('Enter');
  if (await page.locator('.workspace').count() !== 1) throw new Error('Workspace skip link changed route');
  await page.getByRole('button', { name: 'صفحهٔ شروع', exact: true }).click();
  await page.locator('.landing').waitFor();
  page.off('pageerror', onError);
  if (errors.length) throw new Error(JSON.stringify(errors));
  return { replayedLiveResponses: results, chartMotion, chartIdentityPreserved: true, tooltip: 'passed', sampleReportSource: 'passed', anchorNavigation: 'passed', pageErrors: errors };
}
