import { useId, useState, type ReactNode } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'

export function Brand() {
  return <span className="brand"><span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></span><span>ویرا<span className="brand-accent">دیتا</span><small>VIRADATA / INTELLIGENCE</small></span></span>
}

export function Reveal({ children, className, delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const reduce = useReducedMotion()
  return <motion.div className={className} initial={reduce ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .32, delay: reduce ? 0 : delay, ease: 'easeOut' }}>{children}</motion.div>
}

export function Disclosure({ title, children, className = '' }: { title: string; children: ReactNode; className?: string }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const reduce = useReducedMotion()
  return <div className={`disclosure ${className}`}><button type="button" className="disclosure-toggle" aria-expanded={open} aria-controls={id} onClick={() => setOpen(value => !value)}><span>{title}</span><span aria-hidden="true">{open ? '−' : '+'}</span></button><AnimatePresence initial={false}>{open && <motion.div id={id} initial={{ height: reduce ? 'auto' : 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: reduce ? 'auto' : 0, opacity: 0 }} transition={{ duration: reduce ? 0 : .2 }} className="disclosure-content"><div>{children}</div></motion.div>}</AnimatePresence></div>
}
