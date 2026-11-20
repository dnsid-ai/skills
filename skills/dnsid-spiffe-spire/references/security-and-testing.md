# Security, disclosures, and testing

## Contents

- Security boundaries
- Limitations to disclose, always
- Local trust shortcuts versus production
- Production hardening checklist
- What recipe 16 demonstrates, and what it does not
- Test matrix
- Negative-case recipes
- Representative requests

## Security boundaries

| Layer | Decides | Does not decide |
|---|---|---|
| **DNSid** (the controller) | Which organization signed the binding, whether it is the pinned one, whether the signer is ACTIVE (live status and fresh witnessed log evidence), and so whether the relying SPIRE server holds the peer's bundle | Whether the peer's workloads are trustworthy, or what they may do |
| **SPIFFE** (SPIRE, mTLS) | Whether a workload holds a valid SVID from a trust domain whose bundle the relying side holds | Which organization stands behind a trust domain name |
| **Application authorization** | Whether an authenticated workload may call this API (for example, an allow-list of SPIFFE IDs) | Identity |

DNSid never sees workload traffic. A DNSid-approved peer's workloads still need authorization. Keep
the three layers separate in code, logs, and test assertions.

## Limitations to disclose, always

1. **The binding is a local convention**, not part of DNSid.
2. **The operational key signs it; the entity key does not.** That key alone can bind an attacker's
   CA during bootstrap, or until the signer is revoked. Continuity limits this after the first
   approval.
3. **Trust on first use** of the entity-key pin and the log policy, unless they were confirmed out
   of band.
4. **Established TLS sessions survive withdrawal.** Ending them is connection policy.
5. **A stopped or crashed controller leaves trust installed.** Federated bundles have no expiry.
6. **Detection is poll-based.** Latency is at least the poll interval; each cycle is one full
   verification.
7. **Indeterminate exposure:** blocking verification keeps a revoked peer trusted for up to grace
   + poll + propagation.
8. **Forced withdrawal:** over an unauthenticated binding transport, an on-path party can trigger a
   definitive failure (a replayed revoked statement, a corrupted JWS, an unknown signer) and so
   cause an outage. It cannot cause a trust downgrade once continuity anchors exist.
9. **Single witness and no DNSSEC** in a local setup; the status URL is served by the registry
   (delegated outside `gi`).
10. **Rollback and fork detection against a live log is not demonstrated** by recipe 16.
11. **Only the directions you gated are gated.** In the recipe, the reverse direction is standard
    SPIFFE federation.

## Local trust shortcuts versus production

| Recipe 16 (DNSid Local) | Production |
|---|---|
| Entity-key pin captured at first bootstrap from the key at the signer record's `ek=` URL, accepted only if `gi` is the configured governance ID and the URL is HTTPS on that domain | Confirm the thumbprint with the peer out of band |
| Log policy read once from `DNSID_LOG_POLICY_URL` | Obtain log keys, independent witnesses, and quorum out of band |
| First bundle fetch unauthenticated, accepted only through signed coverage | The same, but confirm the first signed key set with the peer where possible |
| Binding served over plain HTTP inside a Docker network | HTTPS (the signature still protects integrity, not availability) |
| One witness; no DNSSEC; status served by the registry | Real witnesses; a DNSSEC mode chosen and tested; record the delegated status |
| Publisher holds the signer key on disk and SPIRE admin access | Managed key custody (KMS or HSM); read the public bundle endpoint instead of admin access |
| Grace 30 s, freshness 300 s, poll 5 s | Values from the user's risk policy |

## Production hardening checklist

None of these is built in the reference. Recommend them and do not claim them.

- [ ] Out-of-band pins and log trust anchors, with recorded provenance.
- [ ] HTTPS for the binding; managed custody for the signing key.
- [ ] Evaluate an entity-key countersignature on the binding, or a standard profile if DNSid
      defines one.
- [ ] Enforcement liveness: external alerting on the health check, a watchdog that withdraws on a
      lost heartbeat, and single-writer HA.
- [ ] Connection policy that bounds session age, if required.
- [ ] Alert on every HOLD and DENY. Ship the audit log, with statement hashes, where the peer can
      reconcile it.
- [ ] Least privilege: the controller needs only the relying SPIRE admin socket and its state
      directory. Never expose the admin socket on the network. Protect state-changing endpoints.
- [ ] Protect the checkpoint store and journal like the policy and pins (append-only or off-host
      journal where that matters).
- [ ] Hash-pinned dependencies. Re-run the SDK error-mapping tests on every SDK upgrade.

## What recipe 16 demonstrates, and what it does not

**Demonstrated live** (development checkout, 2026-11-19/20; recipe `architecture.md`, "Validation
status"):

- Act 1: internal mTLS works; cross-domain fails at the SPIFFE layer; the controller holds.
- Act 2: ALLOW on the controller's own cycle, with full evidence; the checkpoint persisted; the
  installed key equals the peer's real CA key; a new cross-domain handshake succeeds; the peer's
  allow-list admits the caller.
- Act 3: revocation → DENY WITHDRAWN on its own; new handshakes fail; the established session
  continues; internal mTLS is unaffected.
- A `make stop` / `make bootstrap` resume with the signer, pin, and store preserved.
- 573 offline tests, including restart safety, error mapping, and the store.

**Not demonstrated:** a clean-clone `make verify`; rollback or fork detection against real signed
checkpoints; CA rotation; DNSid key rotation; mutual gating; several peers; Pattern B; hosted
(non-local) DNSid; Kubernetes; HA. In the user's environment, every test is **pending** until it has
run there.

## Test matrix

Test at the level where the behavior lives, and assert **which layer** failed.

| Area | Positive | Negative (expected reason → decision) |
|---|---|---|
| Policy load | Valid file loads | Missing key, empty pin list, signer pattern outside `gi`, unknown key, non-positive window → load error |
| Binding rules | Valid statement; `iss` case and trailing dot normalized | One row per reason in `federation-design.md` |
| Coverage | Served ⊆ signed installs; signed-not-served allowed; JWT keys stripped | Served-not-signed → `BUNDLE_NOT_COVERED`; no X.509 authority → `BUNDLE_INVALID` |
| SDK mapping | — | One row per entry in the table in `verification-and-decisions.md` |
| Verifier | A new manager per call, counted, even after an exception | Registry build fails → I; logged state not ACTIVE → D; `gi` mismatch → D; future witness time → I |
| Decisions | INSTALLED, then UNCHANGED, then UPDATED | D → WITHDRAWN at once; I → HELD, then WITHDRAWN after grace; exclusive boundary; a flapping verifier never ALLOWs |
| Continuity | Anchors persisted after ALLOW and used | A forced withdrawal keeps the anchors; only admin re-bootstrap clears them |
| Checkpoint store | Persists across restarts | Missing, corrupt, changed, or second writer → `CHECKPOINT_STORE_FAILED`; rollback or fork → `LOG_INCONSISTENT` |
| Restart | Same signer, pin, and store reused | Uncertain status never creates a signer; wrong resolver → stop; mismatched registration entry → stop, unchanged |
| Fail closed | — | Cycle raises → HOLD within grace, then withdraw |

End to end (real SPIRE and DNSid; each run needs approval): no binding → HOLD; valid binding →
ALLOW; an SVID that is not on the allow-list → handshake succeeds, then the application refuses;
wrong pin → DENY; publisher stopped → HOLD, then withdraw; revoke a throwaway signer → DENY WITHDRAWN,
new handshakes fail; an established session across revocation keeps working; the controller stopped
→ the health check fails and trust stays.

## Negative-case recipes

- **Another organization signs for the peer's trust domain:** stopped by the pin → DENY
  `GOVERNANCE_NOT_APPROVED`. Test with a mapping unit test, and live with a wrong pin. A second real
  governance domain changes shared DNSid state, so ask first.
- **The approved organization claims an unapproved trust domain:** `TRUST_DOMAIN_NOT_BOUND`.
- **Tampered JWS:** change one payload character → `BINDING_SIGNATURE_INVALID`. Record which SDK
  code you actually saw.
- **Rollback:** accept `seq = N`, then present `N − 1` → HOLD `BINDING_ROLLBACK`.
- **Stale evidence:** in unit tests, a verifier double raising a stale `LOG_ERROR` → HOLD
  `EVIDENCE_STALE`. Never shorten a deployed freshness window to provoke it.

## Representative requests

| Request | Path |
|---|---|
| "Gate federation between our two SPIRE trust domains with DNSid" | New federation, Pattern A, one direction; policy with out-of-band pins; test matrix |
| "We already federate with a partner; add DNSid verification" | Existing federation: baseline, run without writes, approved cutover; warn about competing writers |
| "Make it mutual" or "add three partners" | One publisher, controller, policy, and state per direction and per peer; mark it untested |
| "When the partner is revoked, kill their connections" | Withdrawal stops new handshakes only; add connection policy and test it |
| "Let the peer bundle refresh by itself" | That bypasses the gate (Pattern A). Pattern B is an unvalidated option |
| "Restart reissued our signer" or "bootstrap keeps failing" | The signer-preservation and restart rules in `operations.md`; never replace on uncertainty |
