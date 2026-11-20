---
name: dnsid-spiffe-spire
description: >-
  DNSid adds a verification layer to SPIFFE/SPIRE federation: which
  accountable organization stands behind a federation identity, and whether
  that identity remains valid over time. This skill guides the implementation
  of a controller that verifies DNSid identity and signed federation evidence
  before establishing cross-domain trust, keeps checking that evidence, and
  withdraws the peer's federation bundle when verification definitively fails.
  DNSid verifies identity and supporting trust evidence; SPIFFE authenticates
  workloads across trust domains with mutual TLS; applications retain control
  over authorization. Use this skill whenever the user wants to gate SPIFFE or
  SPIRE federation on DNSid, control which organizations may federate with
  their SPIRE deployment, add DNSid to an existing federation, or withdraw a
  partner's trust domain on revocation. Also use it when they ask how DNSid
  relates to SPIFFE, SPIRE, workload mTLS, or authorization, even if they do
  not say "federation". Use dnsid-sdk for SDK code and dnsid-cli for DNSid
  Local. Reference implementation: cookbook Recipe 16, in review as PR #165.
---

# DNSid-gated SPIFFE federation

SPIFFE/SPIRE provides workload identities and mutual TLS authentication across trust domains.
DNSid adds a separate layer of verification: **which accountable organization stands behind a
federation identity, and whether that identity remains valid over time.**

This skill guides the implementation of a controller that verifies DNSid identity and signed
federation evidence before establishing cross-domain trust. It continues checking that evidence
and withdraws the peer's federation bundle when verification definitively fails.

**DNSid verifies identity and supporting trust evidence. SPIFFE authenticates workloads.
Applications retain control over authorization.**

The reference implementation is Recipe 16 in the DNSid cookbook, currently under review in PR #165.

## What each layer decides

| Layer | Question | Mechanism |
|---|---|---|
| **DNSid** | Does the relying SPIRE server hold the peer's bundle at all? | The controller verifies the signed binding, the signer's identity and status, the governance and entity-key pin, and fresh log evidence |
| **SPIFFE** | Is this workload who it claims to be? | SPIRE X.509-SVIDs, verified in each mTLS handshake against the bundles the workload holds |
| **Authorization** | May this workload call this API? | The application's own policy, for example an allow-list of SPIFFE IDs |

Keep the three separate in code, logs, and test assertions. `references/security-and-testing.md`
explains the boundaries.

## Choose the path

| The user wants to… | Do this | Reference |
|---|---|---|
| Federate with a new partner, gated by DNSid | Pattern A: a publisher on the peer side, a controller as the **only writer** of the peer's bundle on the relying side | Recipe 16 (one direction) |
| Add DNSid to a federation that already exists | Baseline first, run the controller without writes, then an approved cutover. SPIRE and the controller must never both write the bundle | `references/federation-design.md`. Not in the recipe |
| Gate both directions (mutual) | The same pattern twice: a publisher and controller on each side, with independent policy, pins, and state | Design guidance. Untested |
| Federate with several partners | One policy and separate state per trust domain | Design guidance. The recipe loads one policy |
| Let SPIRE refresh the peer bundle itself | Pattern B (gate SPIRE's federation relationship). Present it as an option to evaluate | Not validated |
| Only mTLS inside one trust domain | DNSid is not needed. Use SPIRE alone | — |

## Reference implementation

**Cookbook recipe 16, DNSid-verified SPIFFE/SPIRE federation, is in review:**
https://github.com/dnsid-ai/dnsid-cookbook/pull/165 (`recipes/16-spiffe-federation/` once merged).
Two SPIRE trust domains (`acme.test` accepts `rackloria.test`) run in Docker Compose against an
isolated DNSid Local. It shows the three acts live: no trust; DNSid-verified ALLOW; revocation and
withdrawal. Point the user at its files instead of copying them:

| Step | File in the recipe |
|---|---|
| Policy (the relying side's decision record) | `config/federation-policy.template.toml`, `src/dnsidfed/policy.py` |
| DNSid verification and SDK error mapping | `src/dnsidfed/verifier.py` |
| One reconcile cycle and ALLOW/DENY/HOLD | `src/dnsidfed/reconcile.py` |
| Binding format and checks | `src/dnsidfed/publisher.py`, `src/dnsidfed/binding.py` |
| Bootstrap and continuity fetch | `src/dnsidfed/bundle.py` |
| Durable trusted-checkpoint store | `src/dnsidfed/checkpoints.py` |
| Signer, pin, and resolver handling on DNSid Local | `scripts/identity.py`, `scripts/bootstrap.sh` |
| The three acts as assertions | `verify/verify.sh` |

Things to tell the user before they run it:

- It needs host port 443 and builds four images. Its `make clean` refuses to delete checkpoint
  history without `CONFIRM=delete-checkpoint-history`, and `make stop` keeps all state.
- Act 3 permanently revokes the signer, and the signer is never replaced automatically, so the full
  lifecycle runs once per environment. A fresh clone repeats it.
- Until the PR merges, treat the recipe as under review, and quote only behavior its README or
  `architecture.md` states.

## Rules

Follow these even if the user asks for a shortcut. If a request conflicts with one, explain the
risk and stop for an explicit decision.

1. **Pin the peer explicitly.** Map each gated trust domain to exactly one governance ID and at
   least one entity-key thumbprint (`TrustedEntity`), set by the relying party. Never derive the
   mapping from the binding or the record. Captured pins are trust on first use; in production,
   confirm them with the peer out of band.
2. **Configure log trust. Never discover it.** The C2SP log policy comes from configuration
   (`DNSID_LOG_POLICY_URL` on DNSid Local, out-of-band anchors in production). Never take it from
   the record's `lr=` or from anything the log serves.
3. **Fresh lifecycle evidence every cycle, durable checkpoints across cycles.** Build a new log
   registry and `IdentityManager` for each verification, with `status_check_interval=0`, and
   require `verify_log_evidence(...).logged_state == "ACTIVE"`. Share **one** durable checkpoint
   store, so rollback and fork are detected (definitive DENY). A lost or changed store fails closed
   and is never re-created silently.
4. **Fail closed, and keep the two failure classes apart.** Definitive failures (revoked, wrong
   organization or key, bad signature, log inconsistency) DENY and withdraw immediately.
   Indeterminate ones HOLD: add nothing, and withdraw once the grace period passes without a full
   verification. No error path, exception, or unknown state leads to ALLOW.
5. **Install only signed, served CA keys.** Every X.509 authority the peer serves must be in the
   signed set; never install JWT authorities. After the first approval, fetch the bundle only over
   a channel authenticated by the last approved key set, persisted in controller state. Only an
   explicit admin re-bootstrap goes back to the unauthenticated path.
6. **The controller is the only writer of a gated peer's bundle.** No `federates_with` for that
   peer on the relying SPIRE server: SPIRE would refresh around the gate.
7. **Withdrawal stops new handshakes only.** Established TLS sessions continue until the
   application closes them. Never claim that revocation disconnects the peer; offer connection
   policy if the user needs that.
8. **Preserve signer identities.** Reuse a signer only on a positive ACTIVE status. Treat timeouts
   and unreadable answers as uncertain, never as absent. Never reissue, replace, or re-pin
   automatically. Revocation is permanent and needs explicit approval each time.
9. **Keep the model out of the trust path.** Pins, verification, signing, and bundle writes are
   code and configuration. A model may summarize a decision, never make one.
10. **Never weaken verification to pass a test, and never overclaim.** Do not stretch freshness,
    grace, or statement lifetime (a longer lifetime also widens the window in which an old
    statement can be replayed), skip the log check, or reuse a verifier. Report what actually
    ran. State unvalidated behavior as unvalidated: live rollback detection, CA rotation, mutual
    gating, several peers, Pattern B.
11. **Protect secrets.** Never print, log, or commit DNSid private keys, registry API keys, SPIRE
    join tokens, admin tokens, or controller state that holds them. Give the publisher an
    allowlisted environment without the registry API key.

## Workflow

1. **Classify.** New or existing federation? Which directions? How many peers? Which relying
   workloads may federate? What availability policy (poll interval, freshness, grace, alerting)?
   Read `references/federation-design.md`.
2. **Write the policy** as the relying organization's decision record: trust domain, governance ID,
   entity-key pins, signer pattern under that governance ID, binding and bundle endpoints, the
   federated entries, and verification settings. Reject bad policy at load time.
3. **Peer side: publish the binding.** Sign the statement with a dedicated signer identity under
   the peer's governance domain, using
   `JoseProfile.from_identity_manager(manager).create_jws(payload)`. Re-sign before expiry and
   when the CA set changes. The binding format is a local convention, not part of DNSid.
4. **Relying side: the reconcile loop.** Fetch, verify with DNSid, check policy, fetch the bundle
   (bootstrap or continuity), check coverage, then apply. Read
   `references/verification-and-decisions.md` before writing the verifier.
5. **Decide, apply, withdraw** with ALLOW, DENY, and HOLD, a persisted grace clock, an audit
   record for every cycle, and a health check that fails when cycles stop.
6. **Operate.** Revocation, restarts, shutdown and crash behavior, rotation, and recovery are in
   `references/operations.md`.
7. **Test** with the matrix in `references/security-and-testing.md`. Unit tests first; live tests
   only with approval and throwaway signer identities.
8. **Report** with evidence from tests that actually ran, plus the disclosures in
   `references/security-and-testing.md`.

## What not to build

- A controller next to a static `federates_with` for the same peer: two writers, and the gate is
  bypassed.
- A one-shot installer instead of a reconcile loop: it misses the peer's CA changes and never
  withdraws.
- Federation that trusts "any ACTIVE DNSid identity": without pins, any organization could bind the
  trust domain.
- A verifier that keeps one `IdentityManager` alive across cycles, or a checkpoint store that is
  re-created on startup.
- A HOLD that ever adds or changes material, or that turns into ALLOW without a full verification.
- An unauthenticated bundle refresh after the first approval.
- Withdrawal described as disconnecting the peer, or DNSid described as replacing SPIRE or
  authorization.

## Sources

- Cookbook recipe 16 (in review): https://github.com/dnsid-ai/dnsid-cookbook/pull/165
- DNSid documentation: https://docs.dnsid.ai
- Python SDK (the recipe pins `v0.36.0`): https://github.com/dnsid-ai/dnsid-py
- The dnsid skill (protocol and lifecycle), dnsid-sdk (verification code), and dnsid-cli (DNSid
  Local).

When this skill and the live recipe, docs, or installed tools disagree, the recipe, docs, and
tools win. Recheck SDK names against the version the user pins.
