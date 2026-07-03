#!/usr/bin/env python3
"""Shared soak / SLO verifier for live-deployment eval tasks (Primitive P3).

Harbor runs this INSIDE the `main` container AFTER the agent has exited and
declared its fix live. The verifier drives its OWN load at the SUT (system
under test), measures SLOs during a soak window, checks a findings artifact,
and grades. It is tamper-resistant: it reads only

  (a) its own live measurements against the SUT, and
  (b) a fresh, task-captured deploy snapshot (recorded, never trusted for grade),

never anything the agent could have pre-poisoned (no counters the app writes,
no files the agent can edit except the *contents* of findings.json, which are
graded against a spec the agent cannot see).

CLI:
    python soak.py --target http://conduit.web.1:5000 --config soak_config.json \
        [--reward-dir DIR] [--findings PATH] [--audit-cmd 'dokku config:show conduit'] \
        [--audit-file PATH]

Outputs (into ${REWARD_DIR:-/logs/verifier}, or --reward-dir):
    reward.txt   -- a bare float, "1.0" or "0.0"
    result.json  -- the full reward basis (all measured SLOs, per-phase counts,
                    findings verdict, infra_error flag, config + audit snapshot)

Design notes:
  * stdlib + httpx only. Python 3.9 compatible (no `X | Y`, no `match`).
  * Closed-loop-ish open-model load: a fixed-size thread worker pool issues
    requests at a target RPS via a shared token schedule. Simpler and more
    robust across environments than asyncio here, and easy to bound.
  * Unique markers per request (uuid4) so trials never collide and the
    write/read-back correctness check is unambiguous.
  * Only the SOAK window is measured; WARMUP is discarded so transient
    connection resets during the agent's redeploy do not taint the grade.
  * Bounded timeouts everywhere; the process must never hang.
"""
import argparse
import json
import os
import queue
import statistics
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError:  # pragma: no cover - env must provide httpx
    httpx = None


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
@dataclass
class Flow:
    """One driver flow. `kind` selects the built-in behavior.

    kind="write_readback": POST `write.path` with a body that embeds a unique
      marker (templated via {marker}); then GET `read.path` (templated with the
      created resource's slug/id extracted from the POST response via
      `slug_json_path`) and assert the marker text appears in the response body.
    kind="read": GET `path` and assert HTTP ok (optionally that
      `expect_substring` appears).
    """
    name: str
    kind: str
    weight: float = 1.0

    # write_readback
    write_path: Optional[str] = None
    write_body: Optional[Dict[str, Any]] = None      # JSON template; {marker} substituted
    slug_json_path: Optional[str] = None             # dotted path to slug/id in POST resp
    read_path_template: Optional[str] = None         # e.g. "/api/articles/{slug}"
    marker_field: str = "title"                      # informational only

    # read
    path: Optional[str] = None
    expect_substring: Optional[str] = None

    # auth / headers common to both
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class FindingsSpec:
    """Grades /workspace/findings.json. The agent cannot see this spec."""
    required_keys: List[str] = field(default_factory=lambda: ["component", "mechanism"])
    # every regex here must match (case-insensitive) somewhere in the joined
    # string values of the findings. Use these to force the agent to name the
    # actual failing mechanism (e.g. r"pool", r"connection").
    mechanism_regexes: List[str] = field(default_factory=list)
    # a plain-substring convenience list (case-insensitive), all required.
    mechanism_substrings: List[str] = field(default_factory=list)


@dataclass
class SoakConfig:
    target: str = ""
    health_path: str = "/health"
    health_timeout_s: float = 60.0        # max seconds to wait for first healthy
    health_poll_interval_s: float = 1.0

    warmup_s: float = 15.0
    soak_s: float = 180.0
    rps: float = 20.0
    workers: int = 24                     # thread pool size; >= peak in-flight
    request_timeout_s: float = 5.0

    # SLO gates (applied per-driver AND overall)
    goodput_min: float = 0.85             # correct / offered
    error_rate_max: float = 0.12          # failures / offered
    min_samples_per_driver: int = 5       # below this a driver is not gated (too few)

    flows: List[Flow] = field(default_factory=list)
    findings: FindingsSpec = field(default_factory=FindingsSpec)

    # optional bootstrap: register/login to obtain a token before the soak.
    # A tiny fixed sequence of requests; the last response's `token_json_path`
    # value is injected into any header value containing "{token}".
    bootstrap: Optional[Dict[str, Any]] = None

    @staticmethod
    def load(path: str) -> "SoakConfig":
        with open(path, "r") as fh:
            raw = json.load(fh)
        return SoakConfig.from_dict(raw)

    @staticmethod
    def from_dict(raw: Dict[str, Any]) -> "SoakConfig":
        raw = dict(raw)
        flows = [Flow(**f) for f in raw.pop("flows", [])]
        findings_raw = raw.pop("findings", {}) or {}
        findings = FindingsSpec(**findings_raw)
        cfg = SoakConfig(**raw)
        cfg.flows = flows
        cfg.findings = findings
        return cfg


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _dig(obj: Any, dotted: str) -> Any:
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur[part]
    return cur


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    vs = sorted(values)
    if len(vs) == 1:
        return vs[0]
    k = (len(vs) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(vs) - 1)
    frac = k - lo
    return vs[lo] + (vs[hi] - vs[lo]) * frac


def _subst(template: Any, mapping: Dict[str, str]) -> Any:
    """Recursively .format() every string in a JSON-ish structure."""
    if isinstance(template, str):
        try:
            return template.format(**mapping)
        except (KeyError, IndexError):
            return template
    if isinstance(template, dict):
        return {k: _subst(v, mapping) for k, v in template.items()}
    if isinstance(template, list):
        return [_subst(v, mapping) for v in template]
    return template


# --------------------------------------------------------------------------- #
# Health gate
# --------------------------------------------------------------------------- #
def wait_healthy(client: "httpx.Client", cfg: SoakConfig) -> bool:
    deadline = time.time() + cfg.health_timeout_s
    url = cfg.target.rstrip("/") + cfg.health_path
    while time.time() < deadline:
        try:
            r = client.get(url, timeout=cfg.request_timeout_s)
            if r.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(cfg.health_poll_interval_s)
    return False


# --------------------------------------------------------------------------- #
# Bootstrap (optional auth)
# --------------------------------------------------------------------------- #
def run_bootstrap(client: "httpx.Client", cfg: SoakConfig) -> Dict[str, str]:
    """Returns a mapping usable in flow header templates, e.g. {"token": "..."}."""
    ctx: Dict[str, str] = {}
    bs = cfg.bootstrap
    if not bs:
        return ctx
    steps = bs.get("steps", [])
    token_path = bs.get("token_json_path")
    for step in steps:
        method = step.get("method", "POST").upper()
        url = cfg.target.rstrip("/") + step["path"]
        body = _subst(step.get("body"), {"marker": uuid.uuid4().hex[:12]})
        headers = step.get("headers", {})
        try:
            r = client.request(method, url, json=body, headers=headers,
                               timeout=cfg.request_timeout_s)
            if token_path and r.status_code < 300:
                try:
                    ctx["token"] = str(_dig(r.json(), token_path))
                except Exception:
                    pass
        except Exception:
            pass
    return ctx


# --------------------------------------------------------------------------- #
# Load driver
# --------------------------------------------------------------------------- #
@dataclass
class Sample:
    ts: float
    phase: str          # "warmup" | "soak"
    driver: str
    op: str             # "write" | "readback" | "read"
    latency_ms: float
    status: int
    ok: bool            # transport + HTTP < 500 (not a server error / timeout)
    correct: bool       # semantic success (marker read back / substring present)


def _pick_flow(flows: List[Flow], r: float) -> Flow:
    total = sum(max(f.weight, 0.0) for f in flows) or 1.0
    acc = 0.0
    for f in flows:
        acc += max(f.weight, 0.0) / total
        if r <= acc:
            return f
    return flows[-1]


def _do_write_readback(client, cfg, flow, ctx) -> List[Sample]:
    out: List[Sample] = []
    marker = "soak-" + uuid.uuid4().hex[:16]
    mapping = dict(ctx)
    mapping["marker"] = marker
    headers = _subst(flow.headers, mapping)
    body = _subst(flow.write_body or {}, mapping)
    write_url = cfg.target.rstrip("/") + (flow.write_path or "/")

    slug = None
    t0 = time.time()
    status, ok, correct = 0, False, False
    try:
        r = client.post(write_url, json=body, headers=headers,
                       timeout=cfg.request_timeout_s)
        status = r.status_code
        ok = status < 500
        if 200 <= status < 300:
            correct = True
            if flow.slug_json_path:
                try:
                    slug = str(_dig(r.json(), flow.slug_json_path))
                except Exception:
                    slug = None
    except Exception:
        status, ok, correct = 0, False, False
    out.append(Sample(t0, "", flow.name, "write",
                     (time.time() - t0) * 1000.0, status, ok, correct))

    # read-back leg (only meaningful if we got a slug)
    if flow.read_path_template and slug is not None:
        read_url = cfg.target.rstrip("/") + flow.read_path_template.format(slug=slug)
        t1 = time.time()
        status2, ok2, correct2 = 0, False, False
        try:
            r2 = client.get(read_url, headers=headers, timeout=cfg.request_timeout_s)
            status2 = r2.status_code
            ok2 = status2 < 500
            correct2 = (200 <= status2 < 300) and (marker in r2.text)
        except Exception:
            status2, ok2, correct2 = 0, False, False
        out.append(Sample(t1, "", flow.name, "readback",
                         (time.time() - t1) * 1000.0, status2, ok2, correct2))
    return out


def _do_read(client, cfg, flow, ctx) -> List[Sample]:
    headers = _subst(flow.headers, ctx)
    url = cfg.target.rstrip("/") + (flow.path or "/")
    t0 = time.time()
    status, ok, correct = 0, False, False
    try:
        r = client.get(url, headers=headers, timeout=cfg.request_timeout_s)
        status = r.status_code
        ok = status < 500
        correct = (200 <= status < 300)
        if correct and flow.expect_substring:
            correct = flow.expect_substring in r.text
    except Exception:
        status, ok, correct = 0, False, False
    return [Sample(t0, "", flow.name, "read",
                  (time.time() - t0) * 1000.0, status, ok, correct)]


def _one_request(client, cfg, flow, ctx) -> List[Sample]:
    if flow.kind == "write_readback":
        return _do_write_readback(client, cfg, flow, ctx)
    return _do_read(client, cfg, flow, ctx)


def drive_load(client, cfg: SoakConfig, ctx: Dict[str, str]) -> List[Sample]:
    """Open-model load: a scheduler enqueues one job every 1/rps seconds; a
    worker pool executes them. Jobs carry the phase stamped at *dispatch* time,
    so soak vs warmup is decided by when the request starts, not when it ends.
    """
    import random
    rng = random.Random(1234)  # deterministic flow selection sequence

    samples: List[Sample] = []
    samples_lock = threading.Lock()
    jobs: "queue.Queue" = queue.Queue(maxsize=cfg.workers * 4)
    stop = threading.Event()

    warmup_end = None  # set at start below

    def worker():
        while True:
            item = jobs.get()
            if item is None:
                jobs.task_done()
                return
            phase, flow = item
            try:
                results = _one_request(client, cfg, flow, ctx)
                for s in results:
                    s.phase = phase
                with samples_lock:
                    samples.extend(results)
            except Exception:
                pass
            finally:
                jobs.task_done()

    pool = [threading.Thread(target=worker, daemon=True) for _ in range(cfg.workers)]
    for t in pool:
        t.start()

    interval = 1.0 / cfg.rps if cfg.rps > 0 else 0.05
    start = time.time()
    warmup_end = start + cfg.warmup_s
    soak_end = warmup_end + cfg.soak_s
    n = 0
    while True:
        now = time.time()
        if now >= soak_end:
            break
        phase = "warmup" if now < warmup_end else "soak"
        flow = _pick_flow(cfg.flows, rng.random())
        # If the queue is saturated (SUT slower than offered load) we still want
        # to keep offering, but avoid unbounded growth: drop-block briefly.
        try:
            jobs.put((phase, flow), timeout=cfg.request_timeout_s)
        except queue.Full:
            pass
        n += 1
        # pace to target rps
        target_t = start + n * interval
        sleep = target_t - time.time()
        if sleep > 0:
            time.sleep(sleep)

    # drain: let in-flight finish, bounded
    drain_deadline = time.time() + cfg.request_timeout_s + 2.0
    while not jobs.empty() and time.time() < drain_deadline:
        time.sleep(0.05)
    for _ in pool:
        try:
            jobs.put_nowait(None)
        except queue.Full:
            pass
    for t in pool:
        t.join(timeout=2.0)

    return samples


# --------------------------------------------------------------------------- #
# Grading
# --------------------------------------------------------------------------- #
def _grade_group(rows: List[Sample]) -> Dict[str, Any]:
    offered = len(rows)
    ok = sum(1 for s in rows if s.ok)
    correct = sum(1 for s in rows if s.correct)
    failures = offered - ok
    lat = [s.latency_ms for s in rows]
    goodput = (correct / offered) if offered else 0.0
    err = (failures / offered) if offered else 0.0
    return {
        "offered": offered,
        "ok": ok,
        "correct": correct,
        "failures": failures,
        "goodput_ratio": round(goodput, 4),
        "error_rate": round(err, 4),
        "latency_p50_ms": round(_percentile(lat, 50), 2) if lat else None,
        "latency_p95_ms": round(_percentile(lat, 95), 2) if lat else None,
        "latency_p99_ms": round(_percentile(lat, 99), 2) if lat else None,
    }


def grade_slos(samples: List[Sample], cfg: SoakConfig) -> Dict[str, Any]:
    soak = [s for s in samples if s.phase == "soak"]
    warmup = [s for s in samples if s.phase == "warmup"]

    per_driver: Dict[str, Any] = {}
    driver_names = sorted(set(s.driver for s in soak))
    all_pass = True
    reasons: List[str] = []

    for name in driver_names:
        rows = [s for s in soak if s.driver == name]
        g = _grade_group(rows)
        gated = g["offered"] >= cfg.min_samples_per_driver
        d_pass = True
        if gated:
            if g["goodput_ratio"] < cfg.goodput_min:
                d_pass = False
                reasons.append(
                    "driver %s goodput %.3f < %.3f"
                    % (name, g["goodput_ratio"], cfg.goodput_min))
            if g["error_rate"] > cfg.error_rate_max:
                d_pass = False
                reasons.append(
                    "driver %s error_rate %.3f > %.3f"
                    % (name, g["error_rate"], cfg.error_rate_max))
        g["gated"] = gated
        g["pass"] = d_pass
        per_driver[name] = g
        if gated and not d_pass:
            all_pass = False

    overall = _grade_group(soak)
    overall_gated = overall["offered"] >= cfg.min_samples_per_driver
    overall_pass = True
    if not overall_gated:
        overall_pass = False
        reasons.append("overall soak samples %d < min %d (no measurable load)"
                       % (overall["offered"], cfg.min_samples_per_driver))
    else:
        if overall["goodput_ratio"] < cfg.goodput_min:
            overall_pass = False
            reasons.append("overall goodput %.3f < %.3f"
                           % (overall["goodput_ratio"], cfg.goodput_min))
        if overall["error_rate"] > cfg.error_rate_max:
            overall_pass = False
            reasons.append("overall error_rate %.3f > %.3f"
                           % (overall["error_rate"], cfg.error_rate_max))
    overall["gated"] = overall_gated
    overall["pass"] = overall_pass

    slos_pass = all_pass and overall_pass
    return {
        "slos_pass": slos_pass,
        "gates": {"goodput_min": cfg.goodput_min,
                  "error_rate_max": cfg.error_rate_max},
        "overall": overall,
        "per_driver": per_driver,
        "warmup_counts": {"offered": len(warmup)},
        "reasons": reasons,
    }


# --------------------------------------------------------------------------- #
# Findings gate
# --------------------------------------------------------------------------- #
def grade_findings(path: str, spec: FindingsSpec) -> Dict[str, Any]:
    import re
    verdict = {"path": path, "pass": False, "reasons": []}
    try:
        with open(path, "r") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        verdict["reasons"].append("findings.json not found")
        return verdict
    except (OSError, json.JSONDecodeError) as e:
        verdict["reasons"].append("findings.json unreadable/invalid JSON: %s" % e)
        return verdict

    if not isinstance(data, dict):
        verdict["reasons"].append("findings.json is not a JSON object")
        return verdict

    missing = [k for k in spec.required_keys
               if k not in data or str(data.get(k, "")).strip() == ""]
    if missing:
        verdict["reasons"].append("missing/empty required keys: %s" % ", ".join(missing))

    # joined lowercase blob of all string values for substring/regex matching
    def _flatten(v):
        if isinstance(v, str):
            return [v]
        if isinstance(v, dict):
            out = []
            for x in v.values():
                out += _flatten(x)
            return out
        if isinstance(v, list):
            out = []
            for x in v:
                out += _flatten(x)
            return out
        return [str(v)]

    blob = " ".join(_flatten(data)).lower()

    for sub in spec.mechanism_substrings:
        if sub.lower() not in blob:
            verdict["reasons"].append("mechanism missing required substring: %r" % sub)
    for rx in spec.mechanism_regexes:
        if not re.search(rx, blob, re.IGNORECASE):
            verdict["reasons"].append("mechanism does not match required regex: %r" % rx)

    verdict["pass"] = len(verdict["reasons"]) == 0
    verdict["findings"] = data
    return verdict


# --------------------------------------------------------------------------- #
# Deploy audit snapshot (recorded, not gated in MVP)
# --------------------------------------------------------------------------- #
def capture_audit(audit_cmd: Optional[str], audit_file: Optional[str]) -> Dict[str, Any]:
    snap: Dict[str, Any] = {"cmd": audit_cmd, "file": audit_file,
                            "captured": False, "output": None}
    if audit_file:
        try:
            with open(audit_file, "r") as fh:
                snap["output"] = fh.read()
            snap["captured"] = True
            return snap
        except OSError as e:
            snap["error"] = "audit file unreadable: %s" % e
    if audit_cmd:
        try:
            r = subprocess.run(audit_cmd, shell=True, capture_output=True,
                             text=True, timeout=30)
            snap["output"] = (r.stdout or "") + (r.stderr or "")
            snap["returncode"] = r.returncode
            snap["captured"] = True
        except Exception as e:
            snap["error"] = "audit cmd failed: %s" % e
    return snap


# --------------------------------------------------------------------------- #
# Result writing
# --------------------------------------------------------------------------- #
def write_result(reward_dir: str, reward: float, result: Dict[str, Any]) -> None:
    os.makedirs(reward_dir, exist_ok=True)
    with open(os.path.join(reward_dir, "reward.txt"), "w") as fh:
        fh.write(str(float(reward)))
    result["reward"] = float(reward)
    with open(os.path.join(reward_dir, "result.json"), "w") as fh:
        json.dump(result, fh, indent=2, default=str)


def infra_error_result(reward_dir: str, reason: str,
                       config_snap: Dict[str, Any],
                       audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    result = {
        "infra_error": True,
        "reason": reason,
        "slos_pass": False,
        "findings_pass": False,
        "config": config_snap,
        "audit": audit,
    }
    write_result(reward_dir, 0.0, result)
    print("SOAK: INFRA_ERROR reward=0.0 reason=%s" % reason)
    return result


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def run(cfg: SoakConfig, reward_dir: str, findings_path: str,
        audit_cmd: Optional[str], audit_file: Optional[str]) -> Dict[str, Any]:
    config_snap = asdict(cfg)
    # Never echo secrets from bootstrap headers into the result verbatim beyond
    # what the task author put in config; that's the author's call.

    if httpx is None:
        return infra_error_result(reward_dir, "httpx not importable in verifier env",
                                  config_snap)

    audit = capture_audit(audit_cmd, audit_file)

    limits = httpx.Limits(max_connections=cfg.workers + 4,
                          max_keepalive_connections=cfg.workers + 4)
    with httpx.Client(limits=limits, timeout=cfg.request_timeout_s) as client:
        # 1) Health gate — explicit infra error if never healthy.
        if not wait_healthy(client, cfg):
            return infra_error_result(
                reward_dir,
                "target %s never became healthy within %.0fs (health_path=%s)"
                % (cfg.target, cfg.health_timeout_s, cfg.health_path),
                config_snap, audit)

        # 2) Optional bootstrap (auth), best-effort.
        ctx = run_bootstrap(client, cfg)

        # 3) Drive load through warmup + soak.
        samples = drive_load(client, cfg, ctx)

    # 4) Grade SLOs over the soak window.
    slo = grade_slos(samples, cfg)

    # If soak produced no measurable samples at all, that's infra, not model.
    if slo["overall"]["offered"] == 0:
        return infra_error_result(
            reward_dir, "no requests completed during soak window",
            config_snap, audit)

    # 5) Findings gate.
    findings = grade_findings(findings_path, cfg.findings)

    infra_error = False
    slos_pass = bool(slo["slos_pass"])
    findings_pass = bool(findings["pass"])
    reward = 1.0 if (slos_pass and findings_pass and not infra_error) else 0.0

    result = {
        "infra_error": infra_error,
        "reward": reward,
        "slos_pass": slos_pass,
        "findings_pass": findings_pass,
        "slo": slo,
        "findings": findings,
        "audit": audit,
        "config": config_snap,
        "sample_total": len(samples),
    }
    write_result(reward_dir, reward, result)

    # 6) Log the reward basis to stdout.
    print("SOAK: reward=%.1f  slos_pass=%s  findings_pass=%s  infra_error=%s"
          % (reward, slos_pass, findings_pass, infra_error))
    ov = slo["overall"]
    print("  overall: offered=%d goodput=%.3f error_rate=%.3f p95=%sms p99=%sms"
          % (ov["offered"], ov["goodput_ratio"], ov["error_rate"],
             ov["latency_p95_ms"], ov["latency_p99_ms"]))
    for name, g in slo["per_driver"].items():
        print("  driver %-16s offered=%d goodput=%.3f error_rate=%.3f pass=%s"
              % (name, g["offered"], g["goodput_ratio"], g["error_rate"], g["pass"]))
    if slo["reasons"]:
        print("  SLO reasons: " + "; ".join(slo["reasons"]))
    if not findings_pass:
        print("  FINDINGS reasons: " + "; ".join(findings["reasons"]))
    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Soak / SLO verifier (P3)")
    p.add_argument("--target", help="SUT base URL, e.g. http://conduit.web.1:5000")
    p.add_argument("--config", required=True, help="path to soak config JSON")
    p.add_argument("--reward-dir", default=None,
                   help="override ${REWARD_DIR:-/logs/verifier}")
    p.add_argument("--findings", default=None,
                   help="path to findings.json (default /workspace/findings.json)")
    p.add_argument("--audit-cmd", default=None,
                   help="shell cmd to capture the final deploy config (recorded)")
    p.add_argument("--audit-file", default=None,
                   help="path to a pre-captured deploy snapshot (recorded)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    reward_dir = (args.reward_dir
                  or os.environ.get("REWARD_DIR")
                  or "/logs/verifier")
    findings_path = (args.findings
                     or os.environ.get("FINDINGS_PATH")
                     or "/workspace/findings.json")

    # Load config INSIDE the guarded path so a malformed task config still
    # produces an explicit infra_error result (never a silent no-reward crash).
    try:
        cfg = SoakConfig.load(args.config)
        if args.target:
            cfg.target = args.target
        if not cfg.target:
            infra_error_result(reward_dir,
                               "no --target and none in config", {})
            return 0
    except Exception as e:
        import traceback
        traceback.print_exc()
        infra_error_result(reward_dir,
                           "could not load soak config %s: %s" % (args.config, e),
                           {})
        return 0

    try:
        run(cfg, reward_dir, findings_path, args.audit_cmd, args.audit_file)
    except Exception as e:  # never let the verifier crash without a reward
        import traceback
        traceback.print_exc()
        infra_error_result(reward_dir,
                           "verifier raised: %s" % e,
                           asdict(cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
