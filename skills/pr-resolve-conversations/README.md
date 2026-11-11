# pr-resolve-conversations

`resolve_conversations(pr_number: int, repo: str, auto_resolve_simple: bool = True) -> dict`

Reads every review thread on a pull request (GraphQL `reviewThreads`, through the
`gh` CLI). With `auto_resolve_simple`, it resolves the *simple* ones and reports
the rest.

A thread is **simple** when it is outdated: the lines it comments on have
changed since. Nothing else is resolved automatically, because whether a
comment on current code has been addressed is a judgement for a person.

## Output

```json
{
  "repo": "dnsid-ai/skills",
  "pr_number": 12,
  "ok": false,
  "total_threads": 5,
  "already_resolved": [ … ],
  "resolved": [ {"id": "PRRT_…", "path": "main.py", "line": 10, "author": "octocat",
                 "first_comment": "Rename this", "url": "https://github.com/…", "outdated": true} ],
  "unresolved": [ … ],
  "needs_attention": [ … ]
}
```

- `resolved`: threads this call resolved.
- `unresolved`: threads still open. Includes outdated threads when
  `auto_resolve_simple` is false, or when resolving one failed.
- `needs_attention`: the unresolved threads on current code. These are the ones
  to show the user or act on.
- `ok`: no thread is left unresolved.

## Permissions

Reading needs read access. Resolving needs write access to the repository (the
`gh` token's user must be able to resolve conversations); a thread that cannot
be resolved stays in `unresolved` rather than raising.

## Failure modes

A `gh` error while listing (no auth, no access, PR not found) raises
`subprocess.CalledProcessError`; the CLI prints it and exits 1 with no JSON.
