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
