# Claude Agent SDK plugin: configuration and behavior

The source of truth is the repo README and `docs/guide.md` in
https://github.com/dnsid-ai/agent-sdk-plugin. The guide walks through all
three behaviors on DNSid Local with two agents, Alice and Bob.

## Contents

- Identity and keys
- What gets verified
- Configuration
- Bring-online states
- Reading denials
- Layout

## Identity and keys

The agent's identity is `config.json` plus `private.jwk` in
`DNSID_CONFIG_DIR` (default `~/.dnsid`), exactly as the `dnsid` CLI writes
them. Under `dnsid local run <agent>`, the CLI points `DNSID_CONFIG_DIR` at
the local agent's directory and sets the DNS, CA, private-host, and log-policy
variables. In production, mount the identity directory as a secret, or set
`DNSID_AWS_KMS_KEY_ID` so that the agent signs with a KMS key. The plugin
never reads `DNSID_KEY_STORE`.

## What gets verified

| Tool | Peer verified |
|---|---|
| `WebFetch` | hostname of `url` |
| `mcp__plugin_dnsid_dnsid__fetch` | hostname of `url` |
| `mcp__plugin_dnsid_dnsid__verify` | nothing, because it calls no one |
| `mcp__<server>__*` | `DNSID_MCP_SERVER_DOMAINS[server]`, if mapped |
| anything else, including `Bash` | nothing |

`ACTIVE` allows the call, and the host's own permission rules still run
after that. Every other outcome denies with a reason that starts with
`DNSid:`. If the hook crashes, the call is denied. Verdicts are cached in a
file until they expire. Failures are cached for 30 seconds.

The `fetch` tool takes `url`, `method`, `headers`, `body`, and `tag`. It
signs with `keyid=<domain>#<kid>` and covers the method, authority, target
URI, body digest, and every header passed. It accepts only `https:` URLs,
and it returns redirects instead of following them, because a new location
is a new peer. The `verify(domain)` tool returns the hook's verdict without
calling the peer.

## Configuration

Every setting is an environment variable that starts with `DNSID_`. If a
value is invalid, the hook fails, so the call is denied.

| Variable | Default | Meaning |
|---|---|---|
| `DNSID_CONFIG_DIR` | `~/.dnsid` | The agent's identity: `config.json` and `private.jwk` |
| `DNSID_AGENT_AUTH_AUDIENCE` | `DNSID_REGISTRY_URL`, then `https://api.dnsid.ai` | The registry that the bring-online hook authenticates to. On DNSid Local, set it to `https://registry.test` (from `DNSID_TESTNET_ZONE`), because `DNSID_REGISTRY_URL` is a local HTTP port. |
| `DNSID_MODE` | `enforce` | `observe`: log each verdict to stderr and deny nothing |
| `DNSID_ON_UNVERIFIABLE` | `deny` | `ask`: turn a "cannot verify" result into a permission prompt |
| `DNSID_MCP_SERVER_DOMAINS` | `{}` | JSON map of MCP server name to agent domain |
| `DNSID_CACHE_FILE` | `$TMPDIR/dnsid-verdicts.json` | The verdict cache, shared across hook runs |
| `DNSID_DNS_SERVER` | system resolver | DNS for `_dnsid` lookups and for `fetch` |
| `DNSID_CA_BUNDLE` | system store | Extra CA certificates |
| `DNSID_PRIVATE_HOSTS` | none | Hosts or `.suffix` entries that may resolve to private addresses. `dnsid local run` sets this. |
| `DNSID_LOG_POLICY_URL` / `DNSID_LOG_POLICY_FILE` | DNSid's managed catalog | Which transparency logs to trust. Set one, not both. |
| `DNSID_LOG_CHECKPOINT_MAX_AGE` | from the policy | The maximum checkpoint age, in seconds. Requires an operator policy. |
| `DNSID_DNSSEC_MODE` | `auto` | Only `auto` works today |
| `DNSID_AWS_KMS_KEY_ID` | none | Sign with this KMS key instead of `private.jwk` |
| `DNSID_AWS_KMS_ALGORITHM` | `ED25519_SHA_512` | Or `ECDSA_SHA_256` |
| `DNSID_AWS_KMS_RETAINED_KEY_IDS`, `DNSID_AWS_KMS_PENDING_KEY_IDS` | none | Comma-separated lists, used during key rotation |

With no policy variable set, the plugin trusts DNSid's managed logs. Peers
on DNSid Local then come back as "cannot verify" unless the agent runs under
`dnsid local run` or `dnsid local env`, which set `DNSID_LOG_POLICY_URL`.

## Bring-online states

The `SessionStart` hook reads the agent's registration:

| Registration | What the hook does |
|---|---|
| `READY` | Nothing. It tells the model the identity is online. |
| `VERIFIED` and registry-managed | Countersigns the prepared ISSUANCE and submits it. The state is saved in `issuance.json` next to the key, so a retry can resume. |
| anything else | Nothing. It tells the model what the accountable entity still has to do. |

Requests from the hook carry a 5-minute JWT signed by the agent's own key.
No organization credential is present at runtime. A `SessionStart` hook
cannot block the session, so failures reach the model only as context.

## Reading denials

The plugin's runtime skill explains these messages to the running model. For
the person debugging:

- `DNSid: <host>: state REVOKED|RETIRED|PENDING`: the identity exists but is
  not live.
- `DNSid: <host>: <Code>: <detail>`: verification failed. `DNSResolution`
  means no record (wrong host, or the peer has not run `dnsid log issue`).
  Other codes: `RecordInvalid`, `SignatureInvalid`, `TLSError`,
  `StatusUnavailable`, `StatusNotActive`, `LogError`.
- A detail containing `Cannot verify` or `Out of scope`: this verifier could
  not judge the peer, usually because no log trust is configured for that
  peer's log. Fix the log-policy configuration. The peer may be fine.
- `DNSid: verification did not complete: <detail>`: the hook itself failed.
  This is an operator problem.

## Layout

```
hooks/hooks.json   PreToolUse (WebFetch|mcp__.*) → dist/verify/hook.js; SessionStart → dist/online/hook.js
.mcp.json          stdio MCP server "dnsid": verify, fetch
skills/dnsid/      runtime skill for the model (how to read DNSid: messages)
examples/minimal/  alice.ts (the guide's agent) and bob.ts (a peer that verifies with createVerifier)
examples/demo/     a chat UI with Alice in which each protocol step renders as a card
```
