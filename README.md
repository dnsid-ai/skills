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

## Install

**Claude Code:**

```
/plugin marketplace add dnsid-ai/skills
/plugin install dnsid-skills@dnsid
```

**Other agents:** run `npx skills add dnsid-ai/skills`, or copy the folders
under `skills/` into your agent's skills directory (for example
`.claude/skills/` in a project).
