# dnsid command reference

Read this file when SKILL.md does not show the flag you need. If your installed binary disagrees with this
file, trust `dnsid <command> --help`.

## Contents

- Global flags
- `dnsid local …`
- Record commands
- Registration commands
- Publishing on a domain you own
- Exit codes and scripting

## Global flags

| Flag | Env | Default |
|---|---|---|
| `--server url` | `DNSID_SERVER` | `http://127.0.0.1:7755` (DNSid Local) |
| `--config-dir dir` | `DNSID_CONFIG_DIR` | `~/.dnsid`. For a local agent, `local env` sets this to `~/.dnsid-local/agents/<fqdn>`. |
| `--api-key key` | `DNSID_API_KEY` | none. `local env` sets it to `testnet`. |
| `--output json\|pretty` | | pretty for people, json for scripts |
| `--debug` | | prints HTTP requests and responses |
| `--version`, `-v` | | |

## `dnsid local …`

Every `local` subcommand accepts `--state dir` (default `~/.dnsid-local`).
Each state directory is a separate network with its own agents. Use a
project-local state directory (for example `--state .dnsid-local`, as
cookbook recipe 29 does) to keep a project's agents apart from your global
ones.

### `dnsid local up`

| Flag | Env | Default |
|---|---|---|
| `--zone` | | `test` |
| `--agent name=upstream` (repeatable) | | Registers agents during startup |
| `--image` | `DNSID_LOCAL_IMAGE` | `ghcr.io/identity-digital/dnsid-local-registry:main` |
| `--registry-port` | `DNSID_LOCAL_REGISTRY_PORT` | 7755 |
| `--dns-port` | `DNSID_LOCAL_DNS_PORT` | 7753 |
| `--proxy-port` | `DNSID_LOCAL_PROXY_PORT` | 443 |
| `--subnet cidr` | `DNSID_LOCAL_SUBNET` | Derived from the state directory |

Port and subnet choices are saved in the state directory, so later commands
reuse them. The old `DNSID_TESTNET_*` variable names still work. By default
the local registry signs its own witness cosignatures.

### `dnsid local run <name-or-fqdn> [flags] -- <cmd> [args…]`

This command registers the agent if it is missing, starts the network if it
is down, and runs `<cmd>` with the agent's environment set. It returns the
command's exit code.

- `--port p`: the port for the child process. Without it, a free port is
  chosen and exported as `PORT`.
- `--upstream url`: where `https://<agent>` is proxied. Default
  `http://localhost:<port>`.
- `--cu url` (`DNSID_CAPABILITIES_URL`): a capabilities URL to publish in the
  record.
- It also accepts the port, image, and subnet flags of `local up`.

It does **not** run `dnsid log issue`. A new agent stays `VERIFIED` until you
issue it.

### `dnsid local agent list|add|ensure|remove`

- `ensure <name> [--upstream url] [--cu url] [--format shell|dotenv|json] [-- cmd…]`:
  registers the agent if it is missing, and otherwise updates it to the given
  upstream. Without `--`, it prints the agent's environment. With `--`, it
  runs the command. Prefer `ensure` over `add` in scripts.
- `add <name> --upstream url`: registers the agent, and fails if it already
  exists.
- `remove <name>`: deletes one agent.
- `list`: shows domain, upstream, and local status.

### `dnsid local env [<name>] [--format shell|dotenv|json]`

With a name, it prints that agent's full set (see the table in SKILL.md).
With no name, it prints the network variables plus the identity of a default
agent. Prefer to name the agent explicitly.

### `dnsid local down` / `dnsid local reset [--hard]`

`down` stops the containers and keeps the state. `reset` clears the agents and
identities but leaves the network running. `reset --hard` also stops the
containers and deletes the state directory.

## Record commands

These commands work against any domain and need no credentials.

### `dnsid record inspect --domain <fqdn> [--dns-server host[:port]]`

This is a plain DNS lookup. It prints each tag exactly as published, so a
malformed record shows up as malformed. When the record has `lr=`, it also
prints the log checkpoint, the policy, and a stream-explorer link.

### `dnsid record verify [--domain <fqdn>] [flags]`

Runs the same full verification a relying party runs. `--domain` defaults to
the agent selected locally.

| Flag | Env | Purpose |
|---|---|---|
| `--dns-server host[:port]` | `DNSID_DNS_SERVER` | Resolver to use. Point it at a validating resolver to get a DNSSEC verdict. Without it, the CLI prints a warning and uses the system resolver. |
| `--ca-bundle path` | `DNSID_CA_BUNDLE` | Extra PEM CAs, for private or test CAs |
| `--private-hosts host` | `DNSID_PRIVATE_HOSTS` | Hosts or `.suffix` entries that may resolve to private or loopback addresses. Only `.test` is exempt by default. |
| `--log-policy path` | `DNSID_LOG_POLICY_FILE` | Trusted C2SP tlog-policy file |
| `--log-policy-url url` | `DNSID_LOG_POLICY_URL` | Trusted policy URL. Used only when neither of the two options above is set. |
| `--log-trust-profile path` | `DNSID_LOG_TRUST_PROFILE_FILE` | Trusted C2SP trust profile |

Successful output shows the version, the URIs, the governance ID, `DNSID
Verification: VALID`, `Status: ACTIVE`, the DNS TTL, and "Fresh Until".

### `dnsid record publish [--domain <fqdn> | --agent-id id] [--entity-key path]`

Before signing, the registry checks that the domain may publish: an
accountable entity exists, its governance domain is authorized, and you
belong to the agent's organization. For a self-managed agent, the CLI fetches
the canonical record content, signs it locally with the entity key
(`--entity-key`, or `entity_key_path` in `config.json`), and then either
publishes it through a delegated zone or prints the TXT record for you to add
to your own DNS.

## Registration commands

These commands act on the registry at `--server`. On DNSid Local, load
`dnsid local env <name>` first so that the server, API key, CA, and config
directory are all set. Select an agent with `--domain fqdn` or `--agent-id
id`.

| Command | Purpose |
|---|---|
| `dnsid status` | Registration state, environment, record expiry, the last error with its fix, the log reference, the stream explorer, and the next command to run |
| `dnsid verify` | Starts the registry's verification workflow (TLS, JWKS format, proof of possession) for a registration. This is not the same as `record verify`. |
| `dnsid challenge [--key path]` | Signs and submits the current proof-of-possession challenge. The default key is `private.pem` in the config directory. |
| `dnsid log issue [--key path]` | Countersigns and submits the ISSUANCE event. The default key is `private.jwk`. |
| `dnsid token --audience aud [--scope s] [--oidc-issuer url] [--key path]` | Mints an OIDC access token. The issuer comes from `--oidc-issuer`, `DNSID_OIDC_ISSUER`, the agent's config, or discovery, in that order. |
| `dnsid export [-o path]` | Writes a tar.gz (mode 0600) with `config.json`, `private.pem`, `public.jwk`, `private.jwk`, and the entity key if one is configured. Restore it with `tar xzf <archive> -C <config-dir>`. |
| `dnsid revoke --reason owner_request\|key_compromise [--yes]` | Revokes permanently, after a confirmation prompt unless `--yes` |

Registration states: `PENDING → PROVISIONING → VERIFICATION → VERIFIED →
READY`. `ERROR` can be retried: fix the cause that `dnsid status` reports,
then run `dnsid verify` again. `REVOKED`, `REJECTED`, and `CANCELLED` are
terminal.

The usual causes of `ERROR` on a real domain: the `_dnsid` TXT record does
not resolve yet, the TLS certificate is invalid, the JWKS URL cannot be
reached, or the challenge was never answered.

## Publishing on a domain you own

DNSid Local is for development. When others need to verify your agent, the
identity has to live on a domain you control. You publish the TXT record, and
you host both JWKS documents and the status document. The dnsid skill's
`references/record-format.md` has the checklist.

There are two ways to produce the signed record:

- **SDK**: build and sign the record in code (`CreateTXTRecord` /
  `createTxtRecord` / `create_txt_record`) with both key providers configured,
  then publish it with your normal DNS tooling. See the dnsid-sdk publishing
  reference. This path needs no registry and no account.
- **CLI**: `dnsid record publish --domain <fqdn>` signs with your entity key
  and prints the TXT record. It needs a registry that knows the agent.

Either way, finish with `dnsid record verify --domain <fqdn>` (with no
`DNSID_*` local settings loaded), so that the check runs against public DNS
the way a stranger's would.

The SDKs can load a CLI-provisioned identity from `~/.dnsid`:
`config.IdentityManagerFromDnsid`, `createNodeIdentityManagerFromDnsid`, or
`identity_manager_from_dnsid`. Keys under `~/.dnsid` are real credentials,
unlike the throwaway keys in `~/.dnsid-local`.

## Exit codes and scripting

- `record verify` exits non-zero when verification fails or the agent is not
  `ACTIVE`. You can use it directly as a CI gate.
- `local run` returns the child's exit code.
- Add `--output json` to any command you plan to parse.
