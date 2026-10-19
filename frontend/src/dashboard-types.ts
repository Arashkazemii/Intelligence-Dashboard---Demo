import type { Bucket, Period } from './finance'

export type ChartType = 'area' | 'line' | 'bar' | 'horizontal_bar' | 'grouped_bar' | 'stacked_bar' | 'composed' | 'pie' | 'donut' | 'radial' | 'waterfall' | 'radar'
export interface SourceFilter { period: Period; bucket: Bucket; category_id?: string | null; cost_center_id?: string | null }
export interface DashboardField { key: string; label: string; role: 'dimension' | 'measure'; unit: string; metric?: string }
export interface DashboardRow {
  id: string; label: string; period: string; source_ids: string[]; drilldowns: SourceFilter[]
  role?: 'start' | 'delta' | 'end'
  [key: string]: unknown
}
export interface DashboardDataset {
  id: string; title: string; kind: 'time_series' | 'comparison' | 'breakdown' | 'bridge' | 'normalized'
  fields: DashboardField[]; rows: DashboardRow[]; periods: string[]; coverage: 'complete' | 'missing'; limitations: string[]; total?: number
}
export interface DashboardFact {
  id: string; label: string; value: number | null; display: string; unit: string; period: string; metric: string
  source_ids: string[]; drilldowns: SourceFilter[]; definition?: string; formula?: string; comparison?: string; raw_value?: string
}
export interface DashboardCard { id: string; title: string; fact_id: string }
export interface ChartSpec {
  id: string; type: ChartType; title: string; dataset_id: string; x: string
  series: { field: string; axis: 'left' | 'right' }[]; width: 'half' | 'full'
}
export interface DashboardTable { id: string; title: string; dataset_id: string; columns: string[] }
export interface DashboardInsight {
  id: string; title: string; text: string; kind: 'positive' | 'negative' | 'neutral'; priority: 1 | 2 | 3 | 4 | 5
  fact_ids: string[]; baseline: string; scope: string
}
export interface DashboardSpec {
  version: '2.0'; title: string; answer: string; layout: string[]
  cards: DashboardCard[]; charts: ChartSpec[]; tables: DashboardTable[]; insights: DashboardInsight[]
}
