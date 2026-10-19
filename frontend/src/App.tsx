import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, MotionConfig } from 'motion/react'
import Landing from './Landing'
import Workspace from './Workspace'
import { Brand } from './ui'
import { compact, delta, loadLines, loadReport, metricLabels, monthLabels, type Bucket, type Expense, type FinanceReport, type LineResult, type Metric, type Period } from './finance'

import { Details, Notice, type Filter } from './SourceDetails'
const metricBuckets = { revenue: 'REVENUE', cogs: 'COGS', opex: 'OPEX' } as const
const TrendChart = lazy(() => import('./charts').then(module => ({ default: module.TrendChart })))
const ComparisonChart = lazy(() => import('./charts').then(module => ({ default: module.ComparisonChart })))
const ExpenseDonut = lazy(() => import('./charts').then(module => ({ default: module.ExpenseDonut })))


function MetricCard({ metric, label, q2, q3, change, openQ2, openQ3, profit }: { metric: Metric; label: string; q2: string | null; q3: string | null; change: string | null; openQ2?: () => void; openQ3?: () => void; profit?: boolean }) {
  const direction = change == null ? 'unknown' : BigInt(change) < 0n ? 'negative' : 'positive'
  const magnitude = change == null ? null : (BigInt(change) < 0n ? -BigInt(change) : BigInt(change)).toString()
  const changeLabel = change == null ? 'تغییر نامشخص' : BigInt(change) === 0n ? 'بدون تغییر' : `${direction === 'negative' ? 'کاهش' : 'افزایش'} ${compact(magnitude)} میلیارد`
  return <article className={`metric-card metric-${metric} ${profit ? 'profit-card' : ''}`}><div className="metric-top"><span>{label}</span><span className={`metric-change ${direction}`}>{changeLabel}</span></div><div className="metric-values"><div><small>فصل دوم</small>{openQ2 ? <button onClick={openQ2} aria-label={`جزئیات ${label} فصل دوم`}>{compact(q2)}</button> : <b>{compact(q2)}</b>}</div><span className="metric-divider" /><div><small>فصل سوم</small>{openQ3 ? <button onClick={openQ3} aria-label={`جزئیات ${label} فصل سوم`}>{compact(q3)}</button> : <b>{compact(q3)}</b>}</div></div><span className="metric-unit">میلیارد تومان</span></article>
}

function Bridge({ report, select }: { report: FinanceReport; select: (filter: Filter) => void }) {
  const bridge = report.profit_bridge
  if (bridge.coverage !== 'complete') return <Notice title="پل سود در دسترس نیست" text="پوشش یکی از اجزای مالی ناقص است." />
  const steps: { label: string; value: string | null; bucket?: Bucket; tone: string }[] = [
    { label: 'سود فصل دوم', value: bridge.start_profit_toman, tone: 'total' },
    { label: 'اثر درآمد', value: bridge.revenue_effect_toman, bucket: 'REVENUE', tone: 'gain' },
    { label: 'اثر بهای کالا', value: bridge.cogs_effect_toman, bucket: 'COGS', tone: 'loss' },
    { label: 'اثر هزینهٔ عملیاتی', value: bridge.opex_effect_toman, bucket: 'OPEX', tone: 'loss' },
    { label: 'سود فصل سوم', value: bridge.end_profit_toman, tone: 'total' },
  ]
  const max = Math.max(...steps.map(step => Math.abs(Number(step.value ?? 0))), 1)
  return <div className="bridge">{steps.map((step, index) => { const content = <><span className="bridge-order">۰{index + 1}</span><span className="bridge-bar" style={{ width: `${Math.max(16, Math.abs(Number(step.value ?? 0)) / max * 100)}%` }} /><span className="bridge-label">{step.label}</span><strong>{step.bucket ? delta(step.value) : compact(step.value)}</strong></>; return <div className={`bridge-step ${step.tone} ${step.bucket ? `bridge-${step.bucket.toLowerCase()}` : ''}`} key={step.label}><div>{content}</div>{step.bucket && <div className="bridge-sources"><button onClick={() => select({ period: 'q2', bucket: step.bucket!, title: `${step.label}؛ سطرهای فصل دوم` })}>سطرهای فصل دوم</button><button onClick={() => select({ period: 'q3', bucket: step.bucket!, title: `${step.label}؛ سطرهای فصل سوم` })}>سطرهای فصل سوم</button></div>}</div> })}</div>
}


function Report({ back }: { back: () => void }) {
  const [report, setReport] = useState<FinanceReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const [filter, setFilter] = useState<Filter | null>(null)
  const [result, setResult] = useState<LineResult | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [detailReload, setDetailReload] = useState(0)
  const detailRef = useRef<HTMLDivElement>(null)
  useEffect(() => { const controller = new AbortController(); setLoading(true); loadReport(controller.signal).then(setReport).catch(value => { if (!controller.signal.aborted) setError(String(value.message ?? value)) }).finally(() => { if (!controller.signal.aborted) setLoading(false) }); return () => controller.abort() }, [reload])
  useEffect(() => { if (!filter) return; const controller = new AbortController(); setResult(null); setDetailError(''); setDetailLoading(true); loadLines(filter, controller.signal).then(setResult).catch(value => { if (!controller.signal.aborted) setDetailError(String(value.message ?? value)) }).finally(() => { if (!controller.signal.aborted) setDetailLoading(false) }); return () => controller.abort() }, [filter, detailReload])
  function select(value: Filter) { setFilter(value); window.setTimeout(() => detailRef.current?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }), 50) }
  function selectExpense(item: Expense) { select({ period: 'q3', bucket: 'OPEX', category_id: item.category_id, cost_center_id: item.cost_center_id, title: `هزینهٔ ${item.category_name_fa} در فصل سوم`, expected: item.amount_toman }) }
  const metricKeys: Metric[] = ['revenue', 'cogs', 'opex', 'operating_profit']
  return <div className="report dark"><header className="report-header"><button className="plain-brand" onClick={back} aria-label="بازگشت به صفحهٔ شروع"><Brand /></button><nav aria-label="ناوبری گزارش"><a href="#overview">مرور</a><a href="#trend">روند</a><a href="#drivers">پل سود</a><a href="#expenses">هزینه‌ها</a></nav><button className="back-link" onClick={back}>صفحهٔ شروع ↗</button></header>
    {loading ? <main className="report-container"><Notice title="در حال دریافت گزارش" text="اعداد مالی از API پروژه خوانده می‌شوند." /></main> : error ? <main className="report-container"><Notice title="گزارش بارگذاری نشد" text={`${error}؛ اتصال API و پایگاه داده را بررسی کنید.`} retry={() => { setError(''); setReload(value => value + 1) }} /></main> : report ? <main className="report-container"><div className="report-intro" id="overview"><div><span className="section-kicker">گزارش مالی نمونه / {report.dataset_version}</span><h1>از تغییر سود تا سطرهای سازنده</h1><p>مقایسهٔ فصل دوم و سوم ۲۰۲۶ برای {report.company_name_fa}. روی مبلغ یا بخش هزینه بزنید تا سندهای سازنده را ببینید.</p><div className="meta-row"><span>دوره: {report.period.start} تا {report.period.end_exclusive} (پایان غیرشامل)</span><span>واحد: میلیارد تومان ساختگی</span><span>منطقهٔ زمانی: تهران</span></div></div><div className="synthetic-stamp">◌ دادهٔ ساختگی<small>بدون دادهٔ مشتری</small></div></div>
      <div className="metric-grid">{metricKeys.map(key => { const bucket = key === 'operating_profit' ? null : metricBuckets[key]; return <MetricCard key={key} metric={key} label={metricLabels[key]} q2={report.quarters.q2.values[key]?.amount_toman ?? null} q3={report.quarters.q3.values[key]?.amount_toman ?? null} change={report.quarter_changes[key]?.amount_toman ?? null} profit={!bucket} openQ2={bucket ? () => select({ period: 'q2', bucket, title: `${metricLabels[key]} فصل دوم`, expected: report.quarters.q2.values[key]?.amount_toman }) : undefined} openQ3={bucket ? () => select({ period: 'q3', bucket, title: `${metricLabels[key]} فصل سوم`, expected: report.quarters.q3.values[key]?.amount_toman }) : undefined} /> })}</div>
      <div className="report-grid"><section className="report-section trend-section" id="trend"><div className="section-heading"><div><span className="section-kicker">۰۱ / تصویر زمان</span><h2>روند شش ماه</h2><p>نقطهٔ خالی یعنی پوشش داده ناقص است.</p></div><span className="section-unit">میلیارد تومان</span></div><Suspense fallback={<p className="loading-text">در حال آماده‌سازی نمودار…</p>}><TrendChart report={report} onMonth={month => { const snapshot = report.monthly_trend.find(item => item.month === month); select({ period: month as Period, bucket: 'REVENUE', title: `درآمد ${monthLabels[month]}`, expected: snapshot?.values.revenue.amount_toman }) }} /></Suspense></section><section className="report-section comparison-section"><div className="section-heading"><div><span className="section-kicker">۰۲ / مقایسه</span><h2>دو فصل، چهار شاخص</h2><p>اندازهٔ هر شاخص در دو فصل.</p></div></div><Suspense fallback={<p className="loading-text">در حال آماده‌سازی نمودار…</p>}><ComparisonChart report={report} /></Suspense></section></div>
      <div className="report-grid lower-grid"><section className="report-section" id="drivers"><div className="section-heading"><div><span className="section-kicker">۰۳ / پل تغییر سود</span><h2>سود چگونه تغییر کرد؟</h2><p>سهم حسابی تغییر درآمد و هزینه‌ها؛ علت تجاری مستقل از این پل است.</p></div><span className="section-unit">میلیارد تومان</span></div><Bridge report={report} select={select} /></section><section className="report-section" id="expenses"><div className="section-heading"><div><span className="section-kicker">۰۴ / ترکیب هزینه</span><h2>هزینهٔ عملیاتی فصل سوم</h2><p>فقط اجزای مثبت هزینه؛ هر بخش به سطرهای خودش باز می‌شود.</p></div></div>{report.q3_operating_expense.coverage === 'missing' ? <Notice title="تفکیک در دسترس نیست" text="پوشش هزینهٔ عملیاتی فصل سوم ناقص است." /> : <Suspense fallback={<p className="loading-text">در حال آماده‌سازی نمودار…</p>}><ExpenseDonut items={report.q3_operating_expense.items ?? []} onSelect={selectExpense} /></Suspense>}</section></div>
      <div ref={detailRef}>{filter && <Details filter={filter} result={result} loading={detailLoading} error={detailError} close={() => setFilter(null)} retry={() => setDetailReload(value => value + 1)} />}</div><footer className="report-footer"><span>سود عملیاتی = درآمد − بهای کالا − هزینهٔ عملیاتی. تغییر = فصل سوم − فصل دوم.</span><span>دادهٔ ساختگی · مبالغ دقیق در جزئیات به تومان</span></footer>
    </main> : <main className="report-container"><Notice title="گزارش خالی است" text="API گزارشی برای نمایش برنگرداند." /></main>}
  </div>
}

export default function App() {
  const route = () => location.hash === '#report' ? 'report' : location.hash === '#question' ? 'question' : 'landing'
  const [page, setPage] = useState(route)
  useEffect(() => {
    const sync = () => {
      if (!['', '#', '#report', '#question'].includes(location.hash)) return
      setPage(route())
      scrollTo(0, 0)
    }
    addEventListener('hashchange', sync)
    addEventListener('popstate', sync)
    return () => { removeEventListener('hashchange', sync); removeEventListener('popstate', sync) }
  }, [])
  function navigate(target: string) { location.hash = target; scrollTo(0, 0) }
  function back() { navigate('') }
  return <MotionConfig reducedMotion="user" transition={{ duration: .2 }}><AnimatePresence mode="wait"><motion.div key={page} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: .14 }} onAnimationComplete={() => document.querySelector<HTMLElement>('h1')?.focus({ preventScroll: true })}>
    {page === 'landing' ? <Landing start={() => navigate('question')} openReport={() => navigate('report')} /> : page === 'report' ? <Report back={back} /> : <Workspace back={back} openReport={() => navigate('report')} />}
  </motion.div></AnimatePresence></MotionConfig>
}
