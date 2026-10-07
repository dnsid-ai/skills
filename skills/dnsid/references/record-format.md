# Record, endpoints, and log: wire-level detail

Read this file when you parse or debug a `_dnsid` record by hand, when you
host the endpoints for a self-managed identity, or when you explain exactly
what a verifier fetches. If you only need the concepts, SKILL.md is enough.

## Contents

- Looking at a live record
- Endpoint documents (ek, ku, su)
- Log references and log trust
- Flags and key age
- Revocation reasons
- Checklist for hosting a self-managed identity

## Looking at a live record

```bash
dig +short _dnsid.agent.example TXT
dnsid record inspect --domain agent.example        # one tag per line, exactly as published
dnsid record verify  --domain agent.example        # full verification, exits non-zero on failure
```

`dig` prints a long record as several quoted strings, for example
`"v=dnsid-draft-01;…;sg=XImC" "N01d…;su=https://…"`. Join them with nothing
in between. The split can land in the middle of a value, as in this example
where it falls inside `sg`.

For DNSid Local names (`*.test`), query the local resolver:
`dig @127.0.0.1 -p 7753 _dnsid.alice.test TXT`.

## Endpoint documents

**`ku=` (operational key JWKS)** is served from the agent FQDN. In the base
profile it holds exactly one current signing key. Every JWK has a `kid` and
an `alg`:

```json
{"keys":[{"kty":"OKP","crv":"Ed25519","alg":"EdDSA","use":"sig","kid":"lkbUGMjG9fke-frgfS1m2YPR-rMC9Vp0wLAQQ93ZaqI","x":"0YIAmfx-…"}]}
```

Supported algorithms are Ed25519 (`EdDSA`) and P-256 (`ES256`). A `kid` must
never contain `#`, because signers are identified as `domain#kid`. After a
revocation, the `ku` URL should return **410 Gone** with the body
`{"status":"revoked"}` instead of the key.

**`ek=` (entity key JWKS)** has the same shape, holds a different key, and is
served from `gi` or a subdomain of it. DNSid Local serves it at
`https://dnsid.<agent>/.well-known/dnsid-ek.json`. The path is not fixed. The
full URL is in the record.

**`su=` (status)** returns JSON with the protocol state:

```json
{"state":"ACTIVE","lastTransitionAt":"2026-10-07T20:11:41.491571781Z"}
```

Verifiers need a fresh response with `ACTIVE`. Whoever hosts this URL decides
how fast a revocation reaches verifiers. Serve `Cache-Control: no-store`, or a
very short max-age, and make sure no CDN keeps serving `ACTIVE` after a
revoke. After revoking, check both paths: fetch the URL raw, and run
`dnsid record verify`. They can disagree while a cache is stale.

There is no renew command and no background renewer. "Renewal" means
republishing the record.

## Log references and log trust

`lr=` has the form `method:entry-ref`. The C2SP transparency-log method:

```
c2sp-tlog:<scope>:<log-prefix>#<stream-id>
c2sp-tlog:public:https://log.dnsid.ai#EREREREREREREREREREREQ
c2sp-tlog:testnet:https://registry.test#ag-b195ab6d38b871f604e06da7
```

- `scope` is `public`, `testnet`, or `private-*`. A verifier should accept
  only the scopes it expects. In production, do not accept `testnet`.
- `log-prefix` is the URL prefix of the C2SP tiled log.
- `stream-id` is an opaque ID, chosen at random, for one identity instance.
  It is a stream fragment, not a URL you can open in a browser.

The C2SP log policy is a small text document that names the trusted log key,
the witness keys, and the quorum:

```
log registry.test+d7a4f31d+AXAcTUJb…
witness dnsid-witness-1 dnsid-testnet-witness+fc8d2fa8+BBgnoA4H…
quorum dnsid-witness-1
```

Verifiers get trust in one of these ways, and only from their own
configuration:

| Trust source | Use | Configure |
|---|---|---|
| DNSid-managed | Identities on `https://log.dnsid.ai` and `https://log.dev.dnsid.ai` (scope `public`) | Trust material built into the SDK. Select it explicitly in code, or with `{"logTrust":{"managed":true}}` in a deployment file. |
| Trust profile | A deployment that has its own C2SP trust profile | `DNSID_LOG_TRUST_PROFILE_FILE`, or pass it in code |
| Policy document | DNSid Local, or a deployment that distributes a policy | `DNSID_LOG_POLICY_FILE` or `DNSID_LOG_POLICY_URL` (set exactly one) |

DNSid Local exports `DNSID_LOG_POLICY_URL=https://registry.test/dnsid-policy`.
That value is trusted because your own `dnsid local env` produced it. It is
not trusted because of the URL itself. Never build a policy URL from an
`lr=` value.

What the C2SP verifier checks: the checkpoint signature and witness quorum,
Merkle inclusion, append-only consistency with checkpoints it has already
seen, the signatures on each event, stream order, and key continuity. One
inclusion proof shows only that an event exists. To show that nothing was
revoked, the verifier needs the complete stream up to a fresh checkpoint. The
SDKs' managed and environment constructors use a checkpoint freshness of 10
minutes.

Lifecycle-log failure codes: `CHAIN_CONTINUITY`, `DUPLICATE_ISSUANCE`,
`INVALID_EVIDENCE`, `INCOMPLETE_STREAM`, `KEY_CONTINUITY`,
`INVALID_MIGRATION`, and `TERMINAL_STATE`.

## Flags and key age

- `fl=logchk`: before an operation the application treats as high-value or
  irreversible, the relying party should run a fresh non-revocation check
  against the log. In the SDKs, call `VerifyLogEvidence` /
  `verifyNonRevocation` / `verify_log_evidence` on the verified domain. Local
  policy can require this check even when the flag is absent.
- `fl=mtls`: the agent requires mutual TLS. Verifiers that cannot do mTLS
  report "cannot verify". That result does not mean the peer is bad.
- `ka=24h|7d|30d|90d`: the maximum age of the operational key. If the key is
  older, verification fails with `key_age_exceeded`.

## Revocation reasons

The CLI and the registry API accept `owner_request` and `key_compromise`.
`key_compromise` also tells verifiers to distrust everything the key signed.
Protocol-level reasons in the log include `keyCompromise`, `policyViolation`,
`superseded`, and `cessationOfOperation`.

## Checklist for hosting a self-managed identity

For `agent.example` under the accountable entity `example.com`:

1. Keep two different keys: the entity key (for the organization) and the
   operational key (for the agent). Manage each through a key provider: a
   local file, AWS KMS, or your own implementation.
2. Serve the `ek` JWKS over valid HTTPS on `example.com` or a subdomain of it.
3. Serve the `ku` JWKS over valid HTTPS on `agent.example`.
4. Serve the status document at `su=` with caching that is safe for
   revocation.
5. Get a lifecycle-log reference and write the bilateral `ISSUANCE` event.
6. Build and sign the record with an SDK or with `dnsid record publish`.
   Publish one TXT record at `_dnsid.agent.example`.
7. Verify it the way a stranger would: `dnsid record verify --domain
   agent.example`, or `VerifyDomain` with log trust configured.
8. Write down and rehearse the revocation path: status, JWKS tombstone, and
   the log event.

Running your own C2SP log or witness is possible, but those deployments are
still changing. Before you depend on one in production, plan how you will
distribute the policy, which witnesses you trust, and how you will provide
complete-stream evidence.
