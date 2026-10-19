import { DashboardChart, DatasetTable, metricColor, periodLabel, persianText, SourceControls } from './dashboard-charts'
import type { SourceFilter } from './dashboard-types'
import type { QuestionAnswer } from './finance'

function exactValue(value: string): string {
  return /^-?\d+$/.test(value) ? new Intl.NumberFormat('fa-IR').format(BigInt(value)) : persianText(value)
}

export default function Dashboard({ answer, select }: { answer: QuestionAnswer; select: (filter: SourceFilter, title: string) => void }) {
  const spec = answer.spec
  if (answer.status !== 'answered' || !spec) return <section className="question-answer" aria-live="polite"><div className="answer-heading"><span className="section-kicker">محدودهٔ داده</span><h2>{answer.status === 'out_of_scope' ? 'این پرسش خارج از دادهٔ موجود است' : 'دادهٔ کافی در دسترس نیست'}</h2><p>{answer.message}</p></div>{answer.limitations.length > 0 && <ul className="dashboard-limitations">{answer.limitations.map(item => <li key={item}>{item}</li>)}</ul>}</section>
  return <section className="question-answer" aria-live="polite"><div className="answer-heading"><span className="section-kicker">تحلیل بر پایهٔ دادهٔ واقعی همین پایگاه نمایشی</span><h2>{persianText(spec.title)}</h2><p className="dashboard-answer">{persianText(spec.answer)}</p></div>
    <div className="dashboard-grid">{spec.layout.map(id => {
      const card = spec.cards.find(item => item.id === id)
      if (card) {
        const fact = answer.facts.find(item => item.id === card.fact_id)
        return fact ? <article className="answer-value dashboard-card" key={id} style={{ borderTopColor: metricColor(fact.metric) }}><span className="section-kicker">شاخص</span><h3>{persianText(card.title)}</h3><strong>{fact.value == null ? 'بدون داده' : persianText(fact.display)}</strong><span>{periodLabel(fact.period)}</span>{fact.comparison && <p className="fact-comparison">{persianText(fact.comparison)}</p>}{fact.definition && <details className="exact-value"><summary>تعریف شاخص</summary><span>{persianText(fact.definition)}</span></details>}{fact.raw_value && <details className="exact-value"><summary>{fact.unit.includes('تومان') ? 'مقدار دقیق' : 'مقدار محاسبه‌شده'}</summary><span>{exactValue(fact.raw_value)} {fact.unit.includes('تومان') ? 'تومان' : fact.unit}</span></details>}<SourceControls rows={[{ ...fact, label: card.title }]} select={select} /></article> : null
      }
      const chart = spec.charts.find(item => item.id === id)
      if (chart) {
        const dataset = answer.datasets.find(item => item.id === chart.dataset_id)
        return dataset ? <DashboardChart key={id} spec={chart} dataset={dataset} select={select} /> : null
      }
      const table = spec.tables.find(item => item.id === id)
      if (table) {
        const dataset = answer.datasets.find(item => item.id === table.dataset_id)
        return dataset ? <section key={id} className="report-section dashboard-table-panel"><div className="section-heading"><div><span className="section-kicker">جدول داده</span><h3>{persianText(table.title)}</h3><p>{dataset.periods.map(periodLabel).join(' · ')}</p></div></div>{dataset.coverage === 'complete' && dataset.rows.length ? <DatasetTable dataset={dataset} columns={table.columns} title={table.title} /> : <p className="empty">دادهٔ کافی برای جدول موجود نیست.</p>}<SourceControls rows={dataset.rows} select={select} /></section> : null
      }
      const insight = spec.insights.find(item => item.id === id)
      if (insight) {
        const facts = insight.fact_ids.map(factId => answer.facts.find(item => item.id === factId)).filter(item => item != null)
        return <aside key={id} className={`answer-insight dashboard-insight insight-${insight.kind}`}><span className="section-kicker">{insight.kind === 'positive' ? 'نقطهٔ قوت' : insight.kind === 'negative' ? 'نقطهٔ قابل بررسی' : 'مشاهدهٔ داده'}</span><h3>{persianText(insight.title)}</h3><p>{persianText(insight.text)}</p><div className="insight-facts">{facts.map(fact => <span key={fact.id}>{fact.label}: <b>{persianText(fact.display)}</b></span>)}</div><small>مبنای مقایسه: {persianText(insight.baseline)}</small><small>محدودهٔ اعتبار: {persianText(insight.scope)}</small><SourceControls rows={facts} select={select} /></aside>
      }
      return null
    })}</div>
    {answer.limitations.length > 0 && <aside className="dashboard-limitations"><span className="section-kicker">محدودیت‌های این تحلیل</span><ul>{answer.limitations.map(item => <li key={item}>{item}</li>)}</ul></aside>}
    <p className="answer-source">منبع: <bdi>{answer.dataset_id}</bdi> · نسخهٔ <bdi>{answer.dataset_version}</bdi> · دادهٔ ساختگی؛ واحد و دوره برای هر جزء جداگانه مشخص است.</p>
  </section>
}
