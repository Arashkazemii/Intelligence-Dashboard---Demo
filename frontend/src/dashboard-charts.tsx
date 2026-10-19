import { useReducedMotion } from 'motion/react'
import { Disclosure } from './ui'
import type { ReactNode } from 'react'
import { Bar, BarChart, Cell, ReferenceLine, Tooltip, XAxis, YAxis } from 'recharts'
import { EvilAreaChart } from './components/evilcharts/charts/recharts-area-chart'
import { EvilLineChart } from './components/evilcharts/charts/recharts-line-chart'
import { EvilBarChart } from './components/evilcharts/charts/recharts-bar-chart'
import { EvilComposedChart } from './components/evilcharts/charts/recharts-composed-chart'
import { EvilPieChart } from './components/evilcharts/charts/recharts-pie-chart'
import { EvilRadialChart } from './components/evilcharts/charts/recharts-radial-chart'
import { EvilRadarChart } from './components/evilcharts/charts/recharts-radar-chart'
import { ChartContainer, type ChartConfig } from './components/evilcharts/ui/recharts-chart'
import type { ChartSpec, ChartType, DashboardDataset, DashboardField, DashboardRow, SourceFilter } from './dashboard-types'
import { fa, monthLabels } from './finance'

const categoryColors = ['#8de3c8', '#e9bc86', '#a8afea', '#75bfd7', '#df9eab', '#bad37c']
const metricColors: Record<string, string> = {
  revenue: 'var(--metric-revenue)', cogs: 'var(--metric-cogs)', opex: 'var(--metric-opex)',
  operating_profit: 'var(--metric-profit)', shipping: '#75bfd7', freight: '#75bfd7', shipping_cost: '#75bfd7',
  payroll: '#a8afea', rent: '#e9bc86', other: '#bad37c',
}

export function periodLabel(period: string): string {
  if (period.includes(':')) return period.split(':').map(periodLabel).join(' تا ')
  return period === 'q2' ? 'فصل دوم ۲۰۲۶' : period === 'q3' ? 'فصل سوم ۲۰۲۶' : monthLabels[period] ? `${monthLabels[period]} ۲۰۲۶` : period
}

// Color is stable across charts, independent of a model's component ordering.
export function metricColor(key: string): string {
  if (metricColors[key]) return metricColors[key]
  const hash = [...key].reduce((value, character) => (value * 31 + character.charCodeAt(0)) >>> 0, 0)
  return categoryColors[hash % categoryColors.length]
}

type ChartContext = { spec: ChartSpec; dataset: DashboardDataset; config: ChartConfig; fields: DashboardField[]; animate: boolean }
type ChartRenderer = (context: ChartContext) => ReactNode
const axisTick = { fill: 'var(--chart-label)', fontSize: 11 }
const chartMargin = { top: 12, right: 12, bottom: 10, left: 4 }
const tick = (value: number) => fa.format(value)
const precise = new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 3 })
export const persianText = (text: string) => text.replace(/(\d)\.(?=\d)/g, '$1٫').replace(/\d/g, value => '۰۱۲۳۴۵۶۷۸۹'[Number(value)])
const baselineSeries = (field: DashboardField, fields: DashboardField[]) => Boolean(field.metric && fields.filter(item => item.metric === field.metric).length > 1 && fields.find(item => item.metric === field.metric)?.key === field.key)

function ChartTooltip({ active, payload, label, context }: {
  active?: boolean; payload?: readonly { dataKey?: unknown; value?: unknown; payload?: Record<string, unknown>; color?: string }[]
  label?: unknown; context: ChartContext
}) {
  if (!active || !payload?.length) return null
  const row = payload[0]?.payload
  const category = context.dataset.rows.find(item => item.id === row?.id)
  const shownFields = context.spec.series.map(series => context.fields.find(field => field.key === series.field)).filter((field): field is DashboardField => Boolean(field))
  return <div className="dashboard-tooltip" dir="rtl"><strong>{String(row?.[context.spec.x] ?? label ?? context.spec.title)}</strong>
    <small>{periodLabel(String(category?.period ?? row?.period ?? ''))}</small>
    {shownFields.map(field => <div key={field.key}><span><i style={{ background: metricColor(field.metric ?? field.key) }} />{field.label}</span><b>{typeof row?.[field.key] === 'number' ? precise.format(row[field.key] as number) : 'بدون داده'} <em>{field.unit}</em></b></div>)}
  </div>
}

const tooltip = (context: ChartContext) => <Tooltip content={<ChartTooltip context={context} />} isAnimationActive={false} cursor={{ stroke: 'var(--chart-label)', strokeOpacity: .25 }} />

function renderLine(context: ChartContext) {
  const { spec, dataset, config } = context
  return <EvilLineChart data={dataset.rows} config={config} animationType="left-to-right" curveType="linear" chartProps={{ margin: chartMargin }}>
    <EvilLineChart.Grid stroke="var(--chart-grid)" />
    <EvilLineChart.XAxis dataKey={spec.x} tick={axisTick} minTickGap={12} />
    <EvilLineChart.YAxis tick={axisTick} tickFormatter={tick} width={44} />
    {tooltip(context)}
    {spec.series.map(series => <EvilLineChart.Line key={series.field} dataKey={series.field} animationType="left-to-right" strokeVariant={baselineSeries(context.fields.find(field => field.key === series.field)!, context.fields) ? 'dashed' : 'solid'} strokeWidth={2.5} lineProps={{ isAnimationActive: false }}><EvilLineChart.Dot /></EvilLineChart.Line>)}
  </EvilLineChart>
}

function renderArea(context: ChartContext) {
  const { spec, dataset, config } = context
  return <EvilAreaChart data={dataset.rows} config={config} animationType="left-to-right" curveType="linear" chartProps={{ margin: chartMargin }}>
    <EvilAreaChart.Grid stroke="var(--chart-grid)" />
    <EvilAreaChart.XAxis dataKey={spec.x} tick={axisTick} minTickGap={12} />
    <EvilAreaChart.YAxis tick={axisTick} tickFormatter={tick} width={44} />
    {tooltip(context)}
    {spec.series.map(series => <EvilAreaChart.Area key={series.field} dataKey={series.field} animationType="left-to-right" strokeVariant="solid" areaProps={{ dataKey: series.field, isAnimationActive: false }} />)}
  </EvilAreaChart>
}

function renderBar(context: ChartContext) {
  const { spec, dataset, config } = context
  const horizontal = spec.type === 'horizontal_bar'
  const data = horizontal ? [...dataset.rows].sort((left, right) => Number(right[spec.series[0].field]) - Number(left[spec.series[0].field])) : dataset.rows
  return <EvilBarChart data={data} config={config} animationType="left-to-right" layout={horizontal ? 'horizontal' : 'vertical'} stackType={spec.type === 'stacked_bar' ? 'stacked' : 'default'} chartProps={{ margin: chartMargin }}>
    <EvilBarChart.Grid stroke="var(--chart-grid)" />
    <EvilBarChart.XAxis dataKey={horizontal ? undefined : spec.x} type={horizontal ? 'number' : 'category'} tick={axisTick} tickFormatter={horizontal ? tick : undefined} interval={0} />
    <EvilBarChart.YAxis dataKey={horizontal ? spec.x : undefined} type={horizontal ? 'category' : 'number'} tick={axisTick} tickFormatter={horizontal ? undefined : tick} width={horizontal ? 112 : 44} />
    {tooltip(context)}
    {spec.series.map(series => <EvilBarChart.Bar key={series.field} dataKey={series.field} animationType="left-to-right" variant={baselineSeries(context.fields.find(field => field.key === series.field)!, context.fields) ? 'hatched' : 'default'} radius={4} barProps={{ isAnimationActive: false }} />)}
  </EvilBarChart>
}

function renderComposed(context: ChartContext) {
  const { spec, dataset, config, fields } = context
  const right = spec.series.some(series => series.axis === 'right')
  return <EvilComposedChart data={dataset.rows} config={config} animationType="left-to-right" curveType="linear" chartProps={{ margin: chartMargin }}>
    <EvilComposedChart.Grid stroke="var(--chart-grid)" />
    <EvilComposedChart.XAxis dataKey={spec.x} tick={axisTick} minTickGap={12} />
    <EvilComposedChart.YAxis yAxisId="left" tick={axisTick} tickFormatter={tick} width={44} />
    {right && <EvilComposedChart.YAxis yAxisId="right" orientation="right" tick={axisTick} tickFormatter={tick} width={48} />}
    {tooltip(context)}
    {spec.series.map((series, index) => index === 0
      ? <EvilComposedChart.Bar key={series.field} dataKey={series.field} animationType="left-to-right" barProps={{ isAnimationActive: false, yAxisId: series.axis, name: fields.find(field => field.key === series.field)?.label }} />
      : <EvilComposedChart.Line key={series.field} dataKey={series.field} animationType="left-to-right" lineProps={{ isAnimationActive: false, yAxisId: series.axis, strokeWidth: 2.5 }} />)}
  </EvilComposedChart>
}

function categoryConfig(context: ChartContext, rows: DashboardRow[]): ChartConfig {
  return Object.fromEntries(rows.map(row => [String(row._categoryKey), {
    label: String(row[context.spec.x]), colors: { dark: [metricColor(categoryKey(row))], light: [metricColor(categoryKey(row))] },
  }])) as ChartConfig
}

const categoryKey = (row: DashboardRow) => String(row.category_id ?? row.id.split(':').at(-1) ?? row.label)
// Upstream uses nameKey in SVG IDs. Keep that internal key ASCII and space-free;
// Persian display labels remain unchanged in the tooltip and visible legend.
const categoryRows = (context: ChartContext): DashboardRow[] => context.dataset.rows.map((row, index) => ({ ...row, _categoryKey: `category_${categoryKey(row).replace(/[^A-Za-z0-9_-]/g, '_')}_${index}` }))

function renderPie(context: ChartContext) {
  const { spec } = context
  const rows = categoryRows(context)
  return <EvilPieChart data={rows} dataKey={spec.series[0].field} nameKey="_categoryKey" config={categoryConfig(context, rows)}>
    {tooltip(context)}
    <EvilPieChart.Pie innerRadius={spec.type === 'donut' ? '58%' : 0} outerRadius="85%" paddingAngle={2} cornerRadius={3} pieProps={{ isAnimationActive: context.animate, animationDuration: 650 }} />
  </EvilPieChart>
}

function renderRadial(context: ChartContext) {
  const { spec, dataset } = context
  const rows = categoryRows(context)
  return <EvilRadialChart data={rows} nameKey="_categoryKey" config={categoryConfig(context, rows)} max={dataset.total} innerRadius="24%" outerRadius="90%">
    {tooltip(context)}
    <EvilRadialChart.RadialBar dataKey={spec.series[0].field} radialBarProps={{ isAnimationActive: context.animate, animationDuration: 650 }} />
  </EvilRadialChart>
}

function renderRadar(context: ChartContext) {
  const { spec, dataset, config } = context
  return <EvilRadarChart data={dataset.rows} config={config} chartProps={{ outerRadius: '72%' }}>
    <EvilRadarChart.PolarGrid stroke="var(--chart-grid)" />
    <EvilRadarChart.PolarAngleAxis dataKey={spec.x} tick={axisTick} />
    <EvilRadarChart.PolarRadiusAxis domain={[0, 'auto']} tickFormatter={tick} tick={axisTick} />
    {tooltip(context)}
    {spec.series.map(series => <EvilRadarChart.Radar key={series.field} dataKey={series.field} radarProps={{ isAnimationActive: context.animate, animationDuration: 650 }} />)}
  </EvilRadarChart>
}

// EvilCharts has no waterfall. Recharts range bars use the same checked contract,
// tooltip, units, colors, and source controls as the EvilCharts renderers.
function renderWaterfall(context: ChartContext) {
  const { spec, dataset, config } = context
  let running = 0
  const data = dataset.rows.map(row => {
    const value = Number(row[spec.series[0].field])
    const start = row.role === 'delta' ? running : 0
    const end = row.role === 'delta' ? running + value : value
    running = end
    return { ...row, _range: [Math.min(start, end), Math.max(start, end)] }
  })
  return <ChartContainer config={config}><BarChart data={data} accessibilityLayer margin={chartMargin}>
    <XAxis dataKey={spec.x} tick={axisTick} tickLine={false} axisLine={false} interval={0} />
    <YAxis tick={axisTick} tickFormatter={tick} tickLine={false} axisLine={false} width={44} />
    <ReferenceLine y={0} stroke="var(--chart-grid)" />
    {tooltip(context)}
    <Bar dataKey="_range" isAnimationActive={context.animate} animationDuration={600} radius={3}>{dataset.rows.map(row => <Cell key={row.id} fill={row.role === 'delta' ? Number(row[spec.series[0].field]) < 0 ? '#e3aa91' : '#8de3c8' : 'var(--metric-profit)'} />)}</Bar>
  </BarChart></ChartContainer>
}

export const chartRegistry: Record<ChartType, { label: string; render: ChartRenderer }> = {
  area: { label: 'سطح زمانی', render: renderArea }, line: { label: 'خط زمانی', render: renderLine },
  bar: { label: 'میله‌ای', render: renderBar }, horizontal_bar: { label: 'رتبه‌بندی افقی', render: renderBar },
  grouped_bar: { label: 'میله‌ای گروهی', render: renderBar }, stacked_bar: { label: 'میله‌ای انباشته', render: renderBar },
  composed: { label: 'میله و خط', render: renderComposed }, pie: { label: 'سهم از کل', render: renderPie },
  donut: { label: 'سهم از کل', render: renderPie }, radial: { label: 'سهم شعاعی از کل', render: renderRadial },
  waterfall: { label: 'پل تغییر سود', render: renderWaterfall }, radar: { label: 'شاخص‌های نرمال‌شده', render: renderRadar },
}

export function SourceControls({ rows, select }: { rows: { id: string; label: string; source_ids: string[]; drilldowns: SourceFilter[] }[]; select: (filter: SourceFilter, title: string) => void }) {
  const available = rows.filter(row => row.drilldowns.length > 0).map(row => ({ ...row, drilldowns: [...new Map(row.drilldowns.map(filter => [JSON.stringify([filter.period, filter.bucket, filter.category_id ?? null, filter.cost_center_id ?? null]), filter])).values()] }))
  if (!available.length) return <p className="source-unavailable">مسیر سطر منبع برای این داده موجود نیست.</p>
  return <Disclosure className="dashboard-sources" title="مشاهدهٔ سطرهای منبع"><div>{available.map(row => <div className="dashboard-source-row" key={row.id}><span>{row.label} <small>({new Set(row.source_ids).size} سطر)</small></span><div>{row.drilldowns.map((filter, index) => <button type="button" key={`${filter.period}-${filter.bucket}-${filter.category_id ?? ''}-${index}`} onClick={() => select(filter, `${row.label} · ${periodLabel(filter.period)}`)}>{periodLabel(filter.period)} · {filter.bucket === 'REVENUE' ? 'درآمد' : filter.bucket === 'COGS' ? 'بهای کالا' : 'هزینهٔ عملیاتی'}{filter.category_id ? ` · ${filter.category_id}` : ''}</button>)}</div></div>)}</div></Disclosure>
}

export function DatasetTable({ dataset, columns, title }: { dataset: DashboardDataset; columns: string[]; title?: string }) {
  const fields = columns.map(key => dataset.fields.find(field => field.key === key)).filter((field): field is DashboardField => Boolean(field))
  return <div className="table-scroll dashboard-table"><table><caption className="sr-only">{title ?? dataset.title}</caption><thead><tr>{fields.map(field => <th key={field.key} scope="col">{field.label}{field.unit ? `، ${field.unit}` : ''}</th>)}</tr></thead><tbody>{dataset.rows.map(row => <tr key={row.id}>{fields.map(field => <td key={field.key} className={field.role === 'measure' ? 'amount-cell' : undefined}>{typeof row[field.key] === 'number' ? precise.format(row[field.key] as number) : row[field.key] == null ? 'بدون داده' : persianText(String(row[field.key]))}</td>)}</tr>)}</tbody></table></div>
}

export function DashboardChart({ spec, dataset, select }: { spec: ChartSpec; dataset: DashboardDataset; select: (filter: SourceFilter, title: string) => void }) {
  const reduce = useReducedMotion()
  const renderer = chartRegistry[spec.type]
  const fields = spec.series.map(series => dataset.fields.find(field => field.key === series.field)).filter((field): field is DashboardField => Boolean(field))
  const config = Object.fromEntries(fields.map(field => [field.key, { label: field.label, colors: { dark: [metricColor(field.metric ?? field.key)], light: [metricColor(field.metric ?? field.key)] } }])) as ChartConfig
  const context = { spec, dataset, config, fields, animate: !reduce }
  const complete = dataset.coverage === 'complete' && dataset.rows.length > 0 && fields.length === spec.series.length
  const category = ['pie', 'donut', 'radial'].includes(spec.type)
  const legend = category ? dataset.rows.map(row => ({ key: row.id, label: String(row[spec.x]), color: metricColor(categoryKey(row)), pattern: false })) : fields.map(field => ({ key: field.key, label: field.label, color: metricColor(field.metric ?? field.key), pattern: baselineSeries(field, fields) }))
  return <section className={`report-section dashboard-chart dashboard-span-${spec.width}`} data-chart-type={spec.type} aria-labelledby={`${spec.id}-title`}>
    <div className="section-heading"><div><span className="section-kicker">{renderer?.label ?? 'نمودار'}</span><h3 id={`${spec.id}-title`}>{persianText(spec.title)}</h3><p>{dataset.periods.map(periodLabel).join(' · ')}</p><span className="dashboard-unit">{[...new Set(fields.map(field => field.unit))].join(' / ')}</span></div></div>
    {renderer && complete ? <><div className={`dashboard-chart-canvas ${category || spec.type === 'radar' ? 'dashboard-chart-round' : ''}`} dir="ltr">{renderer.render(context)}</div><div className="chart-legend">{legend.map(item => <span key={item.key}><i style={{ background: item.color, backgroundImage: item.pattern ? 'repeating-linear-gradient(45deg,transparent 0 2px,#102019 2px 4px)' : undefined }} />{item.label}{item.pattern ? ' · مبنا' : ''}</span>)}</div>
      {spec.type === 'composed' && spec.series.some(series => series.axis === 'right') && <p className="axis-note">محور چپ: {fields.filter(field => spec.series.find(series => series.field === field.key)?.axis === 'left').map(field => `${field.label} (${field.unit})`).join('، ')}؛ محور راست: {fields.filter(field => spec.series.find(series => series.field === field.key)?.axis === 'right').map(field => `${field.label} (${field.unit})`).join('، ')}</p>}
      {spec.type === 'waterfall' && <p className="axis-note">این پل تطبیق حسابداری تغییر سود است؛ علت تجاری را اثبات نمی‌کند.</p>}
      {spec.type === 'radial' && <p className="axis-note">هر کمان نسبت به کل معتبر {dataset.total == null ? '' : fa.format(dataset.total)} {fields[0]?.unit} سنجیده می‌شود.</p>}
      <Disclosure className="dashboard-data" title="مشاهدهٔ دادهٔ نمودار"><DatasetTable dataset={dataset} columns={[spec.x, ...spec.series.map(series => series.field)]} title={spec.title} /></Disclosure>
      <SourceControls rows={dataset.rows} select={select} />
    </> : <p className="empty" role="status">{!renderer ? 'نوع نمودار پشتیبانی نمی‌شود.' : 'دادهٔ کافی و کامل برای این نمودار موجود نیست.'}</p>}
    {dataset.limitations.length > 0 && <ul className="component-limitations">{dataset.limitations.map(item => <li key={item}>{item}</li>)}</ul>}
  </section>
}
