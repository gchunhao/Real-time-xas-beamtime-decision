import assert from "node:assert/strict";
import test from "node:test";
import { decisionTone, jsonList, pct } from "../.test-dist/formatters.js";

test("quality values are formatted from fractions to percentages", () => assert.equal(pct(0.0045, 2), "0.45%"));
test("all decision states have stable display tones", () => assert.deepEqual(["CONTINUE", "STOP", "REACQUIRE", "REVIEW_REQUIRED"].map(decisionTone), ["continue", "stop", "reacquire", "review"]));
test("audit reason parsing tolerates arrays and legacy text", () => {
  assert.deepEqual(jsonList('["QC_BLOCK","TIME_LIMIT"]'), ["QC_BLOCK", "TIME_LIMIT"]);
  assert.deepEqual(jsonList("legacy reason"), ["legacy reason"]);
});
