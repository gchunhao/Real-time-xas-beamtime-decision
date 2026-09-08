export type ScientificDecision = "CONTINUE" | "STOP" | "REACQUIRE" | "REVIEW_REQUIRED";
export type ScanDisposition = "USABLE" | "SUSPECT" | "EXCLUDED_FROM_USABLE_COUNT" | "PENDING_REVIEW";
export type ReviewQueueStatus = "PENDING" | "RESOLVED" | "SUPERSEDED";
export type ReviewerRating = "Q-ready" | "QL-ready" | "Below-QL" | "QC-blocked";
export type ReviewerRole = "User" | "Beamline Scientist" | "PI" | "Postdoc" | "Student" | "Operator" | "Other";
export type ReviewContext = "LIVE" | "RETROSPECTIVE_BLIND" | "HINDSIGHT";

export interface Metrics {
  q_hf?: number | null;
  q_pre?: number | null;
  q_post?: number | null;
  q_hf_pct?: number | null;
  q_pre_pct?: number | null;
  q_post_pct?: number | null;
  a_spike: number | null;
  route?: string | null;
  marginal_gain_pct?: number | null;
  [key: string]: number | string | boolean | null | undefined;
}

export interface Region {
  name: string;
  start?: number;
  end?: number;
  protected?: boolean;
  start_ev?: number;
  end_ev?: number;
}

export interface Anomaly {
  energy?: number;
  protected?: boolean;
  energy_ev?: number;
  region?: string;
  kind?: string;
  status?: string;
  [key: string]: unknown;
}

export interface Scan {
  id: string;
  scan_number?: number | null;
  sample_id?: string | null;
  element?: string | null;
  edge?: string | null;
  scan_type?: string | null;
  duration_s?: number | null;
  label?: string;
  source_path?: string;
  disposition?: ScanDisposition;
  disposition_reason?: string | null;
  energy?: number[];
  raw?: number[];
  mu?: number[];
  normalized?: number[];
  metrics?: Metrics;
  anomalies?: Anomaly[];
  [key: string]: unknown;
}

export interface Sample {
  logical_sample_key?: string;
  sample_id: string;
  profile_id?: string;
  profile_version?: string;
  physical_scan_count?: number;
  usable_scan_count?: number;
  scan_count?: number;
  scans?: Scan[];
  averages?: Result[];
  history?: Result[];
  latest?: Result | null;
  [key: string]: unknown;
}

export interface Result {
  analysis_id?: string;
  decision_id?: string;
  profile_id?: string;
  provenance?: Record<string, unknown>;
  logical_sample_key?: string;
  sample_id: string;
  scan_count: number;
  usable_scan_count?: number;
  recommendation: ScientificDecision;
  scientific_decision?: ScientificDecision;
  effective_action?: ScientificDecision;
  scheduler_action?: ScientificDecision;
  confidence?: number | null;
  route?: string | null;
  reason?: string;
  reason_codes?: string[];
  recommendation_reason?: string;
  marginal_gain?: number | null;
  marginal_gain_pct?: number | null;
  n_quant?: number | null;
  predicted_n_quant?: number | null;
  total_measured_seconds?: number;
  averaging_mode?: "equal" | "noise_weighted";
  decision_confidence?: string;
  resource_constraint?: string | null;
  energy?: number[];
  normalized_average?: number[];
  raw_average?: number[];
  metrics: Metrics;
  regions?: Region[];
  anomalies?: Anomaly[];
  [key: string]: unknown;
}

export interface SchedulerExecution {
  id?: string;
  sample_id?: string;
  scientific_decision?: ScientificDecision;
  sample_action?: string;
  scheduler_action?: string;
  effective_scheduler_action?: string;
  eligibility?: string;
  executed?: boolean;
  review_hold_active?: boolean;
  logical_sample_key?: string;
  requested_action?: ScientificDecision;
  effective_action?: ScientificDecision;
  executed_action?: string;
  status?: string;
  reason?: string;
  created_at?: string;
  [key: string]: unknown;
}

export interface SchedulerState {
  mode: "SIMULATION" | string;
  acquisition_control_enabled: boolean;
  held_samples: string[];
  last_execution: SchedulerExecution | null;
  recent_executions: SchedulerExecution[];
}

export interface AppState {
  mode?: "IDLE" | "LIVE" | "OFFLINE" | string;
  watching?: boolean;
  watch_folder?: string | null;
  project_id?: string | null;
  session_id?: string | null;
  review_queue_count?: number;
  samples: Sample[];
  latest_results?: Record<string, Result>;
  scheduler: SchedulerState;
  [key: string]: unknown;
}

export interface OfflineImportReport {
  mode: "OFFLINE";
  source_root: string;
  selected_paths: string[];
  discovered_files: number;
  imported_files: number;
  failed_files: number;
  errors: Array<{ path: string; error: string }>;
  project_id?: string | null;
  session_id?: string | null;
}

export interface ProjectResource {
  id: string;
  name: string;
  description?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

export interface SessionResource {
  id: string;
  project_id: string;
  name: string;
  beamline?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  [key: string]: unknown;
}

export interface SampleResource {
  id: string;
  session_id: string;
  logical_sample_key?: string;
  sample_key: string;
  element?: string;
  edge?: string;
  scan_type?: string;
  profile_version_id?: string;
  physical_scan_count: number;
  usable_scan_count: number;
  grouping_confidence?: number | null;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface ScanResource {
  id: string;
  sample_id: string;
  logical_sample_key?: string;
  sample_key?: string;
  scan_number: number | null;
  source_path: string;
  duration_seconds: number | null;
  beamline?: string | null;
  disposition: ScanDisposition;
  disposition_reason?: string | null;
  provenance_hash?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

export interface DecisionResource {
  id: string;
  cumulative_average_id: string;
  logical_sample_key?: string;
  sample_key?: string;
  sample_id: string;
  automatic_recommendation: ScientificDecision;
  scientific_decision: ScientificDecision;
  sample_action?: string;
  scheduler_action?: string;
  effective_scheduler_action?: string;
  auto_execution_eligibility?: string;
  adjudicated_reviewer_decision?: ScientificDecision | null;
  adjudication_status?: string | null;
  route?: string | null;
  confidence?: number | null;
  decision_confidence?: string | null;
  physical_scan_count?: number;
  usable_scan_count?: number;
  scan_count?: number;
  marginal_gain?: number | null;
  resource_constraint?: string | null;
  automatic_reason?: string | null;
  reason_codes_json?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

export interface ReviewQueueItem {
  id: string;
  decision_id: string;
  sample_id: string;
  logical_sample_key?: string;
  sample_key?: string;
  scientific_decision: ScientificDecision;
  automatic_reason?: string | null;
  decision_confidence?: string | null;
  status: ReviewQueueStatus;
  enqueued_at?: string;
  resolved_at?: string | null;
  [key: string]: unknown;
}

export interface ReviewRecord {
  id: string;
  decision_id: string;
  sample_id: string;
  reviewer?: string | null;
  reviewer_role: ReviewerRole;
  reviewer_level: number;
  review_context: ReviewContext;
  rating: ReviewerRating;
  override_recommendation?: ScientificDecision | null;
  notes?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

export interface AuditEvent {
  id: string;
  event_type: string;
  sample_id?: string | null;
  scan_id?: string | null;
  analysis_id?: string | null;
  payload_json?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

export interface SpectrumResource {
  scan_id: string;
  energy: number[];
  raw?: number[];
  normalized?: number[];
  mu?: number[];
  [key: string]: unknown;
}

export interface ResourceBundle {
  projects: ProjectResource[];
  sessions: SessionResource[];
  samples: SampleResource[];
  scans: ScanResource[];
  decisions: DecisionResource[];
  reviewQueue: ReviewQueueItem[];
  reviews: ReviewRecord[];
  audit: AuditEvent[];
  scheduler: SchedulerState;
  workflow: WorkflowProjection;
}

export type WorkflowSampleStatus = "RUNNING" | "QUEUED" | "REVIEW" | "COMPLETED";

export interface WorkflowQueueItem {
  sample_id: string;
  logical_sample_key: string;
  element?: string | null;
  edge?: string | null;
  scan_type?: string | null;
  status: WorkflowSampleStatus;
  automatic_decision?: ScientificDecision | null;
  sample_action?: string | null;
  scheduler_action?: string | null;
  physical_scan_count: number;
  usable_scan_count: number;
  updated_at?: string | null;
}

export interface WorkflowProjection {
  generated_at: string;
  run_status: string;
  simulation_only: true;
  current_sample_id?: string | null;
  current_sample_key?: string | null;
  queue: WorkflowQueueItem[];
  queue_counts: { all: number; running: number; queued: number; review: number; completed: number };
  review_queue_count: number;
  stages: Array<{ key: string; label: string; state: "complete" | "active" | "simulated" | "waiting" }>;
  sample_action?: string | null;
  scheduler_action?: string | null;
  scheduler: SchedulerState;
}

export interface ReviewPayload {
  analysis_id: string;
  sample_id: string;
  rating: ReviewerRating;
  override_recommendation: ScientificDecision | null;
  notes: string;
  reviewer: string;
  reviewer_role: ReviewerRole;
  reviewer_level: number;
  review_context: ReviewContext;
  averaging_mode: "equal" | "noise_weighted";
  included_scans: string[];
  excluded_scans: string[];
  glitch_decisions: Array<Record<string, unknown>>;
  local_normalization_anchors: Record<string, number[]>;
}
