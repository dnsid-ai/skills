#!/usr/bin/env python3
"""resolve_conversations: list a PR's review threads, resolve the simple ones, flag the rest."""

from __future__ import annotations

import json
import subprocess
import sys

QUERY = """
query($owner: String!, $name: String!, $pr: Int!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100, after: $endCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id isResolved isOutdated path line
          comments(first: 1) { totalCount nodes { author { login } body url } }
        }
      }
    }
  }
}"""

RESOLVE = "mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }"


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def summarize(t: dict) -> dict:
    first = (t["comments"]["nodes"] or [{}])[0]
    body = (first.get("body") or "").strip()
    return {
        "id": t["id"],
        "path": t["path"],
        "line": t.get("line"),
        "author": (first.get("author") or {}).get("login", "ghost"),
        "first_comment": body.splitlines()[0][:200] if body else "",
        "url": first.get("url", ""),
        "outdated": t["isOutdated"],
    }


def is_simple(t: dict) -> bool:
    # ponytail: "simple" = outdated (the commented code has changed since). A reply-aware
    # heuristic would need every comment in the thread; add it if outdated proves too narrow.
    return t["isOutdated"]


def resolve_conversations(pr_number: int, repo: str, auto_resolve_simple: bool = True) -> dict:
    owner, name = repo.split("/", 1)
    out = gh(
        "api", "graphql", "--paginate",
        "-f", f"query={QUERY}", "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"pr={pr_number}",
        "--jq", ".data.repository.pullRequest.reviewThreads.nodes[]",
    )
    threads = [json.loads(line) for line in out.splitlines() if line.strip()]

    already = [summarize(t) for t in threads if t["isResolved"]]
    resolved, unresolved = [], []
    for t in (t for t in threads if not t["isResolved"]):
        if auto_resolve_simple and is_simple(t):
            try:
                gh("api", "graphql", "-f", f"query={RESOLVE}", "-f", f"id={t['id']}")
                resolved.append(summarize(t))
                continue
            except subprocess.CalledProcessError:
                pass  # no permission or already gone: report it as still open
        unresolved.append(summarize(t))

    return {
        "repo": repo,
        "pr_number": pr_number,
        "ok": not unresolved,
        "total_threads": len(threads),
        "already_resolved": already,
        "resolved": resolved,
        "unresolved": unresolved,
        "needs_attention": [u for u in unresolved if not u["outdated"]],
    }


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit("usage: main.py <pr_number> <owner/repo> [--no-auto-resolve]")
    try:
        result = resolve_conversations(int(sys.argv[1]), sys.argv[2], "--no-auto-resolve" not in sys.argv)
    except subprocess.CalledProcessError as exc:
        sys.exit(f"error: {exc.stderr.strip()}")
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
