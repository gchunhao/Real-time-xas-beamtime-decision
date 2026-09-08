import { useCallback, useEffect, useState } from "react";
import { api, loadResources } from "./api";
import type { AppState, OfflineImportReport, ResourceBundle, ReviewPayload, ScanDisposition } from "./types";

const EMPTY: ResourceBundle = {
  projects: [], sessions: [], samples: [], archivedSamples: [], scans: [], decisions: [], reviewQueue: [], reviews: [], audit: [],
  scheduler: { mode: "SIMULATION", acquisition_control_enabled: false, held_samples: [], last_execution: null, recent_executions: [] },
  workflow: { generated_at: "", run_status: "PAUSED", simulation_only: true, current_sample_id: null, current_sample_key: null, queue: [], queue_counts: { all: 0, running: 0, queued: 0, review: 0, completed: 0 }, review_queue_count: 0, stages: [], sample_action: null, scheduler_action: null, scheduler: { mode: "SIMULATION", acquisition_control_enabled: false, held_samples: [], last_execution: null, recent_executions: [] } },
};

export function useWorkbenchData() {
  const [state, setState] = useState<AppState | null>(null);
  const [resources, setResources] = useState<ResourceBundle>(EMPTY);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setBusy(true);
    try {
      const nextState = await api.state();
      const nextResources = await loadResources(nextState.session_id);
      setState(nextState);
      setResources(nextResources);
      setError("");
      setLastUpdated(new Date());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      if (!quiet) setBusy(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(true), 2500);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const mutate = useCallback(async <T,>(operation: () => Promise<T>): Promise<T> => {
    setBusy(true);
    try {
      const result = await operation();
      await refresh(true);
      setError("");
      return result;
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught);
      setError(message);
      throw caught;
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  return {
    state, resources, error, busy, lastUpdated, refresh,
    saveReview: (payload: ReviewPayload) => mutate(() => api.saveReview(payload)).then(() => undefined),
    setDisposition: (id: string, disposition: ScanDisposition, reason: string) =>
      mutate(() => api.setDisposition(id, disposition, reason)).then(() => undefined),
    reanalyze: (sampleId: string, averagingMode: "equal" | "noise_weighted", includedScanIds: string[], anchors: Record<string, number[]>) =>
      mutate(() => api.reanalyze(sampleId, averagingMode, includedScanIds, anchors)).then(() => undefined),
    setWatch: (folder: string, maximumScans: number | null, maximumTimeSeconds: number | null, averagingMode: "equal" | "noise_weighted") =>
      mutate(() => api.watch(folder, maximumScans, maximumTimeSeconds, averagingMode)).then(() => undefined),
    importOffline: (paths: string[], averagingMode: "equal" | "noise_weighted" = "equal"): Promise<OfflineImportReport> =>
      mutate(() => api.importOffline(paths, averagingMode)),
    importDemo: (): Promise<OfflineImportReport> => mutate(() => api.importDemo()),
    archiveSample: (id: string, archived: boolean, reason?: string) =>
      mutate(() => api.archiveSample(id, archived, reason)).then(() => undefined),
  };
}
