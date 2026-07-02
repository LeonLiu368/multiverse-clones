"""Task archetypes — the diversity layer.

Real SWE isn't just "read the buried context, then patch." It's deployment, optimization, incident
response, *and* correctness fixes. Each archetype maps a discovered incident to a DIFFERENT task
shape — its own instruction, verifier, required surfaces, and how it's proven — so one incident
stream yields diverse tasks instead of one mono-archetype.

An archetype is chosen per candidate (classify) and drives spec_from_candidate + the verifier.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Archetype:
    name: str
    kind: str                     # observability | deployment | optimization | incident
    verifier_kind: str            # pytest_pr | module_check | build_check | metric | readback
    surfaces: List[str]           # evidence surfaces the task typically needs
    instruction: str              # symptom-level prompt (names the work, not the answer)
    grounds: str = ""             # the SWE capability it exercises
    needs_code: bool = True       # does it ship an SUT bundle + code oracle?
    tags: List[str] = field(default_factory=list)


CODE_FIX = Archetype(
    "code_fix", "observability", "pytest_pr", ["github", "logfire", "slack"],
    "A bug reached production. Use the telemetry, chat, and codebase to find the root cause and fix "
    "it. Your fix must make the failing tests pass without breaking the others.",
    grounds="correctness under buried context", tags=["bugfix", "tests"])

DEPLOYMENT = Archetype(
    "deployment", "deployment", "build_check", ["github", "logfire", "slack"],
    "The build/deploy pipeline is failing on the default branch. Diagnose why it broke and fix the "
    "code or config so the pipeline (build + checks) passes again.",
    grounds="deployment / release engineering", tags=["ci", "config", "deploy"])

OPTIMIZATION = Archetype(
    "optimization", "optimization", "metric", ["github", "logfire"],
    "A part of the system is too slow or too expensive. Profile it and improve the target metric, "
    "keeping all existing behavior correct (the regression tests must still pass).",
    grounds="optimization under a measured objective", tags=["perf", "cost", "latency"])

INCIDENT_RESPONSE = Archetype(
    "incident_response", "incident", "readback", ["logfire", "slack", "linear", "github"],
    "You are on call and an incident is active. Diagnose the root cause from the available surfaces "
    "(logs, chat, tickets, code) and record your findings — the culprit service/change and the fix "
    "— and, where the tools allow, mitigate it.",
    grounds="incident response + tool usage", needs_code=False, tags=["oncall", "diagnosis"])

ARCHETYPES = {a.name: a for a in (CODE_FIX, DEPLOYMENT, OPTIMIZATION, INCIDENT_RESPONSE)}

_OPT = re.compile(r"\b(optimi|perf(ormance)?|latency|speed[ -]?up|throughput|cache|reduce|faster|"
                  r"slow|memory|footprint|cost|N\+1|index)\b", re.I)
_DIAGNOSIS_FEEDS = {"logfire_anomaly", "slack_incident", "linear_sev"}


def classify(cand: Dict[str, Any]) -> Archetype:
    """Pick the archetype for a candidate from its feed + signal — the routing that gives diversity."""
    feed = cand.get("feed", "")
    title = cand.get("title", "")
    if feed == "github_ci":
        return DEPLOYMENT                              # red->green CI = fix the deploy/build (E2E oracle)
    if feed == "github_revert":
        if _OPT.search(title):
            return OPTIMIZATION                        # a perf/cost fix -> optimization (metric oracle)
        return CODE_FIX                                # a bugfix -> correctness (tests oracle)
    if feed in _DIAGNOSIS_FEEDS:
        return INCIDENT_RESPONSE                       # logfire/slack/linear -> diagnose + mitigate
    return CODE_FIX
