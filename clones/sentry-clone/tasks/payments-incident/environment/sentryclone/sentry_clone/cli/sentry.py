from __future__ import annotations

import argparse
import sys

from .client import AuthConfigError, BackendUnavailableError, NotFoundError, SentryClient, SentryClientError, UnsupportedCommandError
from .output import emit_json, emit_table, error


class SentryArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def _strip_json(argv: list[str]) -> tuple[list[str], bool]:
    as_json = "--json" in argv
    return [arg for arg in argv if arg != "--json"], as_json


def _client() -> SentryClient:
    return SentryClient()


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    args_without_json, as_json = _strip_json(raw)
    parser = build_parser()
    args = parser.parse_args(args_without_json)
    setattr(args, "json", as_json)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 0
    try:
        value = args.handler(args)
    except (NotFoundError, AuthConfigError, BackendUnavailableError, UnsupportedCommandError, SentryClientError) as exc:
        error(str(exc))
        return getattr(exc, "exit_code", 1)
    except KeyboardInterrupt:
        return 1
    if as_json:
        emit_json(value)
    else:
        emit_table(value)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = SentryArgumentParser(prog="sentry", description="Sentry-compatible local clone CLI")
    parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="group")

    config = sub.add_parser("config", help="configuration commands")
    config_sub = config.add_subparsers(dest="config_cmd", required=True)
    config_sub.add_parser("check").set_defaults(handler=lambda _args: _client().config_check())

    sub.add_parser("whoami", help="show authenticated user").set_defaults(handler=lambda _args: _client().whoami())

    org = sub.add_parser("org", help="organization commands")
    org_sub = org.add_subparsers(dest="org_cmd", required=True)
    org_sub.add_parser("list").set_defaults(handler=lambda _args: _client().organizations())

    projects = sub.add_parser("projects", help="project commands")
    projects_sub = projects.add_subparsers(dest="projects_cmd", required=True)
    projects_list = projects_sub.add_parser("list")
    projects_list.add_argument("--org")
    projects_list.set_defaults(handler=lambda args: _client().projects(args.org))

    issues = sub.add_parser("issues", help="issue commands")
    issues_sub = issues.add_subparsers(dest="issues_cmd", required=True)
    issues_list = issues_sub.add_parser("list")
    issues_list.add_argument("--project")
    issues_list.add_argument("--org")
    issues_list.add_argument("--query")
    issues_list.add_argument("--sort")
    issues_list.set_defaults(handler=lambda args: _client().issues(project=args.project, org=args.org, query=args.query, sort=args.sort))
    _issue_ref(issues_sub.add_parser("get")).set_defaults(handler=lambda args: _client().issue(args.issue))
    _issue_ref(issues_sub.add_parser("events")).set_defaults(handler=lambda args: _client().issue_events(args.issue))
    _issue_ref(issues_sub.add_parser("latest-event")).set_defaults(handler=lambda args: _client().latest_event(args.issue))
    _issue_ref(issues_sub.add_parser("stacktrace")).set_defaults(handler=lambda args: _client().stacktrace(args.issue))
    _issue_ref(issues_sub.add_parser("breadcrumbs")).set_defaults(handler=lambda args: _client().breadcrumbs(args.issue))
    _issue_ref(issues_sub.add_parser("tags")).set_defaults(handler=lambda args: _client().issue_tags(args.issue))
    _issue_ref(issues_sub.add_parser("suspect-commits")).set_defaults(handler=lambda args: _client().suspect_commits(args.issue))
    _issue_ref(issues_sub.add_parser("activity")).set_defaults(handler=lambda args: _client().activity(args.issue))
    _issue_ref(issues_sub.add_parser("comments")).set_defaults(handler=lambda args: _client().comments(args.issue))
    comment = _issue_ref(issues_sub.add_parser("comment"))
    comment.add_argument("--text", required=True)
    comment.set_defaults(handler=lambda args: _client().add_comment(args.issue, args.text))
    assign = _issue_ref(issues_sub.add_parser("assign"))
    assign.add_argument("--team")
    assign.add_argument("--user")
    assign.set_defaults(handler=lambda args: _client().assign_issue(args.issue, team=args.team, user=args.user))
    resolve = _issue_ref(issues_sub.add_parser("resolve"))
    resolve.add_argument("--in-release")
    resolve.set_defaults(handler=lambda args: _client().resolve_issue(args.issue, args.in_release))
    ignore = _issue_ref(issues_sub.add_parser("ignore"))
    ignore.add_argument("--reason")
    ignore.set_defaults(handler=lambda args: _client().ignore_issue(args.issue, args.reason))
    _issue_ref(issues_sub.add_parser("reopen")).set_defaults(handler=lambda args: _client().reopen_issue(args.issue))

    events = sub.add_parser("events", help="event commands")
    events_sub = events.add_subparsers(dest="events_cmd", required=True)
    events_get = events_sub.add_parser("get")
    events_get.add_argument("event_id")
    events_get.add_argument("--project", required=True)
    events_get.add_argument("--org")
    events_get.set_defaults(handler=lambda args: _client().event(args.event_id, args.project, args.org))

    releases = sub.add_parser("releases", help="release commands")
    rel_sub = releases.add_subparsers(dest="releases_cmd", required=True)
    rel_list = rel_sub.add_parser("list")
    rel_list.add_argument("--project")
    rel_list.add_argument("--org")
    rel_list.set_defaults(handler=lambda args: _client().releases(project=args.project, org=args.org))
    rel_get = rel_sub.add_parser("get")
    rel_get.add_argument("version")
    rel_get.add_argument("--project")
    rel_get.add_argument("--org")
    rel_get.set_defaults(handler=lambda args: _client().release(args.version, project=args.project, org=args.org))
    rel_commits = rel_sub.add_parser("commits")
    rel_commits.add_argument("version")
    rel_commits.add_argument("--project")
    rel_commits.add_argument("--org")
    rel_commits.set_defaults(handler=lambda args: _client().release_commits(args.version, project=args.project, org=args.org))

    ownership = sub.add_parser("ownership", help="ownership commands")
    owner_sub = ownership.add_subparsers(dest="ownership_cmd", required=True)
    owner_list = owner_sub.add_parser("list")
    owner_list.add_argument("--project", required=True)
    owner_list.add_argument("--org")
    owner_list.set_defaults(handler=lambda args: _client().ownership(args.project, args.org))

    return parser


def _issue_ref(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("issue")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
