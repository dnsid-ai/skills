---
name: dnsid
description: >-
  How the DNSid protocol works: verifiable, DNS-anchored identity for AI agents
  (IETF draft-ihsanullah-dnsid). Covers the `_dnsid` TXT record and its tags,
  the entity key versus the operational key, the lifecycle log (C2SP
  transparency log), live status, what a passing verification proves, and what
  DNSid does not do. Use this skill whenever the user mentions DNSid, a
  `_dnsid` record, `dnsid-draft-01`, or agent identity anchored in DNS. Also
  use it when they ask how an agent can prove who it is, or how to verify
  another agent or decide whether to trust it. Use it to read or debug a
  `_dnsid` record, to judge whether DNSid fits a design, and before you design
  any DNSid integration. For commands, use dnsid-cli. For code, use dnsid-sdk.
  For A2A, LangGraph, MCP, Agent SDK, or edge integrations, use
  dnsid-integrations.
---

# DNSid protocol

DNSid gives an AI agent an identity that anyone can verify with public DNS and
HTTPS. The agent's name is a domain (an FQDN). The organization that is
responsible for the agent (the **accountable entity**) signs a TXT record at
`_dnsid.<agent-fqdn>`. That record points to the agent's public key, its live
status, and a lifecycle log. Verifiers need no account, no central directory,
no shared secret, and no prior arrangement with the agent.

TLS proves you reached the right *server*. DNSid proves you are dealing with
the right *agent*, and shows which accountable domain stands behind it.

Use this skill to explain the model and reason about it correctly. For hands-on
work, use the sibling skills.

## The pieces

For an agent `agent.example`, operated by the accountable entity `example.com`:

| Piece | Where | Who signs or serves it |
|---|---|---|
| Identity record | TXT at `_dnsid.agent.example` | Signed by the entity key (`sg=`) |
| Entity key (`ek`) | JWKS at the `ek=` URL, on `gi` or below it | The accountable entity holds the private key |
| Operational key (`ku`) | JWKS at the `ku=` URL, on the agent FQDN | The agent holds the private key |
| Status | JSON at the `su=` URL, for example `{"state":"ACTIVE",...}` | The operator of the status endpoint |
| Lifecycle log | Stream named by `lr=` | Events signed by the entity key, the operational key, or both |

**Two keys, two jobs.** The **entity key** signs the record and lifecycle
events that the accountable entity authorizes, such as revocation. The
**operational key** signs runtime work: HTTP requests, JWTs, and challenges.
It also countersigns the issuance and authorizes its own rotation. The two
keys must be different key material (compared by their RFC 7638 thumbprints).
This split limits damage. Someone who steals the operational key can
impersonate the agent at runtime, but cannot forge a new owner-signed record.
Someone who steals the entity key can forge accountability claims, but does
not get the agent's operational key.

**Bilateral issuance.** The `ISSUANCE` event in the log carries two
signatures: one from the entity key and a countersignature from the agent's
initial operational key. So an organization cannot claim an agent it does not
operate, and an agent cannot claim an organization that never enrolled it.

## The record

This is a record as DNSid Local publishes it (with the signature shortened):

```txt
v=dnsid-draft-01;ek=https://dnsid.alice.test/.well-known/dnsid-ek.json;gi=alice.test;ku=https://alice.test/.well-known/jwks.json;lr=c2sp-tlog:testnet:https://registry.test#ag-b195ab6d38b871f604e06da7;sg=XImCN01d…6MbhvS61jgni2oRFKSLdDw;su=https://registry.test/v1/status/alice.test
```

| Tag | Required | Meaning |
|---|---|---|
| `v` | yes, always first | Wire profile. Implementations publish `dnsid-draft-01`. Verifiers also accept the draft's literal `DNSid1`, but tools must not publish it yet. |
| `gi` | yes | Governance identifier: the accountable entity's lowercase domain |
| `ek` | yes | HTTPS JWKS URL for the entity key. Its host must be `gi` or a subdomain of `gi`. |
| `ku` | yes | HTTPS JWKS URL for the agent's operational key |
| `lr` | yes | Lifecycle-log reference. For C2SP: `c2sp-tlog:<scope>:<log-prefix>#<stream-id>` |
| `su` | yes | HTTPS URL of the live status document |
| `sg` | yes | Entity-key signature over the other tags, as unpadded base64url |
| `fl` | no | Comma-separated policy flags: `logchk` (verifiers should check log non-revocation for high-value operations) and `mtls` |
| `ka` | no | Maximum operational-key age: `24h`, `7d`, `30d`, or `90d` |
| `cu` | no | URL of a capabilities document |

Wire rules that cause real bugs:

- The value is one string of `tag=value` pairs separated by `;`. `v` comes
  first, and publishers sort the other tags by name. Duplicate tags are
  rejected. Unknown tags are kept, and they are covered by the signature.
- **The signing input** is every tag except `sg`, sorted by tag name, joined
  with `;`, with no whitespace, encoded as US-ASCII. Do not build this input
  yourself. Use an SDK (`CreateTXTRecord` / `createTxtRecord` /
  `create_txt_record`) or `dnsid record publish`.
- A record is longer than 255 bytes, so DNS stores it as several character
  strings. `dig` prints them as separate quoted chunks. Join the chunks with
  no separator before you parse them.
- There must be exactly one DNSid TXT record at the name. More than one is
  `record_invalid`.

The deeper detail is in `references/record-format.md`: endpoint JSON shapes,
log references, the C2SP log policy, and flags. Read it when you parse,
publish, or debug a record by hand, or when you host the endpoints yourself.

## Lifecycle and status

Lifecycle events: `ISSUANCE`, `KEY_ROTATION`, `REVOCATION` (forced,
permanent, with a reason), `RETIREMENT` (graceful, permanent), `MIGRATION`
(move to another log method), and `DELEGATION` (an agent grants limited,
expiring authority to another agent).

**Protocol status** comes from the `su=` URL. Its states are `PENDING`,
`PROVISIONING`, `VERIFYING`, `ACTIVE`, `RETIRED`, and `REVOKED`. Only `ACTIVE`
passes verification. `REVOKED` and `RETIRED` are terminal. Nothing can
un-revoke an identity. You can only register a new identity, with new keys,
on the same domain.

**Registration status** is a different thing. It is the registry's workflow
state for the operator (`PENDING → PROVISIONING → VERIFICATION → VERIFIED →
READY`, plus `ERROR`, which can recover). `dnsid status` shows it. Verifiers
never read it. When a registration reaches `READY`, the `su=` URL serves
`ACTIVE`. Do not mix the two up when you explain an agent's state.

The status endpoint answers "is it live now?" The log answers "what happened,
and does the current key chain back to issuance?" A fresh log view does not
replace a fresh status check.

## What verification does

A complete verifier (the SDKs' `VerifyDomain`, or `dnsid record verify`) does
these steps:

1. Resolve `_dnsid.<fqdn>`. Require exactly one record, join its strings, and
   parse it.
2. Apply DNSSEC policy. If DNSSEC validation fails, the record is unusable. An
   unsigned zone gives weaker assurance that rests on the Web PKI.
3. Fetch the `ek` JWKS over HTTPS. Check that its host is under `gi`. Verify
   `sg` with its one current key.
4. Fetch the `ku` JWKS over HTTPS from the agent FQDN. Check that the `ku` key
   differs from the `ek` key.
5. Using an **independently trusted** log policy, verify the bilateral
   `ISSUANCE` and the chain of key rotations to the current `ku` key.
6. Fetch fresh status from `su` and require `ACTIVE`.
7. The application verifies its own message, token, or signature with the
   operational key.

**A pass proves** that the agent's current key is bound to an accountable
domain, that the binding is live, and that the binding has a verifiable
history. **A pass does not prove** that the accountable entity is reputable,
or that the agent may do what it is asking. Those decisions are your policy.
Always restrict which accountable entities (`gi` values) you accept. The SDKs
have a `trustedEntities` allowlist for this.

Results come in three kinds. Keep them apart in code and in what you tell the
user:

- **Verified**: every check passed and the state is `ACTIVE`.
- **Failed**: definite evidence against the identity. Examples: bad signature,
  `REVOKED`, a broken key chain.
- **Indeterminate (cannot verify)**: the check could not finish. Examples: the
  status endpoint is down, the log is not trusted by this verifier, DNS timed
  out. This says nothing bad about the peer. Never report it as verified or
  `ACTIVE`, and never describe the peer as malicious because of it. The SDK
  error's `transient` flag says whether a retry might help.

**Trust in the log is something you configure. Never discover it.** The C2SP
log policy (log key, witnesses, quorum) is a trust anchor. Get it from your
own configuration: DNSid's managed catalog in the SDK, a trust profile, or a
policy file or URL that you obtained through a trusted channel. Never derive
it from the record's `lr=`, from the log server, or from any value the peer
supplies. If you did, an attacker who controls a record would also control
the log that vouches for it.

## How an agent proves who it is

1. **Native verification.** The receiver calls `VerifyDomain(agent-fqdn)`.
   Nothing extra crosses the wire.
2. **Signed HTTP requests (RFC 9421).** The agent signs each request with its
   operational key. `keyid` is `<domain>#<kid>`. The receiver verifies the
   domain, then checks the signature. Use this for agent-to-agent and
   agent-to-API calls.
3. **Signed JWTs and OIDC.** Use these when the receiver expects a bearer
   token, for example a cloud IAM or a gateway with JWT auth. The token is
   signed with the operational key, and the receiver checks it against the
   issuer domain's keys.

## Where DNSid fits and where it does not

DNSid is the accountable-ownership layer (layer 1). It sits on DNS, ICANN, and
DNSSEC (layer 0). Workload identity (SPIFFE), tokens (OAuth/OIDC), credentials
(VCs), and policy engines sit above it and anchor on it.

Steer users away from these misuses:

- **Authenticating humans.** People do not own domains. Use the existing IdP,
  SSO, or passkeys.
- **Wrapping model API calls** (OpenAI, Anthropic, and so on). That is
  inference, not a trust boundary between agents.
- **Replacing TLS or the Web PKI.** DNSid works at the application layer and
  depends on TLS.
- **Authorization or reputation.** Verification says who. Your policy decides
  whether that agent may act.
- **Discovery or transport.** DNSid is neither. A2A, MCP, and HTTP carry the
  traffic, and DNSid identifies the parties.
- **Identity with no revocation plan.** Every deployment needs a revocation
  runbook and a status endpoint that does not cache `ACTIVE` for long.

## Environments

- **DNSid Local**: the full protocol in Docker on a laptop. It uses the zone
  `test` (`alice.test`) and the log scope `testnet`. It needs no account and
  no real DNS. Start here. See dnsid-cli.
- **A domain you own (self-managed)**: your DNS, your TLS, your JWKS and status
  hosting, and your keys. Anyone on the internet can verify it.

The SDK code is the same in both environments. Only configuration changes:
DNS server, CA bundle, and log trust. Verifiers should decide explicitly which
log scopes and environments they accept. A `testnet` identity should not pass
in production.

## Spec status

DNSid is an **individual** IETF Internet-Draft. It is not a working-group
document or a standard. The current version is `draft-ihsanullah-dnsid-01`
(submitted 2026-06-29, expires 2026-12-31). The Go SDK is the reference for
how the protocol behaves on the wire. The conformance suite
([dnsid-ai/dnsid-sdk-compliance](https://github.com/dnsid-ai/dnsid-sdk-compliance))
defines what counts as conformant, and it is the starting point for a new
language SDK.

## Sources

- Docs: https://docs.dnsid.ai (machine-readable: https://docs.dnsid.ai/llms.txt, https://docs.dnsid.ai/llms-full.txt)
- Draft: https://datatracker.ietf.org/doc/draft-ihsanullah-dnsid/
- SDKs: [dnsid-go](https://github.com/dnsid-ai/dnsid-go), [dnsid-ts](https://github.com/dnsid-ai/dnsid-ts), [dnsid-py](https://github.com/dnsid-ai/dnsid-py)
- Recipes: [dnsid-cookbook](https://github.com/dnsid-ai/dnsid-cookbook)

When this skill and the live docs disagree on something that changes over
time (versions, package names, whether something is published), the docs and
the installed tool win.
