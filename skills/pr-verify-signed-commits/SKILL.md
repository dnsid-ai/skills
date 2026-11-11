---
name: pr-verify-signed-commits
description: >-
  Check whether every commit in a GitHub pull request is signed and verified, and get the steps to re-sign the ones that are not. Use when a PR is blocked by a signed-commits rule, before asking for review, or when the user asks whether a PR's commits are signed.
---

# pr-verify-signed-commits

Call `verify_signed_commits` from [main.py](main.py), or run it from this directory:

```bash
python3 main.py 12 dnsid-ai/skills
```

It uses the `gh` CLI and its existing auth, prints JSON matching the
`outputSchema` in [skill.yaml](skill.yaml), and exits 0 when `ok` is true,
1 when it is false. Inputs, outputs and failure modes: [README.md](README.md).
