#!/usr/bin/env python3
"""verify_issue_linked: check a PR body links existing open issues; optionally label them."""

from __future__ import annotations

import json
import re
import subprocess
import sys

# GitHub's closing keywords plus ref/refs. Matches "#12" and "owner/repo#12".
LINK_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs?)\b:?\s+(?:([\w.-]+/[\w.-]+))?#(\d+)",
    re.IGNORECASE,
)

REMEDIATION = [
    'Add a line to the PR description such as "Closes #123", "Fixes #123" or "Refs #123" '
    '("Closes owner/repo#123" for another repository).',
    "If no issue exists yet, open one describing the change, then link it.",
    "Linked issues must exist and be open.",
]


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def parse_links(body: str, default_repo: str) -> list[tuple[str, int]]:
    """Unique (repo, number) pairs linked from a PR body, in order of appearance."""
    return list(dict.fromkeys((r or default_repo, int(n)) for r, n in LINK_RE.findall(body or "")))


def check_issue(repo: str, number: int) -> str | None:
    """An error message, or None if the issue exists and is open."""
    try:
        issue = json.loads(gh("api", f"repos/{repo}/issues/{number}"))
    except subprocess.CalledProcessError:
        return "does not exist or is not accessible"
    if "pull_request" in issue:
        return "is a pull request, not an issue"
    if issue["state"] != "open":
        return f"is {issue['state']}"
    return None


def verify_issue_linked(pr_number: int, repo: str, add_label: str | None = None) -> dict:
    pr = json.loads(gh("api", f"repos/{repo}/pulls/{pr_number}"))
    issues = [
        {"repo": r, "number": n, "error": check_issue(r, n)}
        for r, n in parse_links(pr["body"], pr["base"]["repo"]["full_name"])
    ]
    ok = bool(issues) and not any(i["error"] for i in issues)

    labeled = []
    if ok and add_label:  # write only when every link is valid
        for i in issues:
            gh("api", "-X", "POST", f"repos/{i['repo']}/issues/{i['number']}/labels", "-f", f"labels[]={add_label}")
            labeled.append(f"{i['repo']}#{i['number']}")

    return {
        "repo": repo,
        "pr_number": pr_number,
        "ok": ok,
        "linked_issues": [f"{i['repo']}#{i['number']}" for i in issues],
        "errors": [f"{i['repo']}#{i['number']} {i['error']}" for i in issues if i["error"]]
        or ([] if issues else ["PR body links no issue"]),
        "labeled": labeled,
        "remediation": [] if ok else REMEDIATION,
    }


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit('usage: main.py <pr_number> <owner/repo> ["in-progress"]')
    try:
        result = verify_issue_linked(int(sys.argv[1]), sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None)
    except subprocess.CalledProcessError as exc:
        sys.exit(f"error: {exc.stderr.strip()}")
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
