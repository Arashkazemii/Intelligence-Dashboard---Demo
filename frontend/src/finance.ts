export type Bucket = 'REVENUE' | 'COGS' | 'OPEX'
export type Metric = 'revenue' | 'cogs' | 'opex' | 'operating_profit'
export type Period = 'q2' | 'q3' | `2026-0${4 | 5 | 6 | 7 | 8 | 9}`

export interface Amount { amount_toman: string | null; coverage: 'complete' | 'missing' }
export interface Snapshot { start: string; end_exclusive: string; missing_buckets: string[]; values: Record<Metric, Amount> }
export interface Expense { category_id: string; category_name_fa: string; cost_center_id: string; amount_toman: string; line_ids: string[] }
export interface FinanceReport {
  dataset_id: string; dataset_version: string; company_name_fa: string; synthetic: boolean
  unit: { code: string; scale: string; amount_encoding: string }
  period: { start: string; end_exclusive: string; label_fa: string }
  quarters: { q2: Snapshot; q3: Snapshot }
  quarter_changes: Record<Metric, Amount>
  monthly_trend: (Snapshot & { month: Period })[]
  profit_bridge: { coverage: 'complete' | 'missing'; start_profit_toman: string | null; revenue_effect_toman: string | null; cogs_effect_toman: string | null; opex_effect_toman: string | null; end_profit_toman: string | null; profit_delta_toman: string | null }
  q3_operating_expense: { coverage: 'complete' | 'missing'; items: Expense[] | null }
}
export interface FinanceLine {
  line_id: string; document_id: string; kind: string; source_line_id: string | null
  bucket: Bucket; category_id: string; cost_center_id: string; item_key: string
  amount_toman: string; quantity_delta: string | null; posted_local_date: string
}
export interface LineResult {
  period: Period; bucket: Bucket; category_id: string | null; cost_center_id: string | null
  coverage: 'complete' | 'missing'; bucket_subtotal_toman: string | null; lines: FinanceLine[] | null
}

import type { DashboardDataset, DashboardFact, DashboardSpec } from './dashboard-types'

export interface QuestionAnswer {
  status: 'answered' | 'out_of_scope' | 'data_unavailable'; message: string
  spec: DashboardSpec | null; datasets: DashboardDataset[]; facts: DashboardFact[]
  dataset_id: string; dataset_version: string; limitations: string[]
  meta: { model_calls: number; supplementary_requests: number }
}

export async function loadQuestionCapability(signal?: AbortSignal): Promise<{ enabled: boolean }> {
  return getJson('/api/demo-finance/question-capability', signal) as Promise<{ enabled: boolean }>
}

export async function askQuestion(question: string, signal?: AbortSignal): Promise<QuestionAnswer> {
  const response = await fetch('/api/demo-finance/question', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }), signal })
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : body
    const message = typeof detail === 'string' ? detail : detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string' ? detail.message : null
    if (message) throw new Error(message)
    if (response.status === 503) throw new Error('سرویس مدل موقتاً در دسترس نیست. کمی بعد دوباره تلاش کنید.')
    if (response.status === 504) throw new Error('مهلت پاسخ سرویس مدل تمام شد. دوباره تلاش کنید.')
    if (response.status === 502) throw new Error('پاسخ سرویس مدل قابل پردازش نیست. دوباره تلاش کنید.')
    throw new Error(`دریافت پاسخ با خطای ${response.status} روبه‌رو شد.`)
  }
  const value = await response.json() as QuestionAnswer
  if (!value || !['answered', 'out_of_scope', 'data_unavailable'].includes(value.status) || typeof value.message !== 'string' || !Array.isArray(value.datasets) || !Array.isArray(value.facts) || !Array.isArray(value.limitations) || (value.status === 'answered' && (!value.spec || value.spec.version !== '2.0' || !Array.isArray(value.spec.layout) || !Array.isArray(value.spec.cards) || !Array.isArray(value.spec.charts) || !Array.isArray(value.spec.tables) || !Array.isArray(value.spec.insights)))) throw new Error('ساختار پاسخ دریافتی با نسخهٔ داشبورد سازگار نیست. صفحه را تازه کنید و دوباره تلاش کنید.')
  return value
}

async function getJson(url: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`API: ${response.status}`)
  return response.json()
}

export async function loadReport(signal?: AbortSignal): Promise<FinanceReport> {
  const value = await getJson('/api/demo-finance/q2-q3-2026', signal) as FinanceReport
  const fields: Metric[] = ['revenue', 'cogs', 'opex', 'operating_profit']
  const validSnapshot = (snapshot: Snapshot | undefined) => Boolean(snapshot?.values && fields.every(field => snapshot.values[field] && (snapshot.values[field].amount_toman === null || /^-?\d+$/.test(snapshot.values[field].amount_toman))))
  if (!value || value.synthetic !== true || !validSnapshot(value.quarters?.q2) || !validSnapshot(value.quarters?.q3) || !Array.isArray(value.monthly_trend) || !value.monthly_trend.every(validSnapshot) || !value.profit_bridge || !value.q3_operating_expense || (value.q3_operating_expense.coverage === 'complete' && !Array.isArray(value.q3_operating_expense.items)) || !value.quarter_changes || !fields.every(field => value.quarter_changes[field]) || !value.unit || !value.period) {
    throw new Error('پاسخ گزارش ناقص یا نامعتبر است.')
  }
  return value
}

export async function loadLines(filter: { period: Period; bucket: Bucket; category_id?: string; cost_center_id?: string }, signal?: AbortSignal): Promise<LineResult> {
  const params = new URLSearchParams({ period: filter.period, bucket: filter.bucket })
  if (filter.category_id) params.set('category_id', filter.category_id)
  if (filter.cost_center_id) params.set('cost_center_id', filter.cost_center_id)
  const value = await getJson(`/api/demo-finance/lines?${params}`, signal) as LineResult
  if (!value || value.period !== filter.period || value.bucket !== filter.bucket || !('bucket_subtotal_toman' in value) || !('lines' in value) || (value.coverage === 'complete' && (!Array.isArray(value.lines) || value.bucket_subtotal_toman == null || !/^-?\d+$/.test(value.bucket_subtotal_toman) || !value.lines.every(line => /^-?\d+$/.test(line.amount_toman))))) {
    throw new Error('پاسخ جزئیات ناقص یا نامعتبر است.')
  }
  return value
}

export const metricLabels: Record<Metric, string> = { revenue: 'درآمد', cogs: 'بهای کالا', opex: 'هزینهٔ عملیاتی', operating_profit: 'سود عملیاتی' }
export const monthLabels: Record<string, string> = { '2026-04': 'آوریل', '2026-05': 'مه', '2026-06': 'ژوئن', '2026-07': 'ژوئیه', '2026-08': 'اوت', '2026-09': 'سپتامبر' }

export const fa = new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 1 })
export function billions(amount: string | null | undefined): number | null { return amount == null ? null : Number(amount) / 1_000_000_000 }
export function compact(amount: string | null | undefined): string { const value = billions(amount); return value == null ? 'بدون داده' : fa.format(value) }
export function exact(amount: string | null | undefined): string { return amount == null ? 'بدون داده' : new Intl.NumberFormat('fa-IR').format(BigInt(amount)) }
export function delta(amount: string | null | undefined): string { const value = billions(amount); return value == null ? 'بدون داده' : `${value > 0 ? '+' : ''}${fa.format(value)}` }
