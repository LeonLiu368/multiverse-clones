from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import FakePlaneBackend, backend_for
from .config import Config, load_config, set_config_value
from .demo import run_payments_triage, transcript
from .errors import (
    AUTH_CONFIG,
    SUCCESS,
    USER_ERROR,
    UnsupportedCommandError,
    WorldIssuesError,
)
from .git import pr_receipt, safe_branch_name
from .jql import parse_jql
from .models import minimal_issue, mutation_receipt
from .output import emit, emit_error
from .plane import bootstrap_plane, detect_capabilities, doctor as plane_doctor, local_doctor
from .runtime import grade_task, redact_file, runtime_doctor, runtime_status
from .seed import apply_seed, reset_seed, verify_seed
from .snapshot import diff_snapshots, load_snapshot, save_receipt, save_snapshot, snapshot_exists



AGENT_MODE_BLOCKED = {
    ("seed",),
    ("snapshot",),
    ("demo",),
    ("plane",),
    ("runtime", "grade"),
    ("runtime", "redact"),
    ("runtime", "doctor"),
    ("runtime", "status"),
    ("doctor",),
    ("auth", "doctor"),
}


HELP_TEXT = {
    "linear": """linear - local Linear-compatible issue tracker

Useful commands:
  linear issue mine --json
  linear issue search "query terms" --json
  linear issue query --assignee me --state Todo --json
  linear issue view <ISSUE> --comments --links --attachments --json
  linear issue start [ISSUE] --json
  linear issue comment add <ISSUE> --body "..." --json
  linear issue commit-link <ISSUE> <sha> --json
  linear issue pr <ISSUE> --json
  linear state list --json
""",
    "jira": """jira - local Jira-compatible issue tracker

Useful commands:
  jira jql "assignee = me AND status != Done" --json
  jira issue view <ISSUE> --comments --links --attachments --json
  jira issue transition <ISSUE> "In Review" --json
  jira issue comment add <ISSUE> --body "..." --json
  jira issue commit-link <ISSUE> <sha> --json
""",
    "world-issues": """world-issues - ticketvector administrative CLI

Agent mode disables admin/runtime commands. Use linear or jira for task work.
""",
}


def agent_mode_enabled() -> bool:
    return os.environ.get("WORLD_ISSUES_AGENT_MODE", "").lower() in {"1", "true", "yes", "on"}


def enforce_agent_mode(program: str, args: list[str]) -> None:
    if not agent_mode_enabled() or program != "world-issues":
        return
    head = tuple(args[:2]) if len(args) >= 2 else tuple(args[:1])
    if any(head == blocked or head[: len(blocked)] == blocked for blocked in AGENT_MODE_BLOCKED):
        raise UnsupportedCommandError("world-issues admin/runtime commands are disabled in agent mode")


@dataclass
class Options:
    fmt: str = "plain"
    fields: list[str] | None = None
    limit: int = 50
    cursor: str | None = None
    quiet: bool = False
    no_input: bool = False
    backend: str | None = None
    state_file: str | None = None


def main_world_issues() -> None:
    raise SystemExit(run("world-issues", sys.argv[1:]))


def main_linear() -> None:
    raise SystemExit(run("linear", sys.argv[1:]))


def main_jira() -> None:
    raise SystemExit(run("jira", sys.argv[1:]))


def main() -> None:
    program = Path(sys.argv[0]).name
    if program not in {"world-issues", "linear", "jira"}:
        program = "world-issues"
    raise SystemExit(run(program, sys.argv[1:]))


def run(program: str, argv: list[str]) -> int:
    opts, args = parse_options(argv)
    if any(arg in {"--help", "-h", "help"} for arg in args) or (not args and program in HELP_TEXT):
        print(help_text(program, args))
        return SUCCESS
    config = load_config()
    if opts.backend:
        config = Config(**{**config.__dict__, "backend": opts.backend})
    if opts.state_file:
        config = Config(**{**config.__dict__, "state_file": Path(opts.state_file)})
    if opts.fmt == "plain" and config.output in {"json", "markdown", "plain"}:
        opts.fmt = config.output
    try:
        enforce_agent_mode(program, args)
        backend = None if can_dispatch_without_backend(program, args) else backend_for(config)
        if program == "jira":
            value = dispatch_jira(args, opts, config, backend)
        elif program == "linear":
            value = dispatch_linear(args, opts, config, backend)
        else:
            value = dispatch_world(args, opts, config, backend)
        if value is not None:
            emit(value, fmt=opts.fmt, fields=opts.fields, quiet=opts.quiet)
        return SUCCESS
    except WorldIssuesError as exc:
        emit_error(exc.message, fmt=opts.fmt, code=exc.exit_code, detail=exc.detail)
        return exc.exit_code
    except FileNotFoundError as exc:
        emit_error(str(exc), fmt=opts.fmt, code=USER_ERROR)
        return USER_ERROR
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        emit_error(str(exc), fmt=opts.fmt, code=USER_ERROR)
        return USER_ERROR


def help_text(program: str, args: list[str]) -> str:
    if program in {"linear", "jira"} and args[:2] == ["issue", "help"]:
        return HELP_TEXT[program]
    if program in {"linear", "jira"} and args[:1] == ["issue"]:
        return HELP_TEXT[program]
    return HELP_TEXT.get(program, HELP_TEXT["world-issues"])


def parse_options(argv: list[str]) -> tuple[Options, list[str]]:
    opts = Options()
    args: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--json":
            opts.fmt = "json"
        elif arg == "--plain":
            opts.fmt = "plain"
        elif arg == "--markdown":
            opts.fmt = "markdown"
        elif arg == "--quiet":
            opts.quiet = True
        elif arg == "--no-input":
            opts.no_input = True
        elif arg in {"--fields", "--limit", "--cursor", "--backend", "--state-file"}:
            if i + 1 >= len(argv):
                raise WorldIssuesError(f"missing value for {arg}")
            value = argv[i + 1]
            if arg == "--fields":
                opts.fields = [part.strip() for part in value.split(",") if part.strip()]
            elif arg == "--limit":
                opts.limit = int(value)
            elif arg == "--cursor":
                opts.cursor = value
            elif arg == "--backend":
                opts.backend = value
            elif arg == "--state-file":
                opts.state_file = value
            i += 1
        else:
            args.append(arg)
        i += 1
    return opts, args


def can_dispatch_without_backend(program: str, args: list[str]) -> bool:
    if program != "world-issues" or not args:
        return False
    if args[0] == "config":
        return True
    if args[0] == "auth":
        command = args[1] if len(args) > 1 else "doctor"
        return command == "doctor"
    if args[0] == "plane":
        command = args[1] if len(args) > 1 else ""
        return command in {"bootstrap", "doctor"}
    if args[0] == "doctor":
        return True
    if args[0] == "runtime":
        command = args[1] if len(args) > 1 else "status"
        return command in {"doctor", "status", "redact", "agent-env"}
    return False


def dispatch_world(args: list[str], opts: Options, config: Config, backend: Any) -> Any:
    if not args:
        return {"name": "world-issues", "commands": ["auth", "config", "seed", "snapshot", "demo", "plane", "runtime", "doctor"]}
    if args[0] == "doctor":
        return local_doctor()
    if args[0] == "auth":
        return auth_command(args[1:], config, backend)
    if args[0] == "config":
        return config_command(args[1:], config)
    if args[0] == "seed":
        return seed_command(args[1:], backend)
    if args[0] == "snapshot":
        return snapshot_command(args[1:], backend)
    if args[0] == "demo":
        return demo_command(args[1:], opts, backend, config)
    if args[0] == "plane":
        return plane_command(args[1:], config, backend)
    if args[0] == "runtime":
        return runtime_command(args[1:], config, backend)
    return dispatch_linear(args, opts, config, backend)


def runtime_command(args: list[str], config: Config, backend: Any) -> Any:
    command = args[0] if args else "status"
    if command == "doctor":
        return runtime_doctor(config, backend)
    if command == "status":
        return runtime_status(config, backend)
    if command == "redact" and len(args) >= 2:
        return redact_file(args[1])
    if command == "grade":
        task = args[1] if len(args) >= 2 else "payments-webhook"
        return grade_task(task, backend)
    if command == "agent-env":
        from .runtime import write_agent_env

        return write_agent_env()
    raise UnsupportedCommandError("supported runtime commands: doctor, status, redact <file>, grade <task>, agent-env")


def plane_command(args: list[str], config: Config, backend: Any) -> Any:
    command = args[0] if args else "capabilities"
    if command == "bootstrap":
        method = option_value(args, "--method") or "auto"
        allow_db = "--allow-db-fallback" in args
        return bootstrap_plane(config, method=method, allow_db_fallback=allow_db)
    if command == "capabilities":
        if backend is None:
            backend = backend_for(Config(**{**config.__dict__, "backend": "plane"}))
        return detect_capabilities(backend)
    if command == "doctor":
        if backend is None:
            try:
                backend = backend_for(Config(**{**config.__dict__, "backend": "plane"}))
            except WorldIssuesError:
                backend = None
        return plane_doctor(config, backend)
    raise UnsupportedCommandError("supported plane commands: bootstrap, capabilities")


def auth_command(args: list[str], config: Config, backend: Any) -> Any:
    command = args[0] if args else "doctor"
    if command == "doctor":
        if config.backend == "plane":
            config.require_plane()
        return {
            "ok": True,
            "backend": config.backend,
            "config": config.redacted_dict(),
            "checks": {
                "base_url": bool(config.base_url) or config.backend == "fake",
                "api_key": bool(config.api_key) or config.backend == "fake",
                "workspace": bool(config.workspace),
                "project": bool(config.default_project),
            },
        }
    if command == "whoami":
        if hasattr(backend, "current_user"):
            return backend.current_user()
        raise UnsupportedCommandError("whoami is not wired for this Plane backend yet")
    raise UnsupportedCommandError(f"unsupported auth command: {command}")


def config_command(args: list[str], config: Config) -> Any:
    if not args:
        return config.redacted_dict()
    if args[0] == "show":
        return config.redacted_dict()
    if args[0] == "set" and len(args) >= 3:
        return {"ok": True, "config": set_config_value(args[1], args[2], config)}
    raise UnsupportedCommandError("supported config commands: show, set <key> <value>")


def seed_command(args: list[str], backend: Any) -> Any:
    if len(args) >= 2 and args[0] == "apply":
        return apply_seed(backend, args[1], backend_name=backend_name(backend))
    if len(args) >= 2 and args[0] == "reset":
        return reset_seed(backend, args[1], backend_name=backend_name(backend))
    if len(args) >= 2 and args[0] == "verify":
        return verify_seed(backend, args[1], backend_name=backend_name(backend))
    raise UnsupportedCommandError("supported seed commands: apply <path>, reset <path>, verify <path>")


def snapshot_command(args: list[str], backend: Any) -> Any:
    if len(args) >= 2 and args[0] == "save":
        path = save_snapshot(args[1], backend.snapshot())
        return {"ok": True, "action": "snapshot.save", "name": args[1], "path": str(path)}
    if len(args) >= 3 and args[0] == "diff":
        before = load_snapshot(args[1])
        after = load_snapshot(args[2]) if snapshot_exists(args[2]) else backend.snapshot()
        return diff_snapshots(before, after)
    raise UnsupportedCommandError("supported snapshot commands: save <name>, diff <before> <after>")


def demo_command(args: list[str], opts: Options, backend: Any, config: Config) -> Any:
    if len(args) >= 2 and args[0] == "run" and args[1] == "payments-triage":
        return run_payments_triage(backend, actor=config.actor, backend_name=backend_name(backend))
    if len(args) >= 2 and args[0] == "print-transcript" and args[1] == "payments-triage":
        run_data = run_payments_triage(backend, actor=config.actor, backend_name=backend_name(backend))
        if opts.fmt == "json":
            return {"ok": True, "transcript": transcript(run_data)}
        return transcript(run_data)
    raise UnsupportedCommandError("supported demo commands: run payments-triage, print-transcript payments-triage")


def dispatch_jira(args: list[str], opts: Options, config: Config, backend: Any) -> Any:
    if not args:
        return {"name": "jira", "commands": ["issue", "sprint", "epic", "project", "jql"]}
    if args[0] == "jql" and len(args) >= 2:
        parsed = parse_jql(" ".join(args[1:]))
        return backend.issue_list(filters=parsed.filters, limit=opts.limit, cursor=opts.cursor)
    if args[0] == "project":
        return project_command(args[1:], backend)
    if args[0] == "sprint":
        return cycle_command(args[1:], opts, backend, jira=True)
    if args[0] == "epic":
        return module_command(args[1:], opts, backend, jira=True)
    if args[0] == "issue":
        mapped = args[:]
        if len(mapped) > 1 and mapped[1] == "edit":
            mapped[1] = "update"
        if len(mapped) > 1 and mapped[1] == "clone":
            return clone_issue(mapped[2:], backend)
        if len(mapped) > 1 and mapped[1] == "link":
            mapped = ["issue", "link", "add", *mapped[2:]]
        return issue_command(mapped[1:], opts, config, backend)
    raise UnsupportedCommandError(f"unsupported jira command: {' '.join(args)}")


def dispatch_linear(args: list[str], opts: Options, config: Config, backend: Any) -> Any:
    if not args:
        return {"name": "linear", "commands": ["project", "state", "label", "issue", "cycle", "module"]}
    head = args[0]
    if head == "project":
        return project_command(args[1:], backend)
    if head == "state":
        return state_command(args[1:], backend)
    if head == "label":
        return label_command(args[1:], backend)
    if head == "issue":
        return issue_command(args[1:], opts, config, backend)
    if head == "cycle":
        return cycle_command(args[1:], opts, backend)
    if head == "module":
        return module_command(args[1:], opts, backend)
    raise UnsupportedCommandError(f"unsupported linear command: {' '.join(args)}")


def project_command(args: list[str], backend: Any) -> Any:
    command = args[0] if args else "list"
    if command == "list":
        return backend.project_list()
    if command == "view" and len(args) >= 2:
        return backend.project_view(args[1])
    if command == "members" and len(args) >= 2:
        return backend.project_view(args[1])["members"]
    if command == "create":
        name = option_value(args, "--name")
        key = option_value(args, "--key")
        if not name or not key:
            raise WorldIssuesError("project create requires --name and --key")
        return backend.create_project(name, key)
    if command in {"update", "archive"}:
        raise UnsupportedCommandError(f"project {command} is not wired for real persistence yet")
    raise UnsupportedCommandError("supported project commands: list, view, create, members")


def state_command(args: list[str], backend: Any) -> Any:
    command = args[0] if args else "list"
    if command == "list":
        return backend.list_states()
    if command == "create":
        name = option_value(args, "--name")
        category = option_value(args, "--category")
        if not name or not category:
            raise WorldIssuesError("state create requires --name and --category")
        return backend.create_state(name, category)
    raise UnsupportedCommandError("supported state commands: list, create")


def label_command(args: list[str], backend: Any) -> Any:
    command = args[0] if args else "list"
    if command == "list":
        return backend.list_labels()
    if command == "create":
        name = option_value(args, "--name")
        if not name:
            raise WorldIssuesError("label create requires --name")
        return backend.create_label(name)
    raise UnsupportedCommandError("supported label commands: list, create")


def issue_command(args: list[str], opts: Options, config: Config, backend: Any) -> Any:
    if not args:
        args = ["list"]
    command = args[0]
    if command == "list":
        return backend.issue_list(limit=opts.limit, cursor=opts.cursor)
    if command == "mine":
        return backend.issue_mine(config.actor, limit=opts.limit, cursor=opts.cursor)
    if command == "search" and len(args) >= 2:
        return backend.issue_list(query=" ".join(args[1:]), limit=opts.limit, cursor=opts.cursor)
    if command == "query":
        return backend.issue_list(filters=query_filters(args), limit=opts.limit, cursor=opts.cursor)
    if command == "view" and len(args) >= 2:
        issue = backend.get_issue(args[1])
        if "--comments" in args:
            issue["comments"] = backend.list_comments(args[1])
        if "--links" in args:
            issue["links"] = backend.list_links(args[1])
        if "--attachments" in args:
            issue["attachments"] = backend.list_attachments(args[1])
        return issue
    if command == "create":
        title = option_value(args, "--title")
        if not title:
            raise WorldIssuesError("issue create requires --title")
        issue = backend.create_issue(
            title=title,
            description=option_value(args, "--description") or "",
            priority=option_value(args, "--priority") or "medium",
            assignee=option_value(args, "--assignee"),
            labels=multi_option(args, "--label"),
        )
        return mutation_receipt("issue.create", issue["identifier"], None, issue)
    if command == "update" and len(args) >= 2:
        return update_issue(args[1], args[2:], backend)
    if command == "delete" and len(args) >= 2:
        before, after = backend.delete_issue(args[1])
        return mutation_receipt("issue.delete", args[1], minimal_issue(before), after)
    if command == "transition" and len(args) >= 3:
        before, after = backend.update_issue(args[1], state=" ".join(args[2:]))
        return mutation_receipt("issue.transition", args[1], minimal_issue(before), minimal_issue(after))
    if command == "assign" and len(args) >= 3:
        issue = backend.get_issue(args[1])
        handles = sorted({user["handle"] for user in issue.get("assignees", [])} | {args[2]})
        before, after = backend.update_issue(args[1], assignees=handles)
        return mutation_receipt("issue.assign", args[1], minimal_issue(before), minimal_issue(after))
    if command == "unassign" and len(args) >= 3:
        issue = backend.get_issue(args[1])
        handles = [user["handle"] for user in issue.get("assignees", []) if user["handle"] != args[2]]
        before, after = backend.update_issue(args[1], assignees=handles)
        return mutation_receipt("issue.unassign", args[1], minimal_issue(before), minimal_issue(after))
    if command == "start":
        target = args[1] if len(args) >= 2 and not args[1].startswith("--") else first_mine(backend, config)
        return start_issue(target, args[2:], config, backend)
    if command == "done" and len(args) >= 2:
        before, after = backend.update_issue(args[1], state="Done")
        return mutation_receipt("issue.done", args[1], minimal_issue(before), minimal_issue(after))
    if command == "reopen" and len(args) >= 2:
        before, after = backend.update_issue(args[1], state="Todo")
        return mutation_receipt("issue.reopen", args[1], minimal_issue(before), minimal_issue(after))
    if command == "comment":
        return comment_command(args[1:], backend)
    if command == "link":
        return link_command(args[1:], backend)
    if command == "relation":
        return relation_command(args[1:], backend)
    if command == "subissue":
        raise UnsupportedCommandError("subissue commands are reserved for the Plane relation adapter")
    if command == "history" and len(args) >= 2:
        return backend.history_list(args[1])
    if command in {"attachments", "attachment"} and len(args) >= 2:
        return backend.list_attachments(args[1])
    if command == "attach" and len(args) >= 3:
        path = Path(args[2])
        attachment = backend.add_attachment(args[1], path.name, "application/octet-stream", size=safe_size(path))
        return mutation_receipt("issue.attach", args[1], None, attachment)
    if command == "branch" and len(args) >= 2:
        issue = backend.get_issue(args[1])
        return {"issue": args[1], "branch": safe_branch_name(issue["identifier"], issue["title"], config.actor)}
    if command == "pr" and len(args) >= 2:
        issue = backend.get_issue(args[1])
        create = "--create" in args
        pr = pr_receipt(issue, create=create)
        if create:
            raise UnsupportedCommandError("gh pr create is intentionally guarded; dry-run receipt is available without --create")
        receipt = mutation_receipt("issue.pr", args[1], None, None, dry_run=True, extra={"pr": pr})
        save_receipt(receipt)
        return receipt
    if command == "pr-link" and len(args) >= 3:
        link = backend.add_link(args[1], args[2], "Pull request")
        return mutation_receipt("issue.pr-link", args[1], None, link)
    if command == "commit-link" and len(args) >= 3:
        link = backend.add_link(args[1], f"commit:{args[2]}", f"Commit {args[2]}")
        return mutation_receipt("issue.commit-link", args[1], None, link, extra={"sha": args[2]})
    if command == "repo-link" and len(args) >= 3:
        link = backend.add_link(args[1], args[2], "Repository")
        return mutation_receipt("issue.repo-link", args[1], None, link)
    if command == "artifact" and len(args) >= 4 and args[1] == "add":
        link = backend.add_link(args[2], f"artifact://{args[3]}", Path(args[3]).name)
        return mutation_receipt("issue.artifact.add", args[2], None, link)
    if command == "label" and len(args) >= 4:
        return issue_label_command(args[1:], backend)
    raise UnsupportedCommandError(f"unsupported issue command: {' '.join(args)}")


def update_issue(identifier: str, args: list[str], backend: Any) -> Any:
    fields = {
        "title": option_value(args, "--title"),
        "description": option_value(args, "--description"),
        "priority": option_value(args, "--priority"),
        "state": option_value(args, "--state"),
    }
    labels = multi_option(args, "--label")
    if labels:
        fields["labels"] = labels
    before, after = backend.update_issue(identifier, **{k: v for k, v in fields.items() if v is not None})
    return mutation_receipt("issue.update", identifier, minimal_issue(before), minimal_issue(after))


def first_mine(backend: Any, config: Config) -> str:
    page = backend.issue_mine(config.actor, limit=1)
    if not page["results"]:
        raise WorldIssuesError("no assigned issue found")
    return page["results"][0]["identifier"]


def start_issue(identifier: str, args: list[str], config: Config, backend: Any) -> Any:
    issue = backend.get_issue(identifier)
    handles = sorted({user["handle"] for user in issue.get("assignees", [])} | {config.actor})
    before, after = backend.update_issue(identifier, state="In Progress", assignees=handles)
    branch = safe_branch_name(after["identifier"], after["title"], config.actor)
    checkout = "--checkout" in args
    if checkout:
        subprocess.run(["git", "checkout", "-b", branch], check=False)
    return mutation_receipt(
        "issue.start",
        identifier,
        minimal_issue(before),
        minimal_issue(after),
        extra={"branch": branch, "checkout_performed": checkout},
    )


def comment_command(args: list[str], backend: Any) -> Any:
    if len(args) >= 2 and args[0] == "list":
        return backend.list_comments(args[1])
    if len(args) >= 2 and args[0] == "add":
        issue = args[1]
        body = option_value(args, "--body")
        body_file = option_value(args, "--body-file")
        if body_file:
            body = Path(body_file).read_text(encoding="utf-8")
        if not body:
            raise WorldIssuesError("comment add requires --body or --body-file")
        comment = backend.add_comment(issue, body)
        return mutation_receipt("issue.comment.add", issue, None, comment, extra={"comment_id": comment["id"]})
    if args and args[0] in {"update", "delete"}:
        raise UnsupportedCommandError("comment update/delete is reserved for the Plane comment adapter")
    raise UnsupportedCommandError("supported comment commands: list <issue>, add <issue> --body/--body-file")


def link_command(args: list[str], backend: Any) -> Any:
    if len(args) >= 2 and args[0] == "list":
        return backend.list_links(args[1])
    if len(args) >= 2 and args[0] == "add":
        issue = args[1]
        url = option_value(args, "--url") or (args[2] if len(args) >= 3 else None)
        title = option_value(args, "--title") or "Link"
        if not url:
            raise WorldIssuesError("link add requires --url")
        link = backend.add_link(issue, url, title)
        return mutation_receipt("issue.link.add", issue, None, link)
    if args and args[0] == "delete":
        raise UnsupportedCommandError("link delete is reserved for the Plane link adapter")
    raise UnsupportedCommandError("supported link commands: list <issue>, add <issue> --url <url>")


def relation_command(args: list[str], backend: Any) -> Any:
    if len(args) >= 2 and args[0] == "list":
        return backend.list_relations(args[1])
    if len(args) >= 2 and args[0] == "add":
        issue = args[1]
        relation = None
        other = None
        for flag, name in [
            ("--blocks", "blocks"),
            ("--blocked-by", "blocked-by"),
            ("--duplicates", "duplicates"),
            ("--relates-to", "relates-to"),
        ]:
            other = option_value(args, flag)
            if other:
                relation = name
                break
        if not relation or not other:
            raise WorldIssuesError("relation add requires --blocks/--blocked-by/--duplicates/--relates-to")
        item = backend.add_relation(issue, relation, other)
        return mutation_receipt("issue.relation.add", issue, None, item)
    raise UnsupportedCommandError("supported relation commands: list <issue>, add <issue> --blocks <issue>")


def issue_label_command(args: list[str], backend: Any) -> Any:
    action, issue_id, label = args[0], args[1], args[2]
    issue = backend.get_issue(issue_id)
    labels = {item["name"] for item in issue.get("labels", [])}
    if action == "add":
        labels.add(label)
    elif action == "remove":
        labels.discard(label)
    else:
        raise UnsupportedCommandError("supported issue label commands: add, remove")
    before, after = backend.update_issue(issue_id, labels=sorted(labels))
    return mutation_receipt(f"issue.label.{action}", issue_id, minimal_issue(before), minimal_issue(after))


def cycle_command(args: list[str], opts: Options, backend: Any, *, jira: bool = False) -> Any:
    name = "sprint" if jira else "cycle"
    command = args[0] if args else "list"
    if command == "list":
        return backend.list_cycles()
    if command == "current":
        return backend.current_cycle()
    if command == "add" and len(args) >= 3:
        before, after = backend.update_issue(args[2], cycle=args[1])
        return mutation_receipt(f"{name}.add", args[2], minimal_issue(before), minimal_issue(after))
    if command == "remove" and len(args) >= 3:
        before, after = backend.update_issue(args[2], cycle=None)
        return mutation_receipt(f"{name}.remove", args[2], minimal_issue(before), minimal_issue(after))
    if command in {"create", "view", "update"}:
        raise UnsupportedCommandError(f"{name} {command} is reserved for the Plane cycle adapter")
    raise UnsupportedCommandError(f"supported {name} commands: list, current, add, remove")


def module_command(args: list[str], opts: Options, backend: Any, *, jira: bool = False) -> Any:
    name = "epic" if jira else "module"
    command = args[0] if args else "list"
    if command == "list":
        return backend.list_modules()
    if command == "view" and len(args) >= 2:
        modules = backend.list_modules()
        for module in modules:
            if args[1].lower() in {module["id"].lower(), module["name"].lower()}:
                return module
        raise WorldIssuesError(f"{name} not found: {args[1]}")
    if command == "add" and len(args) >= 3:
        before, after = backend.update_issue(args[2], module=args[1])
        return mutation_receipt(f"{name}.add", args[2], minimal_issue(before), minimal_issue(after))
    if command == "remove" and len(args) >= 3:
        before, after = backend.update_issue(args[2], module=None)
        return mutation_receipt(f"{name}.remove", args[2], minimal_issue(before), minimal_issue(after))
    if command == "create":
        raise UnsupportedCommandError(f"{name} create is reserved for the Plane module adapter")
    raise UnsupportedCommandError(f"supported {name} commands: list, view, add, remove")


def clone_issue(args: list[str], backend: Any) -> Any:
    if not args:
        raise WorldIssuesError("jira issue clone requires an issue")
    original = backend.get_issue(args[0])
    issue = backend.create_issue(
        title=f"Clone: {original['title']}",
        description=original.get("description", ""),
        priority=original.get("priority", "medium"),
        labels=[label["name"] for label in original.get("labels", [])],
    )
    return mutation_receipt("issue.clone", args[0], original, issue)


def query_filters(args: list[str]) -> dict[str, Any]:
    mapping = {
        "--assignee": "assignee",
        "--state": "state",
        "--state-category": "state_category",
        "--label": "label",
        "--priority": "priority",
        "--project": "project",
        "--cycle": "cycle",
        "--module": "module",
        "--search": "search",
    }
    filters: dict[str, Any] = {}
    for flag, key in mapping.items():
        value = option_value(args, flag)
        if value:
            filters[key] = value
    return filters


def option_value(args: list[str], name: str) -> str | None:
    if name not in args:
        return None
    index = args.index(name)
    if index + 1 >= len(args):
        raise WorldIssuesError(f"missing value for {name}")
    return args[index + 1]


def multi_option(args: list[str], name: str) -> list[str]:
    values = []
    i = 0
    while i < len(args):
        if args[i] == name:
            if i + 1 >= len(args):
                raise WorldIssuesError(f"missing value for {name}")
            values.append(args[i + 1])
            i += 1
        i += 1
    return values


def safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def backend_name(backend: Any) -> str:
    return "fake" if isinstance(backend, FakePlaneBackend) else "plane"


if __name__ == "__main__":
    main()
