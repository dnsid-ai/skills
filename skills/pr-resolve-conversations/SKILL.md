---
name: pr-resolve-conversations
description: >-
  List a GitHub pull request's review conversations, resolve the outdated ones, and report which still need a person. Use when a PR is blocked on unresolved conversations, after pushing fixes for review comments, or when the user asks what review feedback is still open.
---

# pr-resolve-conversations

Call `resolve_conversations` from [main.py](main.py), or run it from this directory:

```bash
python3 main.py 12 dnsid-ai/skills                    # resolves outdated threads
python3 main.py 12 dnsid-ai/skills --no-auto-resolve  # read-only
```

It uses the `gh` CLI and its existing auth, prints JSON matching the
`outputSchema` in [skill.yaml](skill.yaml), and exits 0 when `ok` is true,
1 when it is false. Inputs, outputs and failure modes: [README.md](README.md).

By default this **writes to GitHub**: it resolves outdated threads. When the user
only asked what is open, pass `auto_resolve_simple=False` (`--no-auto-resolve`).
