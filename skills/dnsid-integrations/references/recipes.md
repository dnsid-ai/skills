# Cookbook recipes and SDK examples

Read this file before you adapt a recipe, so that you copy
from the right files. Paths are relative to the cookbook repo. Before you
point the user at a recipe, check that its directory exists. `INDEX.md` also
lists ideas that have no directory yet.

## Contents

- Runnable on DNSid Local
- Deploy-only (AWS plus a hosted DNSid issuer)
- Examples in the SDK repos
- Running a recipe

## Runnable on DNSid Local

### 01 — Publish `_dnsid` + JWKS (`recipes/01-publish-jwks/`)

Provisions an identity, then takes it apart by hand: it runs `dig` on the
record, reads every tag, serves the JWKS and fetches it with `curl`, matches
the served key to the local keypair, and checks live status. Use it to teach
the protocol or to debug publication. Files: `src/serve.py`,
`verify/verify.sh`.

### 06b — Go HTTP API verifies DNSid callers (`recipes/06b-go-http-stripe/`)

A fake Stripe-like ledger with `GET /v1/balance` and `POST /v1/balance/credit`
behind `dnsid-go` RFC 9421 verification. Callers that verify may read, and
only allowlisted writers may credit. Files: `src/server/main.go` (the
`authenticate` middleware and the writer allowlist), `src/agent/main.go`
(the signing client), and `src/internal/localregistry/` (log trust from
`DNSID_LOG_POLICY_URL`). The middleware rebuilds the public URL from
`r.Host`. When you adapt it, pin the host in config instead (see the dnsid-sdk
Go reference).

### 12 — A2A + DNSid (`recipes/12-a2a-dnsid/`)

Two Python A2A agents, Alice and Bob, exchange `a2a-sdk` JSON-RPC messages
signed with RFC 9421. Before calling, Alice verifies Bob's domain. Bob
verifies Alice's signature and identity.

- `src/agent_card.py`: agent card with a *required* DNSid signature
  extension, the tag `a2a-dnsid-http-sig-v1`, and the required covered
  components `@method`, `@target-uri`, `content-type`, `content-digest`,
  `a2a-version`, and `a2a-extensions`.
- `src/middleware.py`: inbound verification with `required_tag` and a pinned
  `public_url`.
- `src/client.py`: an outbound signed client.
- `verify/verify.sh`: the end-to-end checks.

TypeScript and Go versions are in `examples/a2a` of `dnsid-ts` and
`dnsid-go`.

### 29 — DNSid-authenticated message board (`recipes/29-dnsid-message-board/`)

A Go service. Its CLI client gets a short-lived OIDC token for each command
by running `dnsid token --domain … --audience …`. The server's
`VerifyOIDCToken` checks the issuer, the exact audience, the time claims,
`jti`, and the subject's full DNSid identity, then applies room roles (with
an optional Cedar/AVP adapter). Files: `src/internal/auth/verifier.go`,
`src/internal/cli/app.go`, and `src/internal/authorization/`. This is the
reference for the pattern "token instead of signature".

### 31 — LangGraph agent with a DNSid identity (`recipes/31-langgraph-dnsid-agent/`)

`lib/langchain-dnsid/` is a small reusable package. It is **not on PyPI**, so
vendor it or install it from the path. It contains:

- `ingress.py`: ASGI middleware that accepts only signed requests, checks
  them against a pinned public origin, requires a tag and `content-type`, and
  remembers nonces to stop replays. It puts the verified caller in
  `request.state.dnsid_caller`.
- `egress.py`: `dnsid_client(idm)`, an httpx client that verifies the
  destination host as a live DNSid identity and then signs. It refuses
  ordinary APIs on purpose. `fetch_tool(client)` exposes it to the model.
- `agent.py`: middleware that hides sensitive tools from callers who are not
  on an allowlist, and blocks them.
- `server.py`: an adapter for LangGraph's deployment server.

The model is never in the trust path. `verify/replay.py` shows the replay
check. Use this recipe as the template for any Python agent framework
(CrewAI, Strands, the OpenAI Agents SDK, and others). Swap the framework
glue and keep `ingress.py` and `egress.py`.

## Deploy-only (AWS plus a hosted DNSid issuer)

These recipes show patterns for Amazon Bedrock AgentCore. They need an AWS
account and a hosted DNSid identity, so they do not run on DNSid Local. Read them for the
pattern, and tell the user what they require.

- **07** `recipes/07-agentcore-gateway-mcp-image-poc/`: an AgentCore Gateway
  MCP image tool with DNSid JWT auth, interceptors, and a local UI.
- **07b** `recipes/07b-agentcore-gateway-oidc-image/`: the minimal version.
  It uses `CUSTOM_JWT` and a direct Lambda target.
- **28** `recipes/28-bedrock-agentcore-github-review/`: a Strands PR-review
  agent on AgentCore Runtime that mints DNSid OIDC tokens with `dnsid-py`.
- **30** `recipes/30-agentcore-gateway-dnsid-oidc-orders/`: verifies a
  DNSid-signed order in a Gateway interceptor and rejects modified or
  replayed actions.

## Examples in the SDK repos

Each SDK repo (`dnsid-go`, `dnsid-ts`, `dnsid-py`) has an `examples/`
directory with `a2a`, `local-key-provider`, `oidc`, `validate-domain`, and
`webbotauth`. Go also has `registry-publish`. Use them when a recipe would be
too much and you only need the smallest working call.

## Running a recipe

```bash
git clone https://github.com/dnsid-ai/dnsid-cookbook && cd dnsid-cookbook/recipes/<recipe>
make bootstrap   # starts DNSid Local and provisions the recipe's identities
make run         # runs the demo
make verify      # end-to-end assertions, the proof the recipe works
make clean       # stops DNSid Local (see below)
```

Most recipes (01, 06b, 12, 31) use the user's **shared** DNSid Local
(`~/.dnsid-local`), and their `make clean` runs `dnsid local down`. That
stops the network for every other project too, although it keeps the
state. Recipe 29 is isolated, using `--state .dnsid-local`. Read the
Makefile before you run `clean`, and tell the user when it will touch shared
state.

The prerequisites are Docker, `make`, the `dnsid` CLI, and the language
toolchain. Python recipes use `uv`.

To add a new recipe, copy `RECIPE_TEMPLATE.md` and follow `CONTRIBUTING.md`.
A recipe ships only when `make verify` passes from a clean state.
