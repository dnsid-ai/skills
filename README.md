# DNSid agent skills

Agent skills for building with [DNSid](https://docs.dnsid.ai), verifiable
DNS-anchored identity for AI agents. They help a coding agent explain DNSid,
set up DNSid Local, write correct SDK code, and add DNSid to agent
frameworks.

| Skill | Use it for |
|---|---|
| [`dnsid`](skills/dnsid/SKILL.md) | The protocol: the `_dnsid` record, the two keys, the lifecycle log, what verification proves, and where DNSid does and does not fit |
| [`dnsid-cli`](skills/dnsid-cli/SKILL.md) | Installing `dnsid`, running DNSid Local, inspecting and verifying records, and troubleshooting |
| [`dnsid-sdk`](skills/dnsid-sdk/SKILL.md) | Go, TypeScript, and Python code: verifying peers, protecting HTTP APIs, signing requests, tokens, log trust, and keys |
| [`dnsid-integrations`](skills/dnsid-integrations/SKILL.md) | The Claude Agent SDK plugin, A2A, LangGraph, MCP, OIDC gateways, edge, and building a new integration |

PR management tools. Each is a Python function an agent calls, with an A2A
skill definition and JSON Schema contract in `skill.yaml`; they use the `gh`
CLI and its auth.

| Skill | Tool |
|---|---|
| [`pr-verify-signed-commits`](skills/pr-verify-signed-commits/README.md) | `verify_signed_commits(pr_number, repo)`: the PR's unverified commits, with how to re-sign them |
| [`pr-resolve-conversations`](skills/pr-resolve-conversations/README.md) | `resolve_conversations(pr_number, repo, auto_resolve_simple=True)`: resolves outdated review threads, flags the rest |
| [`pr-verify-issue-linked`](skills/pr-verify-issue-linked/README.md) | `verify_issue_linked(pr_number, repo, add_label=None)`: checks the PR links open issues, optionally labels them |

## Install

**Claude Code:**

```
/plugin marketplace add dnsid-ai/skills
/plugin install dnsid-skills@dnsid
```

**Other agents:** run `npx skills add dnsid-ai/skills`, or copy the folders
under `skills/` into your agent's skills directory (for example
`.claude/skills/` in a project).

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) and the
[code of conduct](CODE_OF_CONDUCT.md). Report security issues privately per
[SECURITY.md](SECURITY.md), not in a public issue.

## License

The skill text (Markdown files) is licensed under
[CC BY 4.0](LICENSE-docs.txt). Code, including code blocks embedded in
Markdown, and the plugin manifests are licensed under the
[Apache License 2.0](LICENSE).
