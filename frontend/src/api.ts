import type {
  AppState,
  AuditEvent,
  DecisionResource,
  OfflineImportReport,
  ProjectResource,
  ResourceBundle,
  ReviewPayload,
  ReviewQueueItem,
  ReviewQueueStatus,
  ReviewRecord,
  SampleResource,
  ScanDisposition,
  ScanResource,
  SchedulerState,
  SessionResource,
  SpectrumResource,
  WorkflowProjection,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, body || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  state: () => request<AppState>("/api/state"),
  projects: () => request<ProjectResource[]>("/api/projects"),
  sessions: () => request<SessionResource[]>("/api/sessions"),
  samples: (sessionId?: string | null, archived = false) => {
    const query = new URLSearchParams();
    if (sessionId) query.set("session_id", sessionId);
    if (archived) query.set("archived", "true");
    return request<SampleResource[]>(`/api/samples${query.size ? `?${query}` : ""}`);
  },
  sampleScans: (id: string) => request<ScanResource[]>(`/api/samples/${id}/scans`),
  sampleDecisions: (id: string) => request<DecisionResource[]>(`/api/samples/${id}/decisions`),
  sampleSpectrum: (id: string) => request<SpectrumResource>(`/api/samples/${encodeURIComponent(id)}/spectrum`),
  scans: () => request<ScanResource[]>("/api/scans"),
  spectrum: (id: string) => request<SpectrumResource>(`/api/scans/${encodeURIComponent(id)}/spectrum`),
  decisions: () => request<DecisionResource[]>("/api/decisions"),
  reviews: () => request<ReviewRecord[]>("/api/reviews"),
  queue: (status: ReviewQueueStatus) =>
    request<ReviewQueueItem[]>(`/api/review-queue?status=${status}`),
  audit: () => request<AuditEvent[]>("/api/audit"),
  scheduler: () => request<SchedulerState>("/api/scheduler/state"),
  workflow: () => request<WorkflowProjection>("/api/workflow"),
  saveReview: (payload: ReviewPayload) =>
    request<ReviewRecord>("/api/reviews", { method: "POST", body: JSON.stringify(payload) }),
  setDisposition: (id: string, disposition: ScanDisposition, reason: string) =>
    request<ScanResource>(`/api/scans/${encodeURIComponent(id)}/disposition`, {
      method: "PATCH",
      body: JSON.stringify({ disposition, reason }),
    }),
  reanalyze: (sampleId: string, averagingMode: "equal" | "noise_weighted", includedScanIds: string[], anchors: Record<string, number[]>) =>
    request<unknown>("/api/reanalyze", {
      method: "POST",
      body: JSON.stringify({ sample_id: sampleId, averaging_mode: averagingMode, included_scan_ids: includedScanIds, anchors }),
    }),
  watch: (folder: string, maximumScans: number | null, maximumTimeSeconds: number | null, averagingMode: "equal" | "noise_weighted") =>
    request<unknown>("/api/watch", {
      method: "POST",
      body: JSON.stringify({
        folder,
        maximum_scans: maximumScans,
        maximum_time_seconds: maximumTimeSeconds,
        averaging_mode: averagingMode,
      }),
    }),
  importOffline: (paths: string[], averagingMode: "equal" | "noise_weighted" = "equal") =>
    request<OfflineImportReport>("/api/import/offline", {
      method: "POST",
      body: JSON.stringify({ paths, recursive: true, averaging_mode: averagingMode }),
    }),
  importDemo: () => request<OfflineImportReport>("/api/import/demo", { method: "POST" }),
  archiveSample: (id: string, archived: boolean, reason?: string) =>
    request<SampleResource>(`/api/samples/${encodeURIComponent(id)}/archive`, {
      method: "PATCH",
      body: JSON.stringify({ archived, reason: reason || null }),
    }),
};

export async function loadResources(sessionId?: string | null): Promise<ResourceBundle> {
  const [projects, sessions, samples, archivedSamples, scans, decisions, pending, resolved, superseded, reviews, audit, scheduler, workflow] =
    await Promise.all([
      api.projects(),
      api.sessions(),
      api.samples(sessionId),
      api.samples(sessionId, true),
      api.scans(),
      api.decisions(),
      api.queue("PENDING"),
      api.queue("RESOLVED"),
      api.queue("SUPERSEDED"),
      api.reviews(),
      api.audit(),
      api.scheduler(),
      api.workflow(),
    ]);
  const sampleIds = new Set(samples.map(sample => sample.id));
  const decisionIds = new Set(decisions.filter(decision => sampleIds.has(decision.sample_id)).map(decision => decision.id));
  return {
    projects,
    sessions,
    samples,
    archivedSamples,
    scans: scans.filter(scan => sampleIds.has(scan.sample_id)),
    decisions: decisions.filter(decision => sampleIds.has(decision.sample_id)),
    reviewQueue: [...pending, ...resolved, ...superseded].filter(item => sampleIds.has(item.sample_id)),
    reviews: reviews.filter(review => decisionIds.has(review.decision_id)),
    audit,
    scheduler,
    workflow,
  };
}
