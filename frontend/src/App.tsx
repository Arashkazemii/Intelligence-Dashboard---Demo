import { lazy, Suspense, useEffect, useRef, useState, type FormEvent } from 'react'
import { askQuestion, compact, delta, exact, loadLines, loadQuestionCapability, loadReport, metricLabels, monthLabels, type Bucket, type Expense, type FinanceReport, type LineResult, type Metric, type Period, type QuestionAnswer } from './finance'
import type { SourceFilter } from './dashboard-types'

type Filter = { period: Period; bucket: Bucket; title: string; category_id?: string; cost_center_id?: string; expected?: string | null }
const questions = ['چرا سود عملیاتی در فصل سوم کاهش یافت؟', 'روند شش‌ماههٔ درآمد و سود چگونه بود؟', 'هزینه‌های عملیاتی فصل سوم از چه بخش‌هایی تشکیل شد؟']
const metricBuckets = { revenue: 'REVENUE', cogs: 'COGS', opex: 'OPEX' } as const
const DynamicDashboard = lazy(() => import('./dashboard'))
const TrendChart = lazy(() => import('./charts').then(module => ({ default: module.TrendChart })))
const ComparisonChart = lazy(() => import('./charts').then(module => ({ default: module.ComparisonChart })))
const ExpenseDonut = lazy(() => import('./charts').then(module => ({ default: module.ExpenseDonut })))

function Brand() { return <span className="brand"><span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></span><span>ویرا<span className="brand-accent">دیتا</span><small>INTELLIGENCE</small></span></span> }

function Landing({ open, ask }: { open: () => void; ask: (question: string) => void }) {
  const [query, setQuery] = useState('')
  const [message, setMessage] = useState('')
  function submit(event: FormEvent) { event.preventDefault(); if (query.trim().length < 2) { setMessage('پرسش را وارد کنید.'); return }; ask(query.trim()) }
  return <div className="landing dark"><div className="landing-glow" aria-hidden="true" /><div className="data-flow" aria-hidden="true">{Array.from({ length: 7 }, (_, index) => <span key={index} />)}</div>
    <header className="landing-header"><span className="entrance scale" style={{ animationDelay: '.06s' }}><Brand /></span><span className="header-note entrance soft" style={{ animationDelay: '.2s' }}>دموی تحلیل مالی</span><button className="header-link entrance scale" style={{ animationDelay: '.32s' }} onClick={open}>گزارش نمونه ↗</button></header>
    <main className="landing-main"><div className="hero-content"><div className="eyebrow entrance pop" style={{ animationDelay: '.24s' }}><span className="sparkle" aria-hidden="true">✦</span> از داده تا بینشِ قابل بررسی</div>
      <h1><span className="headline-mask"><span className="entrance mask" style={{ animationDelay: '.42s' }}>داستان پشت عددها را</span></span><span className="headline-mask"><span className="entrance mask accent-line" style={{ animationDelay: '.62s' }}>واضح‌تر ببینید.</span></span></h1>
      <p className="hero-lede entrance soft" style={{ animationDelay: '.82s' }}>گزارش مالی نمونه را باز کنید؛ از تغییر سود تا سطرهای سازندهٔ هر هزینه، مسیر تحلیل را دنبال کنید.</p>
      <form className="question-form entrance rise" style={{ animationDelay: '.98s' }} onSubmit={submit}><label htmlFor="question">سؤال خود را بنویسید</label><div className="question-box"><input id="question" value={query} onChange={event => { setQuery(event.target.value); setMessage('') }} placeholder="مثلاً چرا سود فصل سوم کمتر شد؟" /><button type="submit" aria-label="ارسال سؤال">↖</button></div></form>
      {message && <p className="question-message" role="status">{message}</p>}
      <div className="sample-questions entrance soft" style={{ animationDelay: '1.1s' }}><span>سؤال‌های آماده:</span>{questions.map(question => <button key={question} onClick={() => ask(question)}>{question}</button>)}</div>
      <button className="primary-button entrance rise" style={{ animationDelay: '1.22s' }} onClick={open}>مشاهدهٔ گزارش نمونه <span>↗</span></button></div></main>
    <footer className="landing-footer entrance stat" style={{ animationDelay: '1.42s' }}><span><i className="live-dot" /> داده‌های مالی کاملاً ساختگی</span><span>فصل دوم و سوم ۲۰۲۶ · تومان</span><span>گزارش قابل بررسی تا سطح سطر</span></footer>
  </div>
}

function Notice({ title, text, retry }: { title: string; text: string; retry?: () => void }) { return <div className="state-notice" role="status"><span className="notice-symbol">◌</span><h2>{title}</h2><p>{text}</p>{retry && <button className="secondary-button" onClick={retry}>تلاش دوباره</button>}</div> }

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

function Details({ filter, result, loading, error, close, retry }: { filter: Filter; result: LineResult | null; loading: boolean; error: string; close: () => void; retry: () => void }) {
  const sum = result?.lines?.reduce((total, row) => total + BigInt(row.amount_toman), 0n)
  const reconciled = result?.bucket_subtotal_toman != null && sum === BigInt(result.bucket_subtotal_toman) && (filter.expected == null || filter.expected === result.bucket_subtotal_toman)
  return <section className={`detail-panel bucket-${filter.bucket.toLowerCase()}`} id="details"><div className="section-heading"><div><span className="section-kicker">ردیابی عدد</span><h2>{filter.title}</h2><p>جمع سطرهای ثبت‌شدهٔ همین فیلتر؛ این عدد سود دسته یا مرکز هزینه نیست.</p></div><button className="close-button" onClick={close} aria-label="بستن جزئیات">×</button></div>
    <div className="filter-tags"><span>{filter.period.startsWith('2026') ? monthLabels[filter.period] : filter.period === 'q2' ? 'فصل دوم' : 'فصل سوم'}</span><span>{filter.bucket}</span>{filter.category_id && <span>دسته: {filter.category_id}</span>}{filter.cost_center_id && <span>مرکز: {filter.cost_center_id}</span>}</div>
    {loading ? <p className="loading-text">در حال دریافت سطرها…</p> : error ? <Notice title="جزئیات دریافت نشد" text={error} retry={retry} /> : result?.coverage === 'missing' ? <Notice title="دادهٔ این بخش ناقص است" text="API پوشش این بازه را ناقص اعلام کرده است." /> : result?.lines?.length === 0 ? <Notice title="سطر ثبت‌شده‌ای نیست" text="جمع این فیلتر صفر است." /> : result?.lines ? <><div className="detail-summary"><div><small>جمع API</small><strong>{exact(result.bucket_subtotal_toman)} <em>تومان ساختگی</em></strong></div><span className={reconciled ? 'reconciled' : 'mismatch'}>{reconciled ? 'جمع سطرها تطبیق دارد' : 'اختلاف در تطبیق سطرها'}</span></div><div className="table-scroll"><table><thead><tr><th>تاریخ</th><th>سند</th><th>شناسهٔ سطر</th><th>دسته / مرکز</th><th>مبلغ، تومان</th></tr></thead><tbody>{result.lines.map(row => <tr key={row.line_id}><td dir="ltr">{row.posted_local_date}</td><td dir="ltr">{row.document_id}</td><td dir="ltr">{row.line_id}</td><td>{row.category_id} / {row.cost_center_id}</td><td className="amount-cell">{exact(row.amount_toman)}</td></tr>)}</tbody></table></div></> : null}</section>
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

function QuestionPage({ initial, back, openReport }: { initial: string; back: () => void; openReport: () => void }) {
  const [query, setQuery] = useState(initial)
  const [answer, setAnswer] = useState<QuestionAnswer | null>(null)
  const [capability, setCapability] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState<Filter | null>(null)
  const [lines, setLines] = useState<LineResult | null>(null)
  const [detailError, setDetailError] = useState('')
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailReload, setDetailReload] = useState(0)
  const detailRef = useRef<HTMLDivElement>(null)
  useEffect(() => { const controller = new AbortController(); loadQuestionCapability(controller.signal).then(value => setCapability(value.enabled)).catch(() => setCapability(false)); return () => controller.abort() }, [])
  useEffect(() => { if (!initial || capability !== true) return; const controller = new AbortController(); setLoading(true); askQuestion(initial, controller.signal).then(setAnswer).catch(value => { if (!controller.signal.aborted) setError(String(value.message ?? value)) }).finally(() => { if (!controller.signal.aborted) setLoading(false) }); return () => controller.abort() }, [initial, capability])
  useEffect(() => { if (!filter) return; const controller = new AbortController(); setLines(null); setDetailError(''); setDetailLoading(true); loadLines(filter, controller.signal).then(setLines).catch(value => { if (!controller.signal.aborted) setDetailError(String(value.message ?? value)) }).finally(() => { if (!controller.signal.aborted) setDetailLoading(false) }); return () => controller.abort() }, [filter, detailReload])
  async function submit(event: FormEvent) { event.preventDefault(); const question = query.trim(); if (question.length < 2) { setError('پرسش را وارد کنید.'); return }; setError(''); setAnswer(null); setFilter(null); setLoading(true); try { setAnswer(await askQuestion(question)) } catch (value) { setError(String((value as Error).message ?? value)) } finally { setLoading(false) } }
  function selectSource(source: SourceFilter, title: string) { setFilter({ ...source, category_id: source.category_id ?? undefined, cost_center_id: source.cost_center_id ?? undefined, title }); window.setTimeout(() => { detailRef.current?.focus({ preventScroll: true }); detailRef.current?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' }) }, 50) }
  return <div className="report dark"><header className="report-header"><button className="plain-brand" onClick={back}><Brand /></button><nav><button className="back-link" onClick={openReport}>گزارش نمونه</button></nav><button className="back-link" onClick={back}>صفحهٔ شروع ↗</button></header><main className="report-container question-page"><div className="report-intro"><div><span className="section-kicker">پرسش آزاد / دادهٔ مالی نمایشی</span><h1>از داده بپرسید</h1><p>فصل دوم و سوم ۲۰۲۶، با عددهای قابل ردیابی تا سطر مالی.</p></div><div className="synthetic-stamp">دادهٔ ساختگی<small>واحد: تومان ساختگی</small></div></div>
    <section className="report-section question-workspace"><form className="question-form" onSubmit={submit}><label htmlFor="analysis-question">پرسش فارسی</label><div className="question-box"><input id="analysis-question" value={query} onChange={event => setQuery(event.target.value)} maxLength={500} placeholder="مثلاً هزینهٔ حمل چقدر بود؟" disabled={loading || capability === false} /><button type="submit" disabled={loading || capability === false} aria-label="تحلیل پرسش">{loading ? '…' : '↖'}</button></div></form><div className="question-suggestions">{['داشبورد بده', 'داشبورد گزارشی بده', 'داشبورد حمل بده', 'نقاط قوت و ضعف را نشان بده', 'روند درآمد را نشان بده', 'فصل دوم و سوم را مقایسه کن'].map(item => <button key={item} type="button" onClick={() => setQuery(item)}>{item}</button>)}</div>
      {capability === false && <Notice title="پرسش آزاد هنوز فعال نیست" text="برای فعال‌سازی، نشانی سرویس مدل، نام مدل و API key را در محیط backend تنظیم کنید. گزارش نمونه همچنان فعال است." />}{capability === null && <p className="loading-text" role="status">در حال بررسی وضعیت سرویس پرسش…</p>}{loading && <p className="loading-text" role="status">در حال تحلیل پرسش و خواندن داده…</p>}{error && <Notice title="پاسخ دریافت نشد" text={error} retry={() => { if (query.trim()) void submit({ preventDefault() {} } as FormEvent) }} />}</section>
    {answer && <Suspense fallback={<p className="loading-text">در حال آماده‌سازی داشبورد…</p>}><DynamicDashboard answer={answer} select={selectSource} /></Suspense>}
    {filter && <div ref={detailRef} tabIndex={-1} role="region" aria-label="سطرهای منبع انتخاب‌شده"><Details filter={filter} result={lines} loading={detailLoading} error={detailError} close={() => setFilter(null)} retry={() => setDetailReload(value => value + 1)} /></div>}</main></div>
}

export default function App() { const [page, setPage] = useState<'landing' | 'report' | 'question'>(() => location.hash === '#report' ? 'report' : location.hash === '#question' ? 'question' : 'landing'); const [initial, setInitial] = useState(''); useEffect(() => { const sync = () => setPage(location.hash === '#report' ? 'report' : location.hash === '#question' ? 'question' : 'landing'); addEventListener('hashchange', sync); return () => removeEventListener('hashchange', sync) }, []); function open() { location.hash = 'report'; setPage('report'); scrollTo(0, 0) } function ask(question: string) { setInitial(question); location.hash = 'question'; setPage('question'); scrollTo(0, 0) } function back() { history.pushState(null, '', location.pathname); setPage('landing'); scrollTo(0, 0) } return page === 'landing' ? <Landing open={open} ask={ask} /> : page === 'report' ? <Report back={back} /> : <QuestionPage initial={initial} back={back} openReport={open} /> }
