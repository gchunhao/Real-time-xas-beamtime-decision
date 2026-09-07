import assert from "node:assert/strict";
import test from "node:test";
import { api, loadResources } from "../.test-dist/api.js";

test("loads all resource collections and all review queue states", async () => {
  const paths = [];
  globalThis.fetch = async input => {
    const path = String(input); paths.push(path);
    const body = path === "/api/scheduler/state"
      ? { mode: "SIMULATION", acquisition_control_enabled: false, held_samples: [], last_execution: null, recent_executions: [] }
      : path === "/api/workflow"
        ? { simulation_only: true, queue: [], queue_counts: { all: 0 }, stages: [] }
        : [];
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  const bundle = await loadResources();
  assert.equal(bundle.scheduler.mode, "SIMULATION");
  assert.equal(bundle.workflow.simulation_only, true);
  for (const path of ["/api/projects", "/api/samples", "/api/scans", "/api/decisions", "/api/review-queue?status=PENDING", "/api/review-queue?status=RESOLVED", "/api/review-queue?status=SUPERSEDED", "/api/audit", "/api/workflow"]) assert.ok(paths.includes(path), path);
});

test("watch request uses backend seconds contract and averaging mode", async () => {
  let captured;
  globalThis.fetch = async (_input, init) => { captured = JSON.parse(String(init.body)); return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }); };
  await api.watch("D:\\beamtime", 8, 600, "noise_weighted");
  assert.deepEqual(captured, { folder: "D:\\beamtime", maximum_scans: 8, maximum_time_seconds: 600, averaging_mode: "noise_weighted" });
});
