#!/usr/bin/env python3
"""verify_signed_commits: list the commits in a pull request that GitHub does not mark verified."""

from __future__ import annotations

import json
import subprocess
import sys

REMEDIATION = [
    "Configure signing once (SSH): git config --global gpg.format ssh; "
    "git config --global user.signingkey ~/.ssh/id_ed25519.pub; git config --global commit.gpgsign true",
    "Upload the public key to GitHub as a Signing key (Settings > SSH and GPG keys); "
    "the commit author email must be a verified email on that account.",
    "Re-sign the PR's commits: git rebase --exec 'git commit --amend --no-edit -S' origin/<base-branch>, "
    "then git push --force-with-lease.",
    "Reason codes: https://docs.github.com/rest/commits/commits#signature-verification-object",
]


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def unsigned(commits: list[dict]) -> list[dict]:
    return [
        {
            "sha": c["sha"],
            "reason": c["commit"]["verification"]["reason"],
            "subject": c["commit"]["message"].splitlines()[0] if c["commit"]["message"] else "",
            "author": (c.get("author") or {}).get("login") or c["commit"]["author"]["email"],
        }
        for c in commits
        if not c["commit"]["verification"]["verified"]
    ]


def verify_signed_commits(pr_number: int, repo: str) -> dict:
    # ponytail: GitHub's PR commits endpoint caps at 250 commits; split larger PRs.
    out = gh("api", "--paginate", f"repos/{repo}/pulls/{pr_number}/commits", "--jq", ".[]")
    commits = [json.loads(line) for line in out.splitlines() if line.strip()]
    bad = unsigned(commits)
    return {
        "repo": repo,
        "pr_number": pr_number,
        "ok": not bad,
        "total_commits": len(commits),
        "unsigned_commits": bad,
        "remediation": REMEDIATION if bad else [],
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: main.py <pr_number> <owner/repo>")
    try:
        result = verify_signed_commits(int(sys.argv[1]), sys.argv[2])
    except subprocess.CalledProcessError as exc:
        sys.exit(f"error: {exc.stderr.strip()}")
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
