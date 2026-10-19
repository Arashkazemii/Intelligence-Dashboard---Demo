import { lazy, Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { askQuestion, loadLines, loadQuestionCapability, type LineResult, type QuestionAnswer } from './finance'
import type { SourceFilter } from './dashboard-types'
import { Brand, Reveal } from './ui'
import { Details, Notice, type Filter } from './SourceDetails'

const Dashboard = lazy(() => import('./dashboard'))
const suggestions = ['داشبورد بده', 'داشبورد حمل بده', 'نقاط قوت و ضعف را نشان بده', 'درآمد فصل سوم چقدر بود؟']
type Entry = { id: number; question: string; answer: QuestionAnswer }

export default function Workspace({ back, openReport }: { back: () => void; openReport: () => void }) {
  const [query, setQuery] = useState('')
  const [capability, setCapability] = useState<'checking' | 'enabled' | 'disabled' | 'error'>('checking')
  const [capabilityRetry, setCapabilityRetry] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [entries, setEntries] = useState<Entry[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [filter, setFilter] = useState<Filter | null>(null)
  const [lines, setLines] = useState<LineResult | null>(null)
  const [detailError, setDetailError] = useState('')
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailRetry, setDetailRetry] = useState(0)
  const request = useRef<AbortController | null>(null)
  const detailRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const sequence = useRef(0)
  const current = entries.find(entry => entry.id === activeId)
  useEffect(() => {
    const controller = new AbortController()
    setCapability('checking')
    loadQuestionCapability(controller.signal).then(value => setCapability(value.enabled ? 'enabled' : 'disabled')).catch(() => { if (!controller.signal.aborted) setCapability('error') })
    return () => controller.abort()
  }, [capabilityRetry])
  useEffect(() => () => request.current?.abort(), [])
  useEffect(() => {
    if (activeId === null || !matchMedia('(max-width: 760px)').matches) return
    const timer = window.setTimeout(() => {
      document.getElementById('dashboard-heading')?.focus({ preventScroll: true })
      document.getElementById('dashboard-area')?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' })
    }, 100)
    return () => clearTimeout(timer)
  }, [activeId])
  useEffect(() => {
    if (!filter) return
    const controller = new AbortController()
    setLines(null); setDetailError(''); setDetailLoading(true)
    loadLines(filter, controller.signal).then(setLines).catch(value => { if (!controller.signal.aborted) setDetailError(String(value.message ?? value)) }).finally(() => { if (!controller.signal.aborted) setDetailLoading(false) })
    return () => controller.abort()
  }, [filter, detailRetry])
  async function send(question: string) {
    if (loading || capability !== 'enabled') return
    if (question.trim().length < 2) { setError('پرسش را با دست‌کم دو حرف بنویسید.'); inputRef.current?.focus(); return }
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setSubmitted(question.trim()); setError(''); setFilter(null); setLoading(true)
    try {
      const answer = await askQuestion(question.trim(), controller.signal)
      if (!controller.signal.aborted) {
        const entry = { id: ++sequence.current, question: question.trim(), answer }
        setEntries(values => [...values, entry].slice(-8)); setActiveId(entry.id); setQuery('')
      }
    } catch (value) { if (!controller.signal.aborted) setError(String((value as Error).message ?? value)) }
    finally { if (!controller.signal.aborted) setLoading(false) }
  }
  function submit(event: FormEvent) { event.preventDefault(); void send(query) }
  const selectSource = useCallback((source: SourceFilter, title: string) => {
    setFilter({ ...source, category_id: source.category_id ?? undefined, cost_center_id: source.cost_center_id ?? undefined, title })
  }, [])
  useEffect(() => {
    if (!filter) return
    const timer = window.setTimeout(() => {
      detailRef.current?.focus({ preventScroll: true })
      detailRef.current?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' })
    }, 100)
    return () => clearTimeout(timer)
  }, [filter])
  function closeDetails() { setFilter(null); document.getElementById('dashboard-heading')?.focus() }
  return <div className="workspace dark"><a className="skip-link" href="#dashboard-area">رفتن به داشبورد</a><header className="report-header"><button className="plain-brand" onClick={back} aria-label="صفحهٔ شروع"><Brand /></button><span className="workspace-breadcrumb">فضای تحلیل <span>/</span> داده‌های مالی دمو</span><button className="back-link" onClick={openReport}>گزارش نمونه ↖</button></header>
    <main className="workspace-grid"><aside className="chat-panel" aria-label="گفت‌وگو با داده"><div className="chat-heading"><span className="section-kicker">دستیار تحلیل داده</span><h1 tabIndex={-1}>از داده بپرسید.</h1><p>پرسش فارسی شما، نقطهٔ شروع یک داشبورد.</p></div><div className="chat-context"><span className="live-dot" /> دادهٔ مالی ساختگی <span>فصل دوم و سوم ۲۰۲۶</span></div>
      <div className="chat-messages" aria-live="polite" aria-relevant="additions"><Reveal className="assistant-message"><span className="message-author">ویرا‌دیتا</span><p>می‌خواهید چه چیزی را روشن‌تر ببینید؟ یک داشبورد کلی بخواهید یا سراغ یک شاخص مشخص بروید.</p></Reveal>{entries.map(entry => <Reveal key={entry.id} className={`conversation-entry ${entry.id === activeId ? 'is-active' : ''}`}><div className="user-message"><span className="message-author">پرسش شما</span><p>{entry.question}</p></div><button className="answer-message" disabled={loading} onClick={() => { setActiveId(entry.id); setFilter(null); setError('') }} aria-pressed={entry.id === activeId}><span>{entry.answer.status === 'answered' ? 'داشبورد آماده است' : 'پاسخ آماده است'}</span><small>{entry.answer.spec?.title ?? entry.answer.message}</small><b>{entry.id === activeId ? 'در حال نمایش' : 'مشاهدهٔ پاسخ ←'}</b></button></Reveal>)}{loading && <Reveal className="user-message pending-question"><span className="message-author">پرسش شما</span><p>{submitted}</p></Reveal>}</div>
      <div className="composer"><div className="question-suggestions" aria-label="پرسش‌های پیشنهادی">{suggestions.map(item => <button key={item} disabled={loading || capability !== 'enabled'} onClick={() => { setQuery(item); inputRef.current?.focus() }}>{item} <span aria-hidden="true">↖</span></button>)}</div>
        <form className="question-form" onSubmit={submit}><label htmlFor="analysis-question">پرسش فارسی</label><div className="question-box"><textarea id="analysis-question" ref={inputRef} value={query} onChange={event => setQuery(event.target.value)} maxLength={500} rows={3} placeholder="مثلاً هزینهٔ حمل چقدر بود؟" disabled={loading || capability !== 'enabled'} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(query) } }} /><div className="composer-actions"><small>{new Intl.NumberFormat('fa-IR').format(query.length)} / ۵۰۰</small><motion.button whileTap={{ scale: .96 }} type="submit" disabled={loading || capability !== 'enabled' || query.trim().length < 2} aria-label="تحلیل پرسش">{loading ? 'در حال تحلیل…' : 'ارسال پرسش'} <span aria-hidden="true">↑</span></motion.button></div></div></form><p className="composer-note">هر پرسش مستقل بررسی می‌شود. داده‌های دمو ساختگی‌اند.</p>
        <div role="status" className="service-status">{capability === 'checking' && 'در حال بررسی دسترسی به سرویس…'}{capability === 'disabled' && <>سرویس پرسش فعال نیست؛ <button className="text-button" onClick={openReport}>گزارش نمونه را ببینید</button>.</>}{capability === 'error' && <>بررسی سرویس ناموفق بود. <button className="text-button" onClick={() => setCapabilityRetry(value => value + 1)}>تلاش دوباره</button></>}</div></div></aside>
      <section className="dashboard-area" id="dashboard-area" aria-busy={loading}><div className="workspace-title"><div><span className="section-kicker">پرسش → داشبورد → سطر منبع</span><h2 id="dashboard-heading" tabIndex={-1}>{loading ? 'در حال ساخت پاسخ' : current ? 'داشبورد شما' : 'جای یک دید تازه.'}</h2></div><span className="demo-badge">محیط دمو</span></div>
        {error && <Notice title="پاسخ دریافت نشد" text={error} retry={() => void send(submitted || query)} />}
        {loading ? <div className="generation-state" role="status"><div className="generation-label"><span className="loading-orbit" aria-hidden="true" /><div><h3>پرسش در حال پردازش است</h3><p>بازیابی داده، ساخت پاسخ و اعتبارسنجی داشبورد در سرور انجام می‌شود.</p></div></div><div className="skeleton-grid" aria-hidden="true">{[1, 2, 3].map(value => <div key={value} />)}<div className="skeleton-chart" /></div><button className="text-button" onClick={() => { request.current?.abort(); setLoading(false); setQuery(submitted) }}>لغو درخواست</button></div>
        : current ? <Suspense fallback={<p className="loading-text" role="status">داده دریافت شد؛ آماده‌سازی نمایش داشبورد…</p>}><Dashboard key={current.id} answer={current.answer} select={selectSource} /></Suspense>
        : <Reveal className="workspace-empty"><span className="empty-label">VIRADATA / WORKSPACE</span><h3>پشت هر عدد،<br />چیزی برای کشف هست.</h3><p>از پیشنهادهای کنار صفحه شروع کنید یا پرسش خود را بنویسید. پاسخ و نمودارهای مرتبط اینجا نمایش داده می‌شوند.</p><div className="empty-path"><span>پرسش فارسی</span><span aria-hidden="true">←</span><span>دادهٔ معتبر</span><span aria-hidden="true">←</span><span>بینش قابل بررسی</span></div><button className="secondary-button" onClick={() => { setQuery('داشبورد بده'); inputRef.current?.focus() }}>با یک داشبورد کلی شروع کنید</button></Reveal>}
        <AnimatePresence>{filter && <motion.div ref={detailRef} key="source-detail" className="source-detail-region" tabIndex={-1} role="region" aria-label="سطرهای منبع انتخاب‌شده" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} layout="position"><Details filter={filter} result={lines} loading={detailLoading} error={detailError} close={closeDetails} retry={() => setDetailRetry(value => value + 1)} /></motion.div>}</AnimatePresence>
      </section></main></div>
}
