export type Metrics = {
  q_hf: number | null
  q_pre: number | null
  q_post: number | null
  a_spike: number | null
  e0: number | null
  white_line_scale: number | null
  normalization_mode: string
  route: string | null
  usable_protected_region: boolean
  diagnostics: string[]
}

export type Region = { name: string; start: number; end: number; protected: boolean }
export type Anomaly = {
  energy: number; magnitude: number; region: string; protected: boolean
  automatically_masked: boolean; status: string
}
export type Result = {
  analysis_id: string; sample_id: string; profile_id: string; scan_count: number
  scan_ids: string[]; energy: number[]; raw_average: number[]; normalized_average: number[]
  metrics: Metrics; regions: Region[]; anomalies: Anomaly[]; recommendation: string
  recommendation_reason: string; marginal_gain: number | null; predicted_n_quant: number | null
  n_quant: number | null; total_measured_seconds: number; remaining_scan_budget: number | null
  remaining_time_seconds: number | null; averaging_mode: string; created_at: string
  uncertainty: { q_hf_interval_95?: [number,number] | null; method?: string; alpha?: number }
}
export type Scan = {
  id: string; label: string; metadata: Record<string, unknown>
  energy: number[]; raw: number[]; normalized: number[]
}
export type Sample = {
  sample_id: string; scan_count: number; scans: Scan[]; history: Result[]; averages: Result[]; latest: Result | null
}
export type AppState = {
  framework_version: string; mode: string; acquisition_control_enabled: boolean; watching: boolean
  watch_folder: string; limits: { maximum_scans: number | null; maximum_time_seconds: number | null }
  averaging_mode: string; samples: Sample[]; events: Array<Record<string, unknown>>
  database_counts: Record<string, number>
}
