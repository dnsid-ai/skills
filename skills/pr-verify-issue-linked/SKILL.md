---
name: pr-verify-issue-linked
description: >-
  Check that a GitHub pull request links an existing open issue (closes/fixes/resolves/refs #N), and optionally label the linked issues in-progress. Use before opening or reviewing a PR, when a PR must be tied to an issue, or when the user asks which issue a PR closes.
---

# pr-verify-issue-linked

Call `verify_issue_linked` from [main.py](main.py), or run it from this directory:

```bash
python3 main.py 12 dnsid-ai/skills               # read-only
python3 main.py 12 dnsid-ai/skills in-progress   # also labels the linked issues
```

It uses the `gh` CLI and its existing auth, prints JSON matching the
`outputSchema` in [skill.yaml](skill.yaml), and exits 0 when `ok` is true,
1 when it is false. Inputs, outputs and failure modes: [README.md](README.md).

With a label it **writes to GitHub**. Add one only when the user asked for it.
