import assert from "node:assert/strict";
import test from "node:test";
import { decisionTone, jsonList, overallQc, pct, sampleStatus, scanForecast } from "../.test-dist/formatters.js";

test("quality values are formatted from fractions to percentages", () => assert.equal(pct(0.0045, 2), "0.45%"));
test("all decision states have stable display tones", () => assert.deepEqual(["CONTINUE", "STOP", "REACQUIRE", "REVIEW_REQUIRED"].map(decisionTone), ["continue", "stop", "reacquire", "review"]));
test("audit reason parsing tolerates arrays and legacy text", () => {
  assert.deepEqual(jsonList('["QC_BLOCK","TIME_LIMIT"]'), ["QC_BLOCK", "TIME_LIMIT"]);
  assert.deepEqual(jsonList("legacy reason"), ["legacy reason"]);
});
test("forecast distinguishes predicted total from additional scans", () => {
  assert.deepEqual(scanForecast(6, 2), { total: 6, additional: 4 });
  assert.deepEqual(scanForecast(6, 6), { total: 6, additional: 0 });
  assert.deepEqual(scanForecast(undefined, 2), { total: null, additional: null });
});
test("overall QC reads route and completed samples do not remain running", () => {
  assert.deepEqual(overallQc("A", "STOP"), { value: "Route A", status: "Pass", tone: "good" });
  assert.deepEqual(sampleStatus("STOP"), { label: "Completed", tone: "good" });
  assert.deepEqual(sampleStatus("REVIEW_REQUIRED"), { label: "Review Required", tone: "warn" });
});
