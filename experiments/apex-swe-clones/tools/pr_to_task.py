#!/usr/bin/env python3
"""PR -> verifier auto-deriver (P0 of the DevOps-task pipeline).

Given a merged GitHub PR and a container image whose /app/repo is the repo at the PR's
PARENT state (e.g. the APEX agent image), this:
  1. fetches the PR's unified diff,
  2. SPLITS it into golden.patch (product code) vs test.patch (test files),
  3. derives FAIL_TO_PASS / PASS_TO_PASS EMPIRICALLY by running the test command in the image:
       - apply test.patch only            -> node-ids that FAIL  = F2P candidates
       - apply test.patch + golden.patch   -> those must now PASS (confirms gold fixes them)
       - node-ids that PASS in both        = P2P (regression guard)
  4. emits golden.patch, test.patch, test_metadata.json into an output dir.

Never guesses test ids; they come from real runs. Low yield is expected and fine — a PR whose
tests are flaky/network-bound won't produce a clean F2P set and is dropped upstream by the gate.

Usage:
  pr_to_task.py --repo paperless-ngx/paperless-ngx --pr 10555 \
                --image paperless-main:local \
                --test-command 'cd /app/repo && uv run pytest src/documents/tests/conftest.py src/documents/tests/test_workflows.py -v' \
                --out /tmp/pngx10555-derived
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, tempfile, pathlib

TEST_PATH_RE = re.compile(r"(^|/)(tests?)(/|$)|(^|/)test_[^/]*\.py$|(^|/)conftest\.py$|_test\.py$")


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, **kw)


def is_test_file(path: str) -> bool:
    return bool(TEST_PATH_RE.search(path))


def fetch_pr_diff(repo: str, pr: str) -> str:
    r = sh(["gh", "api", f"repos/{repo}/pulls/{pr}",
            "-H", "Accept: application/vnd.github.v3.diff"])
    if r.returncode != 0:
        sys.exit(f"gh diff fetch failed: {r.stderr[:400]}")
    return r.stdout


def split_diff(diff: str) -> tuple[str, str, list[str], list[str]]:
    """Split a unified diff into (golden, test) patch text by destination path."""
    # Each file section starts at a 'diff --git a/... b/...' line.
    sections = re.split(r"(?=^diff --git )", diff, flags=re.M)
    golden, test, gfiles, tfiles = [], [], [], []
    for sec in sections:
        if not sec.strip():
            continue
        m = re.search(r"^\+\+\+ b/(.+)$", sec, flags=re.M) or re.search(r"^diff --git a/\S+ b/(\S+)", sec, flags=re.M)
        path = m.group(1).strip() if m else "?"
        if is_test_file(path):
            test.append(sec); tfiles.append(path)
        else:
            golden.append(sec); gfiles.append(path)
    return "".join(golden), "".join(test), gfiles, tfiles


def nodeid_to_dotted(nodeid: str) -> str:
    """pytest 'path/to/file.py::Class::method' -> 'path.to.file.Class::method'."""
    parts = nodeid.split("::")
    mod = parts[0]
    if mod.endswith(".py"):
        mod = mod[:-3]
    mod = mod.replace("/", ".")
    rest = parts[1:]
    if not rest:
        return mod
    if len(rest) == 1:
        return f"{mod}::{rest[0]}"
    # class + method (+ params): module.Class::method[...]
    return f"{mod}.{rest[0]}::" + "::".join(rest[1:])


def parse_pytest(out: str) -> dict[str, str]:
    """Map dotted-node-id -> status from pytest output. Handles both the verbose per-test
    line ('path.py::node PASSED [ 12%]') and the short-summary line ('FAILED path.py::node ...').
    FAILED/ERROR always wins over PASSED for the same node (e.g. fail-in-body + error-in-teardown)."""
    res = {}
    def record(nid_raw, status):
        nid = nodeid_to_dotted(nid_raw)
        if status in ("FAILED", "ERROR") or nid not in res:
            res[nid] = status
    for line in out.splitlines():
        m = re.match(r"^(\S+\.py::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED)\b", line)  # verbose
        if m:
            record(m.group(1), m.group(2)); continue
        m = re.match(r"^(PASSED|FAILED|ERROR)\s+(\S+\.py::\S+)", line)            # summary
        if m:
            record(m.group(2), m.group(1))
    return res


def run_in_image(image: str, patches: dict[str, str], test_cmd: str) -> dict[str, dict]:
    """Run two phases (test-only, both) in the image; return parsed pytest results."""
    with tempfile.TemporaryDirectory() as td:
        for name, txt in patches.items():
            pathlib.Path(td, name).write_text(txt)
        # In-container: reset repo, apply patches per phase, run tests, capture.
        script = f"""
set +e
cd /app/repo
reset() {{ git checkout -- . >/dev/null 2>&1; git clean -fdq >/dev/null 2>&1; }}
apply() {{ git apply "$1" 2>/dev/null || patch -p1 -F3 < "$1" >/dev/null 2>&1; }}

reset
apply /patches/test.patch
echo '###PHASE testonly'
{test_cmd}
reset

apply /patches/test.patch
apply /patches/golden.patch
echo '###PHASE both'
{test_cmd}
reset
"""
        r = sh(["docker", "run", "--rm", "-v", f"{td}:/patches:ro", image, "bash", "-lc", script],
               timeout=2400)
        out = r.stdout + "\n" + r.stderr
    run_in_image.raw = out  # stash for the caller to persist
    phases = {}
    cur = None
    buf = []
    for line in out.splitlines():
        m = re.match(r"^###PHASE (\w+)", line)
        if m:
            if cur:
                phases[cur] = parse_pytest("\n".join(buf))
            cur, buf = m.group(1), []
        else:
            buf.append(line)
    if cur:
        phases[cur] = parse_pytest("\n".join(buf))
    return phases


def derive_f2p_p2p(phases: dict[str, dict]) -> tuple[list[str], list[str], dict]:
    testonly = phases.get("testonly", {})
    both = phases.get("both", {})
    f2p = sorted(n for n, s in testonly.items()
                 if s in ("FAILED", "ERROR") and both.get(n) == "PASSED")
    p2p = sorted(n for n, s in testonly.items()
                 if s == "PASSED" and both.get(n) == "PASSED")
    # diagnostics: tests that failed test-only but did NOT pass with gold (gold incomplete / flaky)
    unresolved = sorted(n for n, s in testonly.items()
                        if s in ("FAILED", "ERROR") and both.get(n) != "PASSED")
    return f2p, p2p, {"unresolved_after_gold": unresolved,
                      "n_testonly": len(testonly), "n_both": len(both)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", required=True)
    ap.add_argument("--image", required=True, help="image with /app/repo at the PR parent state")
    ap.add_argument("--test-command", required=True)
    ap.add_argument("--test-files", nargs="*", default=[])
    # Repos often ship --cov / xdist (-n auto) in addopts whose workers crash here and emit no
    # parseable test lines. Clear addopts + disable xdist/cache so listed tests run plainly.
    ap.add_argument("--pytest-args", default="-v -o addopts= -p no:cacheprovider -p no:xdist")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    print(f"[1/4] fetching PR diff {a.repo}#{a.pr} ...")
    diff = fetch_pr_diff(a.repo, a.pr)
    golden, test, gfiles, tfiles = split_diff(diff)
    print(f"      golden files: {gfiles}")
    print(f"      test files:   {tfiles}")
    pathlib.Path(a.out, "golden.patch").write_text(golden)
    pathlib.Path(a.out, "test.patch").write_text(test)

    print(f"[2/4] running empirical F2P derivation in {a.image} (2 phases) ...")
    hardened_cmd = f"{a.test_command} {a.pytest_args}".strip()
    phases = run_in_image(a.image, {"golden.patch": golden, "test.patch": test}, hardened_cmd)
    pathlib.Path(a.out, "_phases_raw.txt").write_text(getattr(run_in_image, "raw", ""))
    print(f"      parsed: testonly={len(phases.get('testonly',{}))} both={len(phases.get('both',{}))}")

    print("[3/4] deriving FAIL_TO_PASS / PASS_TO_PASS ...")
    f2p, p2p, diag = derive_f2p_p2p(phases)
    print(f"      F2P={len(f2p)}  P2P={len(p2p)}  unresolved={len(diag['unresolved_after_gold'])}")
    if diag["unresolved_after_gold"]:
        print(f"      WARN unresolved-after-gold (gold incomplete or flaky): {diag['unresolved_after_gold'][:5]}")

    meta = {
        "test_framework": "pytest",
        "test_command": a.test_command,
        "test_files": a.test_files or tfiles,
        "num_test_files": len(a.test_files or tfiles),
        "language": "python",
        "FAIL_TO_PASS": f2p,
        "PASS_TO_PASS": p2p,
    }
    pathlib.Path(a.out, "test_metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    pathlib.Path(a.out, "_diagnostics.json").write_text(json.dumps(diag, indent=2) + "\n")
    print(f"[4/4] wrote {a.out}/{{golden.patch,test.patch,test_metadata.json}}")
    if not f2p:
        print("      RESULT: NO clean F2P — drop this PR (flaky/env-coupled/no failing test).")
        sys.exit(2)
    print("      RESULT: derived OK.")


if __name__ == "__main__":
    main()
