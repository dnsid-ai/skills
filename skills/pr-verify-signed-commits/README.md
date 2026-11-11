# pr-verify-signed-commits

`verify_signed_commits(pr_number: int, repo: str) -> dict`

Lists the commits in a pull request that GitHub does not mark verified, using
`GET /repos/{repo}/pulls/{pr_number}/commits` through the `gh` CLI. Read-only;
the token needs read access to the repository.

## Output

```json
{
  "repo": "dnsid-ai/skills",
  "pr_number": 12,
  "ok": false,
  "total_commits": 3,
  "unsigned_commits": [
    {"sha": "9f1c…", "reason": "unsigned", "subject": "Fix typo", "author": "octocat"}
  ],
  "remediation": ["Configure signing once (SSH): …", "…"]
}
```

`reason` is GitHub's verification reason: `unsigned`, `unknown_key` (the key is
not uploaded as a signing key), `unverified_email` / `no_user` (the author email
is not verified on the key owner's account), `bad_email`, `expired_key`,
`invalid`, and so on. `remediation` is empty when `ok` is true.

## What an agent should do with it

- `ok: true`: nothing.
- `ok: false`: show the user each commit and its reason, then the remediation.
  Re-signing rewrites the branch's history, so ask before running the rebase and
  force-push yourself.

## Failure modes

- A `gh` error (no auth, no access, PR not found) raises
  `subprocess.CalledProcessError`; the CLI prints it and exits 1 with no JSON.
- GitHub returns at most 250 commits for a pull request; a larger PR is checked
  only on those.
