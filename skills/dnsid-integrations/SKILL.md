---
name: dnsid-integrations
description: >-
  Add DNSid identity to an agent framework or platform using the official
  integrations and cookbook recipes. Covers the Claude Agent SDK plugin
  (`@dnsid-ai/agent-sdk-plugin`), A2A, LangGraph/LangChain, MCP clients and
  servers, HTTP APIs and webhooks, OIDC token gateways (Amazon Bedrock
  AgentCore Gateway, cloud IAM), and edge or CDN verification. It also covers
  the design rules for building a new integration. Use this skill whenever the
  user wants agents built on any framework to verify each other, to sign
  their calls, or to call only verified peers. Use it when they mention the
  DNSid plugin or the cookbook, or ask how to "add DNSid to" a framework,
  gateway, or platform, even if they do not say "integration". Use it
  together with dnsid-sdk for the code and dnsid-cli for the local
  environment.
---

# DNSid integrations

An integration places the two DNSid checks where a framework already
sends and receives traffic:

- **Outbound:** sign what the agent sends, and verify the peer before
  sending.
- **Inbound:** verify every caller before a handler or tool runs.

Everything runs on public DNS and HTTPS, needs no account, and can be tested
end to end on DNSid Local.

## Choose the path

| The user has… | Use | Reference implementation | Runs on DNSid Local? |
|---|---|---|---|
| An agent on the **Claude Agent SDK** | The official plugin | [dnsid-ai/agent-sdk-plugin](https://github.com/dnsid-ai/agent-sdk-plugin), npm `@dnsid-ai/agent-sdk-plugin` | Yes |
| **A2A** agents | RFC 9421 signatures with tag `a2a-dnsid-http-sig-v1`, plus an agent-card extension | Cookbook recipe 12, and `examples/a2a` in each SDK | Yes |
| **LangGraph / LangChain** | `langchain-dnsid`: ingress middleware, an egress client, and tool gating | Cookbook recipe 31 | Yes |
| An **HTTP API or webhook receiver** | SDK inbound verification and an allowlist | Cookbook recipe 06b (Go), dnsid-sdk references | Yes |
| A **gateway or IAM that expects JWTs** | DNSid OIDC tokens | Recipe 29 (Go, local). Recipes 07, 07b, 28, and 30 (AgentCore) | 29: yes. The AgentCore recipes need AWS and a hosted DNSid issuer. |
| **MCP** | Verify the server's domain before connecting. Have the server verify signed HTTP. | No shipped recipe. Plugin: `DNSID_MCP_SERVER_DOMAINS` | Pattern only, see below |
| **Edge or CDN** (Workers, Lambda@Edge, Fastly, Vercel, …) | Verify at the edge with Web Crypto and bounded caches | No shipped recipe | Pattern only, see below |
| **Crawlers and bots** | The Web Bot Auth profile | `examples/webbotauth` in each SDK | Yes |

Recipes live in https://github.com/dnsid-ai/dnsid-cookbook. Each runnable
recipe has `make bootstrap`, `make run`, `make verify`, and `make clean`.
Most of them share the user's DNSid Local, and their `clean` target stops it.
`references/recipes.md` lists what each recipe shows and which files to copy
from. Read it before you adapt one. The cookbook index also lists planned
recipes that have no directory yet. Only point the user at recipes that exist
under `recipes/`.

## Claude Agent SDK plugin

For agents built on `@anthropic-ai/claude-agent-sdk`, the plugin does the
whole job without changes to prompts:

1. **Verifies peers.** A `PreToolUse` hook verifies the host on `WebFetch`,
   on the plugin's `fetch` tool, and on mapped `mcp__*` tools. It denies the
   call unless the peer is `ACTIVE`, even in `bypassPermissions` mode.
2. **Signs requests.** Its MCP `fetch` tool signs with RFC 9421 using the
   agent's key.
3. **Brings itself online.** A `SessionStart` hook submits the agent's own
   ISSUANCE.

```bash
npm install @dnsid-ai/agent-sdk-plugin      # requires Node 24+
```

```ts
import { fileURLToPath } from 'node:url';
import { query } from '@anthropic-ai/claude-agent-sdk';

const pluginRoot = fileURLToPath(
  new URL('.', import.meta.resolve('@dnsid-ai/agent-sdk-plugin/package.json')),
);

// DNSid Local only: the registry expects its HTTPS name as the token audience,
// but `dnsid local run` sets DNSID_REGISTRY_URL to a local HTTP port.
// Without this, the bring-online hook cannot authenticate locally.
const zone = process.env.DNSID_TESTNET_ZONE;
if (zone) process.env.DNSID_AGENT_AUTH_AUDIENCE ??= `https://registry.${zone}`;

for await (const msg of query({
  prompt,
  options: {
    plugins: [{ type: 'local', path: pluginRoot }],
    disallowedTools: ['WebFetch'],   // force the signed fetch tool
    settingSources: [],              // keep the developer's ~/.claude settings, MCP servers, and plugins out
  },
})) { /* ... */ }
```

This matches `examples/minimal/alice.ts` and `docs/guide.md` in the plugin
repo. Copy from those files when the user wants a complete program.

```bash
dnsid local run alice --port 3001 -- node alice.ts '<prompt>'   # identity + local DNS/CA from the CLI
```

Things that catch people out. Explain them when you set the plugin up:

- `Bash` is **not gated**. A `curl` in a shell command reaches any host
  without verification. To enforce the boundary, restrict `Bash` with
  permission rules.
- `WebFetch` is verified but **unsigned**, so the peer cannot tell who is
  calling. To make every call signed, disallow `WebFetch`.
- MCP servers are verified only if you map them in `DNSID_MCP_SERVER_DOMAINS`
  (JSON: server name to agent domain).
- To roll out gradually, start with `DNSID_MODE=observe`. It logs verdicts
  and denies nothing. Switch to `enforce` once the logs look right.
- "Cannot verify" (for example, an untrusted log or an `fl=mtls` peer) denies
  by default. `DNSID_ON_UNVERIFIABLE=ask` turns it into a permission prompt
  instead. It never allows the call silently.
- The verdict cache defaults to `$TMPDIR/dnsid-verdicts.json`. On a host
  that other users share, set `DNSID_CACHE_FILE` to a private path, because
  anyone who can write to the cache can plant a verdict.
- Verification is not an allowlist. Any `ACTIVE` DNSid agent passes the hook.
  To restrict which peers the agent may call, add permission rules on the
  `fetch` tool, or your own `PreToolUse` hook that checks the domain.
- A peer that receives the plugin's signed requests can verify them with the
  same verifier: `import { createVerifier } from '@dnsid-ai/agent-sdk-plugin/verify'`.
- Do **not** install this plugin into an interactive Claude Code session for
  ordinary development. It would deny `WebFetch` to every site that has no
  DNSid identity. It is meant for agents you build and deploy.

`references/agent-sdk-plugin.md` has the full environment-variable table and
the bring-online states. Read it when you configure the plugin beyond the
defaults, when you use KMS keys, or when you debug a `DNSid:` denial.

## Rules for any integration

These rules come from the shipped integrations. A new integration that
follows them gets the same security properties.

1. **Put the checks in the transport, not in tool code.** Sign and verify
   inside the HTTP client, middleware, or hook that every call already goes
   through. Recipe 31 does this: one egress client signs and verifies the
   peer for every tool that uses it. A tool that builds its own client
   bypasses both checks, so make the safe client the only one tools can
   reach.
2. **Keep the model out of the trust path.** The model can choose a URL, but
   code decides whether that host is trusted. Verify the destination domain
   before sending. Then a prompt injection that says "call evil.example"
   ends in a refusal, not a signed request.
3. **Fail closed.** Unverifiable, revoked, or not on the allowlist means
   deny. "Cannot verify" is not evidence against the peer. Report it
   neutrally, and still do not proceed (or ask a human, as the plugin does).
4. **Verification is not authorization.** After verification, apply an
   allowlist of accountable entities (`trustedEntities`) and per-tool or
   per-route permissions. Recipe 31 hides sensitive tools from callers who
   are not on the allowlist.
5. **Name the application in the signature.** Use an RFC 9421 `tag` that is
   specific to the protocol (for example `a2a-dnsid-http-sig-v1`), and
   require it on the receiving side. Cover the protocol headers that matter.
   A2A covers `a2a-version`, `a2a-extensions`, and `content-type`.
6. **Advertise the requirement.** Where the protocol has a capability
   document (A2A agent card, MCP server metadata), declare that DNSid
   signatures are required, so callers learn the rule before their first
   request.
7. **Pin the public origin, buffer the raw body, and stop replays** on every
   inbound path. dnsid-sdk rule 6 explains why.
8. **Prove it on DNSid Local.** Use two identities (for example `alice.test`
   and `bob.test`) and show each case: a signed and verified call succeeds;
   unsigned, tampered, replayed, unknown, and non-allowlisted calls are
   refused. The cookbook's `make verify` targets are the model for this.

## MCP (pattern)

No recipe or published server ships for MCP yet.

- **The client verifies the server.** Map each MCP server to the DNSid
  domain it should have. Verify that domain before connecting and on each
  reconnect, and refuse when verification fails. With the Agent SDK plugin,
  this is `DNSID_MCP_SERVER_DOMAINS`.
- **The server verifies the client** (Streamable HTTP transport): put the
  inbound RFC 9421 middleware from dnsid-sdk in front of the MCP endpoint,
  and authorize tools on the verified caller domain.
- Stdio servers have no network peer, so DNSid does not apply to them.

## Edge and CDN (pattern)

No recipe ships for this yet.

- Verify at the edge with Web Crypto (Ed25519 and P-256) and reject before
  the request reaches the origin. The TypeScript SDK core does not depend on
  a runtime, but it needs a DNS-over-HTTPS resolver and a fetcher for the
  platform.
- Cache JWKS and status for no longer than the revocation delay you can
  accept, and never past the response's freshness window.
- Do not use runtimes that **cannot make network calls** (CloudFront
  Functions) on paths where revocation matters. They can only check against
  key and status data that was synced in advance, so a revocation is not
  seen until the next sync.

## Tokens instead of signatures

When a platform already validates JWTs (AgentCore Gateway `CUSTOM_JWT`, AWS
IAM OIDC, GCP Workload Identity Federation, Azure federated credentials,
OAuth middleware), use DNSid OIDC. The agent signs an RFC 7523 assertion with
its operational key, exchanges it for a short-lived token for one audience,
and the platform validates the token. For full assurance, the relying
service should also verify the subject's DNSid identity, as recipe 29 shows
with `VerifyOIDCToken`. The AgentCore recipes (07, 07b, 28, 30) need AWS and
a hosted DNSid identity. They show the pattern, but they do not run on DNSid
Local.

## What not to build

- DNSid in front of **model API calls** (OpenAI, Anthropic, and so on): that
  is not a boundary between agents.
- DNSid as **end-user login**: people do not have domains.
- An integration that **only checks the record signature**. A full
  verification includes status, the key chain, and the log. Always call the
  SDK's full verify.
- An integration that **treats a passing verification as permission**.
