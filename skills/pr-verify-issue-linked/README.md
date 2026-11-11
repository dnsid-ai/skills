# pr-verify-issue-linked

`verify_issue_linked(pr_number: int, repo: str, add_label: str | None = None) -> dict`

Parses the pull request body for issue links and checks each one through the
`gh` CLI.

A link is a closing keyword or `ref` followed by an issue reference:
`close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`, `resolves`,
`resolved`, `ref`, `refs`, case-insensitive, with an optional colon, then `#N`
or `owner/repo#N`. `#N` means the PR's base repository.

Each linked issue must exist, be an issue rather than a pull request, and be
open. `ok` is true when at least one issue is linked and every one passes.

With `add_label` (for example `"in-progress"`), the label is added to every
linked issue, only when `ok` is true. GitHub creates the label if the repository
does not have it.

## Output

```json
{
  "repo": "dnsid-ai/skills",
  "pr_number": 12,
  "ok": false,
  "linked_issues": ["dnsid-ai/skills#7", "dnsid-ai/other#3"],
  "errors": ["dnsid-ai/other#3 is closed"],
  "labeled": [],
  "remediation": ["Add a line to the PR description such as \"Closes #123\" …", "…"]
}
```

A PR with no link returns `"errors": ["PR body links no issue"]`.

## Permissions

Checking needs read access to the PR's repository and to every linked issue's
repository; an issue the token cannot see is reported as not existing. Labeling
needs write (triage) access to the issue's repository.

## Failure modes

A `gh` error reading the PR, or adding a label, raises
`subprocess.CalledProcessError`; the CLI prints it and exits 1 with no JSON.
