import type { ScientificDecision } from "./types";

export function pct(value: number | null | undefined, digits = 2): string {
  return value == null || !Number.isFinite(value) ? "—" : `${(value * 100).toFixed(digits)}%`;
}

export function num(value: number | null | undefined, digits = 2): string {
  return value == null || !Number.isFinite(value) ? "—" : value.toFixed(digits);
}

export function shortTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function decisionTone(value: ScientificDecision | string | null | undefined): string {
  if (value === "STOP") return "stop";
  if (value === "CONTINUE") return "continue";
  if (value === "REACQUIRE") return "reacquire";
  return "review";
}

export function humanize(value: string | null | undefined): string {
  return value ? value.replaceAll("_", " ") : "—";
}

export function jsonList(value: string | null | undefined): string[] {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map(String) : [String(parsed)];
  } catch {
    return [value];
  }
}

export function scanForecast(
  predictedTotal: number | null | undefined,
  currentUsable: number | null | undefined,
): { total: number | null; additional: number | null } {
  if (predictedTotal == null || !Number.isFinite(predictedTotal)) {
    return { total: null, additional: null };
  }
  const total = Math.max(0, Math.round(predictedTotal));
  if (currentUsable == null || !Number.isFinite(currentUsable)) {
    return { total, additional: null };
  }
  return { total, additional: Math.max(0, total - Math.max(0, Math.round(currentUsable))) };
}

export function sampleStatus(decision: ScientificDecision | string | null | undefined): { label: string; tone: string } {
  if (decision === "STOP") return { label: "Completed", tone: "good" };
  if (decision === "CONTINUE") return { label: "Running", tone: "info" };
  if (decision === "REACQUIRE") return { label: "Reacquire", tone: "warn" };
  if (decision === "REVIEW_REQUIRED") return { label: "Review Required", tone: "warn" };
  return { label: "Waiting", tone: "neutral" };
}

export function overallQc(route: string | null | undefined, decision: ScientificDecision | string | null | undefined): { value: string; status: string; tone: string } {
  if (route === "A" || route === "B") return { value: `Route ${route}`, status: "Pass", tone: "good" };
  if (decision === "REVIEW_REQUIRED") return { value: "Not assigned", status: "Review", tone: "warn" };
  if (decision === "REACQUIRE") return { value: "Not assigned", status: "Reacquire", tone: "warn" };
  return { value: "Waiting", status: "Waiting", tone: "neutral" };
}
