---
name: dnsid-sdk
description: >-
  Write code with the DNSid SDKs (Go `github.com/dnsid-ai/dnsid-go`,
  TypeScript `@dnsid-ai/*`, Python `dnsid`). Covers verifying another agent's
  domain, protecting an HTTP API so it accepts only DNSid-signed requests,
  signing outbound requests with RFC 9421, minting and verifying DNSid
  JWT/OIDC tokens, configuring transparency-log trust, key providers (local
  files, AWS KMS), and publishing a self-managed `_dnsid` record. Use this
  skill whenever the user writes, reviews, or debugs code that imports a DNSid
  SDK. Also use it when they ask to "add DNSid", "verify the caller", "sign
  requests as my agent", or "check the agent's identity" in a service, or when
  they hit a DNSid `VerificationError`, even if they do not name the SDK. For
  the protocol concepts, use the dnsid skill. For a local environment to test
  against, use dnsid-cli. For framework-specific wiring (A2A, LangGraph, MCP,
  Agent SDK, edge), also use dnsid-integrations.
---

# DNSid SDKs

There are three open-source SDKs (Apache-2.0). They have the same surface and
are packaged differently. The Go module is the reference implementation of
the protocol. Each SDK does the following:

- **verify** a peer domain (`VerifyDomain`)
- **sign and verify** RFC 9421 HTTP requests, JWTs or JWS, and OIDC tokens
- **publish** a self-managed record
- verify **lifecycle-log** evidence
- manage keys through a **KeyProvider**

## Install

| | Install | Runtime | Notes |
|---|---|---|---|
| Go | `go get github.com/dnsid-ai/dnsid-go` then `go mod tidy` | Go 1.26.6+ | One module. Subpackages: `config`, `httpsig`, `jose`, `oidc`, `webbotauth`, `log/c2sptlog`. Separate module `key/aws`. Run `tidy` after the first import of `config`. |
| TypeScript | `npm install @dnsid-ai/sdk` + one package per capability | Node 22+, ESM or CJS | `@dnsid-ai/http-signatures`, `@dnsid-ai/jose`, `@dnsid-ai/oidc`, `@dnsid-ai/log-c2sp-tlog`, `@dnsid-ai/registry`, `@dnsid-ai/key-aws`, `@dnsid-ai/key-gcp`, `@dnsid-ai/web-bot-auth`. Node helpers are in `@dnsid-ai/sdk/node`. |
| Python | `pip install "git+https://github.com/dnsid-ai/dnsid-py.git"` | Python 3.11+ | **Not on PyPI yet.** Install from git. One `dnsid` package. Add the `[aws]` extra for KMS: `pip install "dnsid[aws] @ git+https://github.com/dnsid-ai/dnsid-py.git"`. |

Check the installed version (`go list -m`, `npm ls`, `pip show dnsid`) before
you trust an API name. The SDKs are pre-1.0 and their surfaces still change.

## Pick the right reference

Read **one** language file. It has working code for every task below:

- Go: `references/go.md`
- TypeScript: `references/typescript.md`
- Python: `references/python.md`

Read `references/log-trust-and-keys.md` when you configure trust for a log
that is not on DNSid Local (managed logs, a trust profile, or a policy file),
when you add a `logchk` check before a high-value operation, or when you
rotate keys or use KMS.

## The identity manager

Everything starts from an **IdentityManager**. Pick the constructor that
matches where the identity and trust settings come from:

| Situation | Go | TypeScript | Python |
|---|---|---|---|
| Under `dnsid local run`, or after `eval "$(dnsid local env <agent>)"` | `config.IdentityManagerFromEnvironment` | `createNodeIdentityManagerFromEnvironment` | `identity_manager_from_environment` |
| An identity the CLI wrote to `~/.dnsid` | `config.IdentityManagerFromDnsid` | `createNodeIdentityManagerFromDnsid` | `identity_manager_from_dnsid` |
| Verify-only, with explicit log trust | `dnsid.NewVerifier(dnsid.WithLogRegistry(r))` | `createNodeIdentityVerifier({}, { logRegistry: r })` | `IdentityManager(deps=IdentityManagerDependencies(log_registry=r))` |
| Full explicit config and key provider | `dnsid.NewIdentityManager(cfg, kp)` | `createNodeIdentityManager(cfg, { keyProvider })` | `IdentityManager(DnsidConfig(...), kp)` |

A verifier does not need a key of its own. It does need **log trust**. Every
verification checks the peer's lifecycle log, and an SDK with no trusted log
reader fails closed. The environment constructors set up log trust from
`DNSID_LOG_POLICY_URL`, `DNSID_LOG_POLICY_FILE`, or
`DNSID_LOG_TRUST_PROFILE_FILE`. In other setups you pass a log registry
yourself.

Build the manager **once** and reuse it. It holds the verification cache, the
JWKS and status freshness state, and the store of trusted checkpoints that
gives rollback protection. A new manager for each request throws all of that
away and repeats DNS, HTTPS, and log fetches on every call.

## Rules for correct DNSid code

These rules exist because breaking them gives code that looks like it works
on the happy path but either lets attackers through or locks legitimate
callers out.

1. **Get log trust from your own configuration, never from the peer.** Use
   the managed catalog, a trust profile, or a policy file or URL that you
   obtained through a trusted channel. Never build a policy location from the
   record's `lr=`, the log prefix, or anything the log server or peer
   advertises. If you did, whoever controls the record would also control
   the evidence for it.

2. **Treat any verification error as "not verified."** Show the code to
   operators. Branch on it with the **SDK's own constants**, never with string
   literals, because the spellings differ by language:

   | Meaning | Go (`dnsid.VerificationCode*`) | TypeScript (`VerificationCode.*`) | Python (`VerificationCode.*`) |
   |---|---|---|---|
   | DNS lookup failed | `dns_resolution` | `DNSResolution` | `DNS_RESOLUTION` |
   | Record malformed or ambiguous | `record_invalid` | `RecordInvalid` | `RECORD_INVALID` |
   | `sg=` did not verify | `signature_invalid` | `SignatureInvalid` | `SIGNATURE_INVALID` |
   | Status not `ACTIVE` (revoked or retired) | `status_not_active` | `StatusNotActive` | `STATUS_NOT_ACTIVE` |
   | Status endpoint unreachable | `status_unavailable` | `StatusUnavailable` | `STATUS_UNAVAILABLE` |
   | Log evidence failed or untrusted | `log_error` | `LogError` | `LOG_ERROR` |
   | Blocked by your `trustedEntities` | `counterparty_not_accepted` | `CounterpartyNotAccepted` | `COUNTERPARTY_NOT_ACCEPTED` |

   The full list also has `dnssec_failed`, `tls_error`, `key_age_exceeded`,
   the lifecycle-log codes, and the profile codes for tokens and signatures.
   The SDKs do not always classify the same situation the same way. For
   example, a name with no `_dnsid` record is `dns_resolution` (transient) in
   Go, `DNSResolution` (not transient) in TypeScript, and `RECORD_INVALID` in
   Python. So branch on codes only for messages and metrics. Never let a
   specific code decide that a peer is allowed.

3. **Use `transient` only to decide whether to retry.** It never means
   "let it through." The status endpoint being down or the log being
   unreachable makes the result *indeterminate*. Fail closed by default. If a
   route really must fail open, make that an explicit per-route decision in
   code, and never log or report the caller as verified or `ACTIVE`.

4. **Verification is not authorization.** A valid result proves which
   accountable entity stands behind the caller, not that the caller may act.
   Restrict who you accept. Use the manager's `trustedEntities` allowlist on
   governance IDs (exact match, optionally pinned to entity-key thumbprints).
   Then check per-route permissions against the verified domain. An *empty*
   allowlist denies everyone. A missing allowlist makes no decision.

5. **Bind identity to what the SDK verified, never to what the client says.**
   Take the caller from the returned `VerifiedDomain` (`Domain()` /
   `.domain`), not from a header, the request body, or the `keyid` string.

6. **When you verify inbound HTTP signatures:**
   - Rebuild the request URL from your service's **configured public
     origin**, for example `https://agent.example`. The signature covers
     `@authority` and `@target-uri` as the client sent them. Behind a proxy
     or load balancer your server sees a different scheme or host. Do not
     "fix" this by trusting the incoming `Host` or `X-Forwarded-*` headers.
     Pin the origin in config.
   - Pass the **exact raw body bytes** to the verifier. Do not pass a
     re-serialized parsed body. Buffer the body with a size cap, verify it,
     then hand the same bytes to your handler. When a body is present, the
     SDKs require a covered `Content-Digest` and check it themselves.
   - **Stop replays.** Verification checks freshness (`created`, at most 5
     minutes by default), not reuse. For state-changing routes, remember each
     `(keyid, nonce)` until the signature's maximum age has passed, and
     reject repeats. Use a shared store (for example Redis `SET NX EX`) when
     you run more than one replica.
   - Use an RFC 9421 `tag` that names your application. The signer sets it,
     and the verifier requires it (TypeScript `requiredTag`, Python
     `required_tag`). This stops a signature made for one application from
     being accepted by another.
   - Answer every failure with `401` and a generic body. Log the code on the
     server side.

7. **When you sign outbound requests,** wrap the HTTP client once (signed
   client, signed fetch, or signed httpx client), so that no code path can
   forget to sign. If an agent's model chooses the URLs, verify the
   *destination* domain before sending as well. Then a prompt cannot steer
   the agent into sending signed requests to an arbitrary host. Use a
   separate, plain client for ordinary APIs that have no DNSid identity.

8. **Do not hand-roll the protocol.** Use the SDK for record serialization
   and signing, JWKS checks, RFC 9421 signature bases, and log proofs. These
   checks are subtle: the ek/ku distinctness check, the `gi` host check,
   multi-string TXT records, and stream completeness.

9. **Keep keys out of logs and out of the repo.** Never print private JWKs,
   tokens, or `dnsid export` archives. Keys under `~/.dnsid` belong to the
   CLI. TypeScript and Python load them as read-only views. If the SDK has to
   rotate keys, give it its own key store.

10. **Do not accept `testnet` in production.** A DNSid Local identity carries
    log scope `testnet`. Production verifiers should be configured only with
    production log trust (managed `public` logs, or your own profile), so
    that local identities fail.

## Test against a real identity

Run your code against DNSid Local rather than mocks. The environment
constructors then work with no code changes:

```bash
dnsid local up
dnsid local agent ensure alice --upstream http://localhost:3001
eval "$(dnsid local env alice)" && dnsid log issue --domain alice.test   # publish alice's record
dnsid local run bob -- <your verifier or server command>                  # runs as bob.test, can verify alice.test
```

A good smoke test covers four cases: verify `alice.test` (expect `ACTIVE`),
verify `nope.test` (expect a `VerificationError`), send a signed request that
passes, and send a tampered body that fails. Each language reference has this
code. For the CLI side, see dnsid-cli.

## Tokens instead of signed requests

Use JWTs when the receiver expects a bearer token: cloud IAM federation, API
gateways with JWT authorizers (for example AgentCore Gateway `CUSTOM_JWT`), or
existing OAuth middleware.

- **DNSid JWT or JWS (JOSE profile):** the agent signs with its operational
  key, and the receiver checks the token against the issuer domain's
  published key. Go `jose`, TypeScript `@dnsid-ai/jose` (`JoseProfile`),
  Python `dnsid.jose`.
- **OIDC:** the agent signs an RFC 7523 assertion and exchanges it at an OIDC
  issuer for an access token. The receiver checks the issuer signature, the
  audience, the time claims, *and* the subject's DNSid identity. Go `oidc`
  (`GetOIDCToken`, `VerifyOIDCToken`), TypeScript `@dnsid-ai/oidc`
  (`OIDCProfile`), Python `dnsid.oidc` (`mint_oidc_token`,
  `verify_oidc_token`). On DNSid Local, `dnsid token --audience <aud>` mints
  one.

Always pin the audience, keep token lifetimes short, and require `jti` if you
need to detect replays. Cookbook recipe 29 is a complete OIDC example in Go.

## API references

The docs site has full per-language references. Fetch them instead of
guessing a signature:

- Go: https://docs.dnsid.ai/reference/go/overview
- TypeScript: https://docs.dnsid.ai/reference/ts
- Python: https://docs.dnsid.ai/reference/py/overview
- Everything as one file: https://docs.dnsid.ai/llms-full.txt
