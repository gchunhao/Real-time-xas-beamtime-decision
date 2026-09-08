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

test("offline import sends all native-selected paths as one batch", async () => {
  let capturedPath;
  let capturedBody;
  globalThis.fetch = async (input, init) => {
    capturedPath = String(input);
    capturedBody = JSON.parse(String(init.body));
    return new Response(JSON.stringify({ mode: "OFFLINE", discovered_files: 2, imported_files: 2, failed_files: 0, errors: [], source_root: "D:\\data", selected_paths: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  await api.importOffline(["D:\\data\\a.dat", "D:\\data\\b.dat"], "equal");
  assert.equal(capturedPath, "/api/import/offline");
  assert.deepEqual(capturedBody, { paths: ["D:\\data\\a.dat", "D:\\data\\b.dat"], recursive: true, averaging_mode: "equal" });
});

test("demo import uses the bundled-data endpoint", async () => {
  let capturedPath;
  globalThis.fetch = async input => {
    capturedPath = String(input);
    return new Response(JSON.stringify({ mode: "OFFLINE", discovered_files: 6, imported_files: 6, failed_files: 0, errors: [], source_root: "demo", selected_paths: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  await api.importDemo();
  assert.equal(capturedPath, "/api/import/demo");
});

test("sample spectrum requests the persisted sample-average endpoint", async () => {
  let capturedPath;
  globalThis.fetch = async input => {
    capturedPath = String(input);
    return new Response(JSON.stringify({ sample_id: "sample/id", energy: [], normalized: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  await api.sampleSpectrum("sample/id");
  assert.equal(capturedPath, "/api/samples/sample%2Fid/spectrum");
});
