import { EvilLineChart } from './components/evilcharts/charts/recharts-line-chart'
import { EvilBarChart } from './components/evilcharts/charts/recharts-bar-chart'
import { EvilPieChart } from './components/evilcharts/charts/recharts-pie-chart'
import type { ChartConfig } from './components/evilcharts/ui/recharts-chart'
import { billions, fa, metricLabels, monthLabels, type Expense, type FinanceReport, type Metric } from './finance'

const palette: Record<Metric, string> = { revenue: 'var(--metric-revenue)', cogs: 'var(--metric-cogs)', opex: 'var(--metric-opex)', operating_profit: 'var(--metric-profit)' }
const metrics: Metric[] = ['revenue', 'cogs', 'opex', 'operating_profit']
const config = Object.fromEntries(metrics.map(key => [key, { label: metricLabels[key], colors: { dark: [palette[key]], light: [palette[key]] } }])) as ChartConfig
const tick = (value: number) => fa.format(value)

export function TrendChart({ report, onMonth, selectedMetrics = metrics }: { report: FinanceReport; onMonth: (month: string) => void; selectedMetrics?: Metric[] }) {
  const data: Record<string, unknown>[] = report.monthly_trend.map(item => ({ month: monthLabels[item.month] ?? item.month, monthKey: item.month, ...Object.fromEntries(selectedMetrics.map(key => [key, billions(item.values[key]?.amount_toman)])) }))
  if (!data.length) return <p className="empty">داده‌ای برای روند شش ماه موجود نیست.</p>
  return <div className="chart-wrap"><span className="sr-only">روند ماهانهٔ {selectedMetrics.map(key => metricLabels[key]).join(' و ')}؛ واحد میلیارد تومان ساختگی</span>
    <EvilLineChart data={data} config={config} animationType="left-to-right" chartProps={{ margin: { top: 12, right: 16, bottom: 0, left: 0 } }}>
      <EvilLineChart.Grid stroke="var(--chart-grid)" />
      <EvilLineChart.XAxis dataKey="month" tick={{ fill: 'var(--chart-label)', fontSize: 12 }} />
      <EvilLineChart.YAxis tickFormatter={tick} tick={{ fill: 'var(--chart-label)', fontSize: 12 }} width={38} />
      <EvilLineChart.Tooltip />
      {selectedMetrics.map(key => <EvilLineChart.Line key={key} dataKey={key} strokeWidth={key === 'operating_profit' ? 3 : 2} />)}
    </EvilLineChart>
    <div className="chart-legend">{selectedMetrics.map(key => <span key={key}><i style={{ background: palette[key] }} />{metricLabels[key]}</span>)}</div>
    <div className="month-actions" aria-label="نمایش سطرهای ماه"><span>جزئیات ماه:</span>{report.monthly_trend.map(item => <button key={item.month} type="button" onClick={() => onMonth(item.month)}>{monthLabels[item.month]}</button>)}</div>
  </div>
}

export function ComparisonChart({ report, selectedMetrics = metrics }: { report: FinanceReport; selectedMetrics?: Metric[] }) {
  const data: Record<string, unknown>[] = [
    { quarter: 'فصل دوم', ...Object.fromEntries(selectedMetrics.map(key => [key, billions(report.quarters.q2.values[key]?.amount_toman)])) },
    { quarter: 'فصل سوم', ...Object.fromEntries(selectedMetrics.map(key => [key, billions(report.quarters.q3.values[key]?.amount_toman)])) },
  ]
  return <div className="chart-wrap" role="img" aria-label={`مقایسهٔ ${selectedMetrics.map(key => metricLabels[key]).join(' و ')} در فصل دوم و سوم؛ واحد میلیارد تومان ساختگی`}>
    <EvilBarChart data={data} config={config} chartProps={{ margin: { top: 8, right: 8, bottom: 0, left: 0 } }}>
      <EvilBarChart.Grid stroke="var(--chart-grid)" />
      <EvilBarChart.XAxis dataKey="quarter" tick={{ fill: 'var(--chart-label)', fontSize: 12 }} interval={0} />
      <EvilBarChart.YAxis tickFormatter={tick} tick={{ fill: 'var(--chart-label)', fontSize: 12 }} width={38} />
      <EvilBarChart.Tooltip />
      {selectedMetrics.map(key => <EvilBarChart.Bar key={key} dataKey={key} radius={4} animationType="none" />)}
    </EvilBarChart>
    <div className="chart-legend">{selectedMetrics.map(key => <span key={key}><i style={{ background: palette[key] }} />{metricLabels[key]}</span>)}</div>
  </div>
}

export function ExpenseDonut({ items, onSelect }: { items: Expense[]; onSelect: (item: Expense) => void }) {
  const positive = items.filter(item => Number(item.amount_toman) > 0)
  if (!positive.length) return <p className="empty">جزئیات هزینهٔ مثبت موجود نیست.</p>
  const data = positive.map(item => ({ name: item.category_id, value: billions(item.amount_toman) ?? 0 }))
  const colors = ['var(--opex-1)', 'var(--opex-2)', 'var(--opex-3)', 'var(--opex-4)']
  const donutConfig = Object.fromEntries(positive.map((item, index) => [item.category_id, { label: item.category_name_fa, colors: { dark: [colors[index % colors.length]], light: [colors[index % colors.length]] } }])) as ChartConfig
  return <div className="donut-layout">
    <div className="donut-chart" role="img" aria-label="ترکیب دسته‌های مثبت هزینهٔ عملیاتی فصل سوم">
      <EvilPieChart data={data} dataKey="value" nameKey="name" config={donutConfig} onSelectionChange={selection => { const item = positive.find(candidate => candidate.category_id === selection?.dataKey); if (item) onSelect(item) }}>
        <EvilPieChart.Tooltip />
        <EvilPieChart.Pie innerRadius="60%" outerRadius="85%" paddingAngle={3} cornerRadius={5} isClickable pieProps={{ isAnimationActive: false }} />
      </EvilPieChart>
      <div className="donut-center"><b>{fa.format(positive.reduce((sum, item) => sum + (billions(item.amount_toman) ?? 0), 0))}</b><small>میلیارد تومان</small></div>
    </div>
    <div className="expense-list">{positive.map((item, index) => <button type="button" key={`${item.category_id}-${item.cost_center_id}`} onClick={() => onSelect(item)}><span className="expense-name"><i style={{ background: colors[index % colors.length] }} />{item.category_name_fa}</span><strong>{fa.format(billions(item.amount_toman) ?? 0)}</strong><span className="sr-only">نمایش سطرهای سازنده</span></button>)}</div>
  </div>
}
