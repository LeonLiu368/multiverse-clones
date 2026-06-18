#!/usr/bin/env node
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const { buildReplayPlan } = require("../src/persistentSessionPlanner");

function argValue(flag, fallback) {
  const index = process.argv.indexOf(flag);
  if (index === -1 || index + 1 >= process.argv.length) {
    return fallback;
  }
  return process.argv[index + 1];
}

function runPsql(sql) {
  const result = spawnSync("psql", ["-v", "ON_ERROR_STOP=1", "-f", "-"], {
    input: sql,
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"]
  });
  if (result.status !== 0) {
    process.stderr.write(result.stdout || "");
    process.stderr.write(result.stderr || "");
    process.exit(result.status || 1);
  }
}

function sqlLiteral(value) {
  return String(value).replace(/'/g, "''");
}

function applyPlan(plan, artifactPath) {
  const values = plan.actions.map((action) => `('${sqlLiteral(action.gap_id)}')`).join(",");
  if (!values) {
    throw new Error("refusing to apply an empty replay plan");
  }
  const auditRows = plan.actions.map((action) => {
    const span = `${action.missing_offsets.start}-${action.missing_offsets.end}`;
    return `('${sqlLiteral(action.gap_id)}','${sqlLiteral(action.action)}','${sqlLiteral(span)}','${sqlLiteral(artifactPath)}')`;
  }).join(",");
  const repairedIds = JSON.stringify(plan.actions.map((action) => action.gap_id));
  const sql = `
WITH planned(gap_id) AS (VALUES ${values})
UPDATE incident_session_gaps
SET status = 'replay_planned',
    candidate_action = 'replay_missing_offsets_before_commit',
    updated_at = NOW()
FROM planned
WHERE incident_session_gaps.gap_id = planned.gap_id;

INSERT INTO session_repair_audit (gap_id, action, offset_span, artifact_path)
VALUES ${auditRows};

UPDATE incident_status
SET status = 'replay_plan_ready',
    repaired_gap_ids = '${sqlLiteral(repairedIds)}'::jsonb,
    updated_at = NOW()
WHERE ticket_id = '${sqlLiteral(plan.incident_id)}';
`;
  runPsql(sql);
}

function main() {
  const fixturePath = argValue("--fixture", path.join(process.cwd(), "fixtures", "reconnect-captures.json"));
  const outPath = argValue("--out", "/app/artifacts/tbmq_persistent_session_replay_plan.json");
  const apply = process.argv.includes("--apply");
  const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
  const plan = buildReplayPlan(fixture);

  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(plan, null, 2) + "\n");
  if (apply) {
    applyPlan(plan, outPath);
  }
  console.log(`wrote ${outPath}`);
}

main();
