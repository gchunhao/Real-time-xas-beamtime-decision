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

export function differenceSpectrum(
  aEnergy: number[],
  aValues: number[],
  bEnergy: number[],
  bValues: number[],
): { x: number[]; y: number[] } {
  const a = aEnergy.flatMap((energy, index) =>
    Number.isFinite(energy) && Number.isFinite(aValues[index]) ? [[energy, aValues[index]] as const] : []
  );
  const b = bEnergy.flatMap((energy, index) =>
    Number.isFinite(energy) && Number.isFinite(bValues[index]) ? [[energy, bValues[index]] as const] : []
  ).sort((left, right) => left[0] - right[0]);
  if (a.length < 2 || b.length < 2) return { x: [], y: [] };

  const x: number[] = [];
  const y: number[] = [];
  let right = 1;
  for (const [energy, value] of a) {
    if (energy < b[0][0] || energy > b[b.length - 1][0]) continue;
    while (right < b.length && b[right][0] < energy) right += 1;
    if (right >= b.length) break;
    const [x1, y1] = b[right - 1];
    const [x2, y2] = b[right];
    const interpolated = x2 === x1 ? y2 : y1 + ((energy - x1) / (x2 - x1)) * (y2 - y1);
    x.push(energy);
    y.push(value - interpolated);
  }
  return { x, y };
}
