---
name: dnsid-cli
description: >-
  Install and use the `dnsid` CLI and DNSid Local, the complete DNSid network
  (DNS, TLS, registry, transparency log) that runs in Docker on a laptop. Use
  this skill whenever the user wants to try DNSid, give a local agent an
  identity, run a service as a DNSid agent (`dnsid local run`), publish or
  inspect a `_dnsid` record, verify a domain from the command line, mint a
  token, export credentials, or revoke an identity. Use it whenever a task
  needs a working DNSid environment to test against, even if the user does not
  name the CLI. That includes running a cookbook recipe or checking that SDK
  code works. Also use it to troubleshoot `dnsid` command errors, agents stuck
  in VERIFIED, or `_dnsid` lookups that fail locally.
---

# dnsid CLI and DNSid Local

The `dnsid` CLI does three jobs:

- runs **DNSid Local**, a disposable DNSid network on your machine
- inspects and verifies the `_dnsid` record of any domain
- drives a registry through registration, issuance, tokens, and revocation

The SDKs do not depend on the CLI, but it is the fastest way to get a real
identity to develop against. For the protocol concepts behind these commands,
see the dnsid skill.

## Install

```bash
brew install dnsid-ai/tap/dnsid                       # macOS, Linux
curl -fsSL https://docs.dnsid.ai/install.sh | sh      # macOS, Linux; checks SHA256SUMS
scoop bucket add dnsid https://github.com/dnsid-ai/scoop-bucket && scoop install dnsid   # Windows
dnsid --version
```

To upgrade, use the same channel you installed with. If more than one copy is
installed, `which -a dnsid` shows which one wins on PATH. DNSid Local also
needs Docker with Compose, running.

## The local loop

```bash
dnsid local up                                               # 1. start the network (safe to rerun)
dnsid local agent ensure alice --upstream http://localhost:3001   # 2. key + registration + TLS + route
eval "$(dnsid local env alice)"                              # 3. load alice's DNSID_* settings into this shell
dnsid log issue --domain alice.test                          # 4. countersign ISSUANCE; publishes the record
dnsid status --domain alice.test                             # 5. expect READY
dnsid record verify --domain alice.test                      # 6. verify the way a stranger would
```

What each step does, and why it matters:

1. `local up` starts CoreDNS (authoritative for the zone `test`, on
   `127.0.0.1:7753`), a Caddy HTTPS proxy with a local CA (on 443), and the
   registry with its lifecycle log (on `127.0.0.1:7755`). State lives in
   `~/.dnsid-local`.
2. `agent ensure` expands the short name `alice` to `alice.test`. It generates
   an Ed25519 key, registers the agent, issues a TLS certificate, and routes
   `https://alice.test` to your upstream. It is safe to rerun: an existing
   agent is updated to the given `--upstream`. Afterwards the agent is
   `VERIFIED`, which means registered but **not yet published**.
3. `local env alice` prints the exports that point every client (CLI and SDKs)
   at the local DNS, CA, and log policy, and at alice's keys. These settings
   apply to one shell only. In a new terminal, run the `eval` again.
4. `log issue` is the step people miss. It countersigns the bilateral ISSUANCE
   with the agent's key, which publishes the `_dnsid` record and moves the
   agent to `READY`. Until this runs, lookups fail because there is no
   record. (The Claude Agent SDK plugin runs this step itself at session
   start.)
5. `status` reports where the agent stands, and while the agent is still in
   progress it prints the next command to run. Follow that hint.
6. `record verify` runs full SDK verification (DNS, both JWKS, signature,
   status, transparency log). It exits non-zero on failure, so you can use it
   in scripts and CI.

The record can take a few seconds to show up in local DNS after `log issue`.
If `record inspect` reports `no such host` right after a successful issue,
wait about 5 seconds and try again before you investigate further.

### Run a process as an agent

`dnsid local run` does all of the above for one command. It starts the network
if needed, ensures the agent exists, sets its environment, and runs your
command. The exit code of your command becomes the exit code of `dnsid local
run`.

```bash
dnsid local run alice -- npm run dev                   # free port chosen, exported as PORT
dnsid local run alice --port 3001 -- python server.py  # fixed port
```

`local run` does not run `dnsid log issue`. If the agent has to be verifiable
by others (and not only able to verify peers), run `log issue` once after the
first `local run` or `agent ensure`.

### What `dnsid local env <agent>` exports

| Variable | Used for |
|---|---|
| `DNSID_DOMAIN`, `DNSID_GOVERNANCE_ID`, `DNSID_AGENT_NAME` | The agent's identity |
| `DNSID_CONFIG_DIR`, `DNSID_KEY_STORE` | Where its config and keys live (`~/.dnsid-local/agents/…`) |
| `DNSID_DNS_SERVER` (`127.0.0.1:7753`) | Resolves `*.test`. Without it, lookups go to public DNS and fail. |
| `DNSID_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS` | Trust the local CA for HTTPS |
| `DNSID_PRIVATE_HOSTS` (`.test`) | Lets verifiers fetch URLs that resolve to loopback |
| `DNSID_LOG_POLICY_URL` | The trusted log policy for the local log |
| `DNSID_LOG_REF`, `DNSID_STATUS_URL`, `DNSID_KU_URL` | The agent's publication settings |
| `DNSID_SERVER`, `DNSID_REGISTRY_URL`, `DNSID_API_KEY` | The local registry (the API key is the fixed value `testnet`) |
| `PORT`, `DNSID_AGENT_UPSTREAM` | Where the agent's own server listens |

Always name the agent. `dnsid local env` with no name prints the network
settings *plus* identity variables for a default agent (`DNSID_DOMAIN` and
others). Code that loads that output acts as an agent you did not choose.
Add `--format dotenv` or `--format json` when you want a file instead of
shell exports.

The SDKs' environment constructors read these variables directly:
`config.IdentityManagerFromEnvironment` (Go),
`createNodeIdentityManagerFromEnvironment` (TypeScript), and
`identity_manager_from_environment` (Python). See dnsid-sdk.

### Reaching local agents with other tools

Only clients that use `DNSID_DNS_SERVER` can resolve `*.test`. Browsers and
plain `curl` cannot. For `curl`, pin the name and trust the CA:

```bash
curl --cacert ~/.dnsid-local/certs/root-ca.pem \
     --resolve alice.test:443:127.0.0.1 https://alice.test/.well-known/jwks.json
dig @127.0.0.1 -p 7753 _dnsid.alice.test TXT
```

## Day-to-day commands

| Command | Use |
|---|---|
| `dnsid local agent list` | List local agents |
| `dnsid local agent remove <name>` | Delete one local agent |
| `dnsid local down` | Stop the containers and keep the state |
| `dnsid local reset` | Clear all agents but keep the network running |
| `dnsid local reset --hard` | Stop everything and delete `~/.dnsid-local` |
| `dnsid record inspect --domain <fqdn>` | Print any domain's record one tag per line, exactly as published |
| `dnsid record verify --domain <fqdn>` | Run full verification, exit 1 on failure |
| `dnsid status --domain <fqdn>` | Show registration state, record expiry, errors, and the next step. Works for any domain, because the status endpoint is public. |
| `dnsid token --domain <fqdn> --audience <aud>` | Mint a short-lived OIDC access token for the agent (RFC 7523 assertion exchanged at the registry's issuer). Works on DNSid Local. |
| `dnsid export -o creds.tar.gz` | Pack config and **unencrypted** private keys for another machine |
| `dnsid revoke --domain <fqdn> --reason owner_request\|key_compromise` | Revoke permanently |

Global flags: `--output json|pretty`, `--config-dir` (`DNSID_CONFIG_DIR`),
`--server` (`DNSID_SERVER`, default `http://127.0.0.1:7755`), and `--debug`
(prints HTTP traffic). Use `--output json` when a script or an agent will
parse the output.

`references/commands.md` has every flag, the port and state overrides, and
self-managed publishing. Read it when you need a flag that is not shown here,
when you run several local networks, or when you publish on a real domain.

## Before you run a destructive command

These commands cannot be undone. Unless the user has clearly asked for the
exact effect, ask before you run them:

- **`dnsid revoke`** is terminal. No command un-revokes an identity. The
  status endpoint serves `REVOKED` at once, verification fails from then on,
  and the log keeps the revocation forever. The domain can later host a *new*
  identity with new keys. Use `--yes` only after the user has confirmed.
- **`dnsid local reset` / `reset --hard`** wipe *every* local agent, not only
  the one you are working on. Other projects or cookbook recipes may depend
  on them. Run `dnsid local agent list` first. To remove a single agent, use
  `dnsid local agent remove <name>`. To keep a project's agents separate, give
  it its own `--state` directory (for example `--state .dnsid-local`).
  `dnsid local down` stops the shared network for every project. Some
  cookbook recipes run it from `make clean`.
- **`dnsid export`** writes private keys in plaintext. Never commit the
  archive or paste its contents anywhere.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `lookup _dnsid.x.test … no such host` | The agent is not issued yet (run `dnsid log issue`), the record is still propagating (wait about 5 s), or this shell is missing `DNSID_DNS_SERVER` (run `eval "$(dnsid local env <name>)"`). |
| `dnsid status` shows `VERIFIED`, not `READY` | Run the `Next:` command it prints. This is usually `dnsid log issue --domain …`. |
| `dnsid agent list` says "No agents found" | That command queries a registry organization. For local agents, use `dnsid local agent list`. |
| TLS or certificate errors fetching `https://*.test` | The local CA is not trusted. Set `DNSID_CA_BUNDLE`, or `NODE_EXTRA_CA_CERTS` for Node, or pass `--cacert` to curl. Loading `local env` sets the first two. |
| Verification says the URL resolves to a private address | Set `DNSID_PRIVATE_HOSTS=.test` (from `local env`), or pass `--private-hosts`. This guard exists on purpose, so that verification cannot be steered into an internal network. |
| Verification fails on the log, or says it cannot verify | No trusted log policy is configured. Locally, `DNSID_LOG_POLICY_URL` comes from `local env`. For other domains, see the dnsid-sdk transparency-log reference. |
| `local up` cannot bind a port | Another process holds 443, 7753, or 7755. Pass `--proxy-port`, `--dns-port`, or `--registry-port`. The chosen values are saved in the state directory. |
| Docker errors | Start Docker. `local up` needs Compose. On the first run it pulls `ghcr.io/identity-digital/dnsid-local-registry`. |
| `dnsid testnet …` in old instructions | This is the earlier name for `dnsid local`. It still works, but use `local` instead. |

To debug a failing agent end to end, run `dnsid status --domain <fqdn>`. Then
run `dnsid record inspect --domain <fqdn>` to see whether the record exists.
Then run `dnsid record verify --domain <fqdn> --debug` to see which fetch
fails.

## Commands to leave alone

`dnsid --help` also lists `init`, `agent`, `zone`, `connector`, and `admin`.
These commands work with DNSid's hosted registry and need an organization API
key. Do not run them unless the user says they have a hosted account and asks
for one. `dnsid init` in particular registers against the hosted
sandbox by default. For local work, use `dnsid local …`. For your own domain,
use the self-managed path in `references/commands.md`.
