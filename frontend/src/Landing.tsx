import { lazy, Suspense, useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { compact, loadReport, metricLabels, type FinanceReport, type Metric } from './finance'
import { Brand, Reveal } from './ui'

const TrendChart = lazy(() => import('./charts').then(module => ({ default: module.TrendChart })))
const metrics: Metric[] = ['revenue', 'cogs', 'opex', 'operating_profit']

function ProductPreview({ openReport }: { openReport: () => void }) {
  const [report, setReport] = useState<FinanceReport | null>(null)
  const [error, setError] = useState(false)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError(false)
    loadReport(controller.signal).then(setReport).catch(() => { if (!controller.signal.aborted) setError(true) })
    return () => controller.abort()
  }, [retry])
  return <section className="product-preview" aria-label="پیش‌نمایش گزارش نمونه"><div className="preview-toolbar"><div><span className="section-kicker">از داخل ویرا‌دیتا</span><h2>یک نگاه به داده، یک مسیر تا بینش.</h2></div><span className="preview-badge">پیش‌نمایش · دادهٔ ساختگی</span></div>
    {report ? <><div className="preview-metrics">{metrics.map(metric => <div key={metric} className={`preview-metric metric-${metric}`}><span>{metricLabels[metric]}</span><strong>{compact(report.quarters.q3.values[metric].amount_toman)} <small>میلیارد تومان</small></strong><span>فصل سوم ۲۰۲۶</span></div>)}</div><div className="preview-chart"><div className="section-heading"><h3>روند درآمد و سود عملیاتی</h3><button className="text-button" onClick={openReport}>بررسی گزارش نمونه ↖</button></div><Suspense fallback={<p className="loading-text">آماده‌سازی نمودار…</p>}><TrendChart report={report} selectedMetrics={['revenue', 'operating_profit']} onMonth={openReport} /></Suspense></div></> : <div className="preview-pending" role="status">{error ? <>پیش‌نمایش دریافت نشد. <button className="text-button" onClick={() => setRetry(value => value + 1)}>تلاش دوباره</button></> : 'در حال دریافت گزارش نمونه از پایگاه داده…'}</div>}
    <div className="preview-footnote">دادهٔ مالی نمایشی پروژه · فصل دوم و سوم ۲۰۲۶ · این پیش‌نمایش پاسخ زنده به پرسش نیست.</div>
  </section>
}

export default function Landing({ start, openReport }: { start: () => void; openReport: () => void }) {
  return <div className="landing dark"><a className="skip-link" href="#landing-content">رفتن به محتوا</a><header className="landing-header"><Brand /><nav aria-label="ناوبری اصلی"><a href="#product-preview">نگاهی به محصول</a><button className="text-button" onClick={openReport}>گزارش نمونه ↖</button></nav><span className="demo-badge">نسخهٔ دمو</span></header>
    <main id="landing-content"><div className="hero-stage"><div className="light-beam" aria-hidden="true"><div className="beam-haze" /><div className="beam-core" /><div className="beam-dust" /><div className="beam-impact" /></div><div className="hero-content"><Reveal delay={.06}><span className="eyebrow"><span className="live-dot" /> هوش داده، به زبان شما</span></Reveal><Reveal delay={.13}><h1 tabIndex={-1}>شما بپرسید.<br />داده‌ها را <span className="accent-line">روشن ببینید.</span></h1></Reveal><Reveal delay={.22}><p className="hero-lede">از یک پرسش فارسی به داشبورد، نمودار و بینش برسید.<br className="desktop-break" /> با عددهایی که می‌توانید تا سطر منبع دنبال کنید.</p></Reveal><Reveal delay={.3}><motion.button className="primary-button start-button" whileHover={{ y: -2 }} whileTap={{ scale: .97 }} onClick={start}>شروع <span aria-hidden="true">←</span></motion.button><p className="hero-caption">یک پرسش، یک دید روشن‌تر.</p></Reveal></div><span className="hero-coordinate" aria-hidden="true">V / 01<br />از پرسش به بینش</span></div>
    <Reveal className="preview-shell" delay={.3}><div id="product-preview"><ProductPreview openReport={openReport} /></div></Reveal><section className="landing-principles" aria-label="مسیر کار"><div><span>۰۱</span><h3>به فارسی بپرسید</h3><p>پرسش خود را دربارهٔ داده‌های دمو بنویسید.</p></div><div><span>۰۲</span><h3>داشبورد را کشف کنید</h3><p>پاسخ، شاخص‌ها و نمودارهای متناسب با پرسش.</p></div><div><span>۰۳</span><h3>به منبع برسید</h3><p>عددها را باز کنید و سطرهای سازنده را ببینید.</p></div></section></main>
    <footer className="landing-footer"><span>ViraData</span><span>دموی تحلیل داده · داده‌های مالی ساختگی، بدون دادهٔ مشتری</span></footer></div>
}
