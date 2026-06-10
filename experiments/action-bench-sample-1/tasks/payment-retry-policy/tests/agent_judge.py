#!/usr/bin/env python3
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
LOG_DIR = Path(os.environ.get("VERIFIER_LOG_DIR", "/logs/verifier"))
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    LOG_DIR = Path(os.environ.get("TMPDIR", "/tmp")) / "verifier"
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def write_reward(value):
    payload = {"reward": value}
    write_json(LOG_DIR / "reward.json", payload)
    (LOG_DIR / "reward.txt").write_text(str(value) + "\n")
    for path in (Path("reward.json"), Path("/verifier/reward.json")):
        try:
            write_json(path, payload)
        except Exception:
            pass
    for path in (Path("reward.txt"), Path("/verifier/reward.txt")):
        try:
            path.write_text(str(value) + "\n")
        except Exception:
            pass


def fail_closed(error, extra=None):
    report = {
        "status": "error",
        "error": str(error),
        "judge_model": os.environ.get("JUDGE_MODEL", "cursor/composer"),
        "mode": reward_mode(),
        "reward": 0,
    }
    if extra:
        report.update(extra)
    write_reward(0)
    write_json(LOG_DIR / "judge_report.json", report)
    return 0


def reward_mode():
    if os.environ.get("ALLOW_FRACTIONAL_LLM_REWARD") == "1":
        return "continuous"
    mode = os.environ.get("REWARD_MODE", "binary").strip().lower()
    return "continuous" if mode == "continuous" else "binary"


def load_json(path):
    return json.loads(Path(path).read_text())


def build_prompt(rubric, evidence):
    prompt = (TESTS_DIR / "judge_prompt.md").read_text()
    return (
        prompt
        + "\n\nTRUSTED RUBRIC JSON:\n"
        + json.dumps(rubric, indent=2, sort_keys=True)
        + "\n\nUNTRUSTED EVIDENCE JSON:\n<EVIDENCE>\n"
        + json.dumps(evidence, indent=2, sort_keys=True, default=str)
        + "\n</EVIDENCE>\n"
    )


def find_cursor_agent():
    found = shutil.which("cursor-agent")
    if found:
        return found
    candidates = [
        Path("/usr/local/bin/cursor-agent"),
        Path("/opt/cursor-judge/dist-package/cursor-agent"),
        Path.home() / ".local/bin/cursor-agent",
        Path("/root/.local/bin/cursor-agent"),
        Path("/home/agent/.local/bin/cursor-agent"),
    ]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


CURSOR_AGENT_VERSION = "2026.06.04-5fd875e"
CURSOR_AGENT_SHA256 = "5425aab29f8a01d377de3dc7f7455739ad59829e0879ea0c4296bd9eec520300"
CURSOR_AGENT_INSTALL = (
    'set -e; curl -fsSL "https://downloads.cursor.com/lab/{v}/linux/x64/agent-cli-package.tar.gz" '
    '-o /tmp/cursor-agent.tgz; echo "{sha}  /tmp/cursor-agent.tgz" | sha256sum -c -; '
    "mkdir -p /opt/cursor-judge; tar -xzf /tmp/cursor-agent.tgz -C /opt/cursor-judge; "
    "rm -f /tmp/cursor-agent.tgz; "
    "ln -sf /opt/cursor-judge/dist-package/cursor-agent /usr/local/bin/cursor-agent"
).format(v=CURSOR_AGENT_VERSION, sha=CURSOR_AGENT_SHA256)


def ensure_cursor_agent():
    binary = find_cursor_agent()
    if binary:
        return binary
    install = subprocess.run(
        ["bash", "-c", CURSOR_AGENT_INSTALL],
        capture_output=True,
        text=True,
        timeout=int(os.environ.get("JUDGE_INSTALL_TIMEOUT_SEC", "300")),
    )
    (LOG_DIR / "judge_install.log").write_text(install.stdout + "\n" + install.stderr)
    if install.returncode != 0:
        raise RuntimeError("cursor-agent install failed with return code {}".format(install.returncode))
    binary = find_cursor_agent()
    if not binary:
        raise RuntimeError("cursor-agent not found after install")
    return binary


def cursor_agent_call(prompt, model):
    api_key = os.environ.get("CURSOR_API_KEY")
    if not api_key:
        raise RuntimeError("CURSOR_API_KEY not set")
    binary = ensure_cursor_agent()
    cli_model = model.split("/")[-1]
    env = dict(os.environ)
    env["CURSOR_API_KEY"] = api_key
    timeout = int(os.environ.get("JUDGE_TIMEOUT_SEC", "240"))
    with tempfile.TemporaryDirectory(prefix="llm-judge-") as tmp:
        proc = subprocess.run(
            [binary, "--print", "--trust", "--output-format=text", "--model", cli_model, "--", prompt],
            cwd=tmp,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    (LOG_DIR / "judge_stdout.log").write_text(proc.stdout)
    (LOG_DIR / "judge_stderr.log").write_text(proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError("cursor-agent judge failed with return code {}".format(proc.returncode))
    return proc.stdout, proc.stderr


def http_call(prompt, model):
    api_key = os.environ.get("CURSOR_API_KEY")
    if not api_key:
        raise RuntimeError("CURSOR_API_KEY not set")
    if os.environ.get("JUDGE_API_KEY"):
        raise RuntimeError("JUDGE_API_KEY is not supported; use CURSOR_API_KEY")

    url = os.environ["CURSOR_API_URL"]
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + api_key}
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
    ).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=int(os.environ.get("JUDGE_TIMEOUT_SEC", "120"))) as response:
        data = json.loads(response.read().decode())
    if isinstance(data, str):
        return data, ""
    if isinstance(data, dict):
        for key in ("output_text", "text", "content", "response"):
            if isinstance(data.get(key), str):
                return data[key], ""
        choices = data.get("choices")
        if choices and isinstance(choices, list):
            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            content = message.get("content") or choices[0].get("text")
            if isinstance(content, str):
                return content, ""
    return json.dumps(data), ""


def command_call(cmd, prompt):
    timeout = int(os.environ.get("JUDGE_TIMEOUT_SEC", "120"))
    with tempfile.TemporaryDirectory(prefix="llm-judge-") as tmp:
        proc = subprocess.run(
            cmd,
            cwd=tmp,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    (LOG_DIR / "judge_stdout.log").write_text(proc.stdout)
    (LOG_DIR / "judge_stderr.log").write_text(proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError("judge command failed with return code {}".format(proc.returncode))
    return proc.stdout, proc.stderr


def call_judge(prompt, model):
    if os.environ.get("ALLOW_JUDGE_STUB") == "1":
        if os.environ.get("JUDGE_RESPONSE_FILE"):
            return Path(os.environ["JUDGE_RESPONSE_FILE"]).read_text(), ""
        if os.environ.get("JUDGE_RESPONSE_JSON"):
            return os.environ["JUDGE_RESPONSE_JSON"], ""
    if os.environ.get("ALLOW_JUDGE_COMMAND") == "1" and os.environ.get("JUDGE_COMMAND"):
        return command_call(shlex.split(os.environ["JUDGE_COMMAND"]), prompt)
    if os.environ.get("CURSOR_API_URL"):
        stdout, stderr = http_call(prompt, model)
        (LOG_DIR / "judge_stdout.log").write_text(stdout)
        (LOG_DIR / "judge_stderr.log").write_text(stderr)
        return stdout, stderr
    return cursor_agent_call(prompt, model)


def extract_json_object(raw):
    text = raw.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        try:
            return json.loads("\n".join(lines).strip())
        except Exception:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("no JSON object found in judge output")


def normalize_violation(violation):
    if isinstance(violation, str):
        return violation
    if isinstance(violation, dict):
        parts = []
        for key in ("type", "criterion", "id", "detail", "reason", "description"):
            value = violation.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        if parts:
            return ": ".join(parts)
        return json.dumps(violation, sort_keys=True)
    return str(violation)


def validate_judge_json(raw, rubric):
    try:
        data = extract_json_object(raw)
    except Exception as exc:
        raise ValueError("judge returned malformed JSON: {}".format(exc))
    if not isinstance(data, dict):
        raise ValueError("judge JSON must be an object")
    if not isinstance(data.get("passed"), bool):
        raise ValueError("passed must be boolean")
    if not isinstance(data.get("judge_score"), (int, float)) or not 0 <= data["judge_score"] <= 1:
        raise ValueError("judge_score must be a number in [0,1]")
    if data.get("verdict") not in ("pass", "partial", "fail"):
        raise ValueError("verdict must be pass, partial, or fail")
    if not isinstance(data.get("criteria"), list):
        raise ValueError("criteria must be a list")
    if not isinstance(data.get("summary"), str) or not data["summary"].strip():
        raise ValueError("summary must be a non-empty string")
    if not isinstance(data.get("violations"), list):
        raise ValueError("violations must be a list")
    data["violations"] = [normalize_violation(v) for v in data["violations"]]

    expected = {c["id"]: c for c in rubric["criteria"]}
    seen = {}
    for criterion in data["criteria"]:
        if not isinstance(criterion, dict):
            raise ValueError("each criterion must be an object")
        cid = criterion.get("id")
        if not isinstance(cid, str):
            raise ValueError("criterion id must be a string")
        if criterion.get("status") not in ("pass", "partial", "fail"):
            raise ValueError("criterion {} has invalid status".format(cid))
        if not isinstance(criterion.get("score"), (int, float)) or not 0 <= criterion["score"] <= 1:
            raise ValueError("criterion {} score must be in [0,1]".format(cid))
        if not isinstance(criterion.get("reason"), str) or not criterion["reason"].strip():
            raise ValueError("criterion {} reason must be non-empty".format(cid))
        seen[cid] = criterion
    missing = sorted(set(expected) - set(seen))
    if missing:
        raise ValueError("judge criteria missing ids: {}".format(", ".join(missing)))
    return data


def derive_reward(judge, rubric):
    policy = rubric.get("binary_reward_policy", {})
    mandatory_threshold = float(policy.get("mandatory_threshold", 0.9))
    pass_threshold = float(policy.get("pass_threshold", 0.70))
    criteria_by_id = {c["id"]: c for c in judge["criteria"]}
    weighted = 0.0
    total_weight = 0.0
    mandatory_failures = []
    criterion_results = []
    for rubric_criterion in rubric["criteria"]:
        cid = rubric_criterion["id"]
        judged = criteria_by_id[cid]
        weight = float(rubric_criterion.get("weight", 0))
        score = float(judged["score"])
        total_weight += weight
        weighted += weight * score
        mandatory = bool(rubric_criterion.get("mandatory"))
        passed = judged["status"] == "pass" and score >= mandatory_threshold
        if mandatory and not passed:
            mandatory_failures.append(cid)
        criterion_results.append(
            {
                "id": cid,
                "mandatory": mandatory,
                "weight": weight,
                "score": score,
                "status": judged["status"],
                "mandatory_passed": passed if mandatory else None,
            }
        )
    judge_score = round(weighted / total_weight, 4) if total_weight else 0.0
    anti_cheat_ok = len(judge.get("violations", [])) == 0
    mandatory_ok = not mandatory_failures
    mode = reward_mode()
    if not mandatory_ok or not anti_cheat_ok:
        reward = 0
    elif mode == "continuous":
        reward = judge_score
    else:
        reward = 1 if judge_score >= pass_threshold else 0
    return {
        "mode": mode,
        "reward": reward,
        "code_derived_judge_score": judge_score,
        "llm_reported_judge_score": judge.get("judge_score"),
        "pass_threshold": pass_threshold,
        "mandatory_threshold": mandatory_threshold,
        "mandatory_ok": mandatory_ok,
        "mandatory_failures": mandatory_failures,
        "anti_cheat_ok": anti_cheat_ok,
        "violations": judge.get("violations", []),
        "criterion_results": criterion_results,
    }


def main():
    model = os.environ.get("JUDGE_MODEL", "cursor/composer")
    if model != "cursor/composer" and os.environ.get("ALLOW_NON_CURSOR_JUDGE") != "1":
        return fail_closed("judge model {} is not cursor/composer".format(model))
    try:
        rubric = load_json(TESTS_DIR / "rubric.json")
        evidence_path = LOG_DIR / "evidence.json"
        evidence = load_json(evidence_path) if evidence_path.exists() else {"status": "missing"}
        prompt = build_prompt(rubric, evidence)
        raw, _stderr = call_judge(prompt, model)
        judge = validate_judge_json(raw, rubric)
        derived = derive_reward(judge, rubric)
        report = {
            "status": "ok",
            "judge_model": model,
            "raw_judge_json": judge,
            **derived,
        }
        if abs(float(judge.get("judge_score", 0)) - float(derived["code_derived_judge_score"])) > 0.001:
            report["score_discrepancy"] = "judge-reported judge_score differed from code-derived weighted score; code-derived score was used"
        write_reward(derived["reward"])
        write_json(LOG_DIR / "judge_report.json", report)
        return 0
    except Exception as exc:
        return fail_closed(exc)


if __name__ == "__main__":
    sys.exit(main())
