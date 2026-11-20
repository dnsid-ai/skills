# DNSid verification and the ALLOW / DENY / HOLD decision

## Contents

- The reconcile cycle
- DNSid verification, with SDK names
- Fresh lifecycle state, durable checkpoints
- Log trust policy, freshness, and skew
- Mapping SDK errors to reasons
- The three decisions
- The grace period is a policy choice
- A cycle that raises
- Evidence to record
- Enforcement liveness

Names below were checked against the DNSid Python SDK **0.36.0** (the version recipe 16 pins, from
`dnsid-ai/dnsid-py` tag `v0.36.0`). Recheck them for any other SDK version or language. The
dnsid-sdk skill covers general SDK usage.

## The reconcile cycle

Each cycle runs in this order. Nothing is written to SPIRE until every step passes
(`src/dnsidfed/reconcile.py`):

1. Fetch the binding JWS. Failure → HOLD `BINDING_UNAVAILABLE`.
2. **[DNSid]** Verify the signer's identity, the governance and entity-key pin, and the JWS
   signature, with a fresh SDK manager.
3. **[DNSid]** Verify fresh, witness-cosigned C2SP evidence that the signer is ACTIVE.
4. **Policy:** signer pattern, statement fields, trust domain, endpoint, age, and anti-rollback
   `seq` (the table in `federation-design.md`).
5. Fetch the peer's bundle endpoint, in bootstrap or continuity mode.
6. **Coverage:** every served X.509 authority is in the signed set.
7. **Apply:** `bundle set` (X.509 authorities only), then `federatesWith` on the approved entries.
   Record the decision.

## DNSid verification, with SDK names

From `src/dnsidfed/verifier.py`:

```python
registry = create_c2sp_tlog_verification_registry(C2spTlogVerificationOptions(
    policy_document=log_policy,                 # pinned bytes, never fetched per cycle
    transport_config=transport,
    trusted_checkpoint_store=checkpoint_store,  # ONE durable store shared by every cycle
    checkpoint_freshness_ms=int(v.checkpoint_freshness_s * 1000),
    max_clock_skew_ms=int(v.clock_skew_s * 1000),
))
manager = IdentityManager.for_verification(
    IdentityManagerDependencies(log_registry=registry),
    verification=VerificationConfig(status_check_interval=timedelta(0), trusted_entities=[pin]),
    transport=transport,
)
with manager:
    payload, vd = JoseProfile(resolver=manager).verify_jws(jws)   # record, status, pin, signature
    ev = manager.verify_log_evidence(vd)                          # fresh witnessed lifecycle evidence
    # require ev.logged_state == "ACTIVE"; re-check vd.record.gi against the policy
```

`pin` is `TrustedEntity(governance_id, entity_key_thumbprints)`. A different organization, or a
different entity key under the same governance ID, fails with `COUNTERPARTY_NOT_ACCEPTED`. The
recipe also re-checks `gi` against the policy as defence in depth, and rejects a witness time in
the future beyond the clock skew.

`verify_jws` checks status-service state. Treat the separate `verify_log_evidence` step as required
policy for accepting another organization's CA, not as optional.

## Fresh lifecycle state, durable checkpoints

The recipe handles two kinds of SDK state in opposite ways (`src/dnsidfed/verifier.py` explains
why):

- **Lifecycle state is never reused.** Build a new log registry **and** a new `IdentityManager`
  for every verification, close it after use (`with manager:`), and set
  `status_check_interval=timedelta(0)` so the status service is asked on every call. In SDK
  0.36.0, a C2SP log reader caches each identity's verified history and reuses it until that
  evidence expires or its checkpoint is older than `checkpoint_freshness_ms`
  (`dnsid/c2sp_tlog/reader.py`, `_cached_history`). A long-lived reader's log evidence can
  therefore lag a revocation by up to the freshness window. Each cycle costs one full
  verification; size the poll interval with that in mind.
- **Trusted checkpoints are always reused.** Inject **one** durable `CheckpointStore` into every
  fresh registry. Then a log that rolls back or forks between cycles or restarts is detected, not
  trusted again on first contact. The SDK provides the `CheckpointStore` protocol and an in-memory
  implementation. Recipe 16 adds file persistence (`src/dnsidfed/checkpoints.py`):
  - initialize the store explicitly, once, on first install (`ensure-initialized`); the controller
    never creates it, and a restart loads the same file;
  - a missing, corrupt, foreign, or externally changed store, a second writer, or a failed write
    makes the store unavailable → definitive DENY `CHECKPOINT_STORE_FAILED`. Never substitute an
    empty store;
  - recovery is an explicit, journaled operator action with the controller stopped.

Limits to state: anyone who can write the state directory can delete the store and its journal
(which looks like a fresh install) or restore an older copy while the controller is stopped. The
first checkpoint for each log is trusted on first use. **Recipe 16 has not demonstrated rollback or
fork detection against real signed checkpoints from a live log.** Its offline tests cover the store
and how its errors are handled. Do not describe a deployment as rollback-protected until that is
tested.

## Log trust policy, freshness, and skew

- **The log trust policy is configured, never discovered.** On DNSid Local, read it once at setup
  from `DNSID_LOG_POLICY_URL` and pin it. Never derive it from the record's `lr=` or from anything
  the log provides. In production, get the log keys, witness keys, and quorum out of band, and
  record the policy's SHA-256 with every decision.
- Set `checkpoint_freshness_ms` explicitly. The recipe uses 300 s as a local example, not a
  recommendation.
- Pass the controller's clock skew as `max_clock_skew_ms`.
- A local log with a single witness demonstrates the mechanism. It is not Internet-scale
  transparency. Say so.

## Mapping SDK errors to reasons

Map every outcome to a reason and a class: **D** (definitive, withdraw now) or **I**
(indeterminate, hold within grace). Unknown outcomes are never ALLOW. Use the structured fields
first. Recipe 16 (`_map_sdk_error`) evaluates in this order, and the first match wins:

| SDK signal (0.36.0) | Reason | Class |
|---|---|---|
| `category` in `LOG_ROLLBACK`, `LOG_FORK`, `LOG_INCONSISTENT` (or `C2spCheckpointConsistencyError`) | `LOG_INCONSISTENT` | D |
| `category == CHECKPOINT_STORE_ERROR` (or `C2spCheckpointStoreError`) | `CHECKPOINT_STORE_FAILED` | D |
| `category == TERMINAL_STATE`, or a terminal `agent_state` | `IDENTITY_NOT_ACTIVE` | D |
| `COUNTERPARTY_NOT_ACCEPTED` | `GOVERNANCE_NOT_APPROVED` | D |
| `SIGNATURE_INVALID`, `KEY_NOT_FOUND` | `BINDING_SIGNATURE_INVALID` | D |
| `STATUS_NOT_ACTIVE` | `IDENTITY_NOT_ACTIVE` | D |
| `RECORD_NOT_FOUND` | `IDENTITY_NOT_FOUND` | D |
| `RECORD_INVALID` mentioning JOSE | `BINDING_SIGNATURE_INVALID` | D |
| `TLS_ERROR` with HTTP 410 (a revoked identity's JWKS) | `IDENTITY_NOT_ACTIVE` | D |
| `LOG_ERROR` "too stale" | `EVIDENCE_STALE` | I |
| `LOG_ERROR` mentioning revoked, retired, or terminal | `IDENTITY_NOT_ACTIVE` | D |
| Other `LOG_ERROR`: transient, or not | `EVIDENCE_UNAVAILABLE` (I), or `LOG_VERIFICATION_FAILED` (D) | |
| Transient codes (`DNS_RESOLUTION`, `STATUS_UNAVAILABLE`, `DEADLINE_EXCEEDED`, …) or `transient=True` | `EVIDENCE_UNAVAILABLE` | I |
| Any other `VerificationError` | `VERIFICATION_FAILED` | D |
| `C2spTlogError` (for example while building the registry), or any other exception | `EVIDENCE_UNAVAILABLE` | I |

The message-text rows are fallbacks where 0.36.0 has no structured signal. If the wording changes,
the result is still DENY or HOLD, never ALLOW. Pin this table with one unit test per row, and
re-run it on every SDK upgrade.

## The three decisions

| Decision | When | Effect on the peer's bundle |
|---|---|---|
| **ALLOW** | Every step passed | `INSTALLED`, `UPDATED`, or `UNCHANGED`; `federatesWith` ensured; grace clock reset |
| **DENY** | A definitive reason (`IDENTITY_NOT_ACTIVE`, `IDENTITY_NOT_FOUND`, `GOVERNANCE_NOT_APPROVED`, `BINDING_SIGNATURE_INVALID`, `SIGNER_NOT_ALLOWED`, `TRUST_DOMAIN_NOT_BOUND`, `BINDING_ISSUER_MISMATCH`, `BUNDLE_ENDPOINT_MISMATCH`, `LOG_VERIFICATION_FAILED`, `VERIFICATION_FAILED`, `LOG_INCONSISTENT`, `CHECKPOINT_STORE_FAILED`) | **Withdrawn immediately** (`WITHDRAWN`, or `NONE` if nothing was installed) |
| **HOLD** | Any other reason, within the grace period | Kept as is (`HELD`) or still absent (`NONE`). **Never adds or changes material** |
| **DENY** (controller policy) | An indeterminate reason after the grace period | Withdrawn |

Keep the **DNSid result** (`VERIFIED`, `NOT_VERIFIED`, `INDETERMINATE`) as a separate field from
the controller's decision, and record which layer failed. A policy check that fails after DNSid
succeeded is not a DNSid failure.

Rules (all enforced by the recipe):

- Persist the grace clock with the anti-rollback `seq` and the continuity anchors, so a restart
  does not reset it.
- An installed bundle with no recorded verification (state lost) is withdrawn on the first
  indeterminate result, not held.
- The grace boundary is exclusive: withdraw when the time since the last full verification is
  greater than the grace period.
- After any withdrawal, re-approval needs a full verification. A flapping verifier can never turn
  a HOLD into ALLOW.

## The grace period is a policy choice

`unavailable_grace_s` is how long installed trust may stay without a fully verified cycle. The
recipe's 30 s is a local demonstration value. Set it with the user, weighing:

- **Exposure:** anyone who can block verification keeps a revoked peer trusted for up to grace +
  poll interval + SPIRE propagation.
- **Outage:** a DNSid or network disruption longer than the grace period withdraws federation from
  a peer in good standing.

Zero is valid. Alert on every HOLD. Treat changes to the grace period, freshness, or poll interval
as policy changes that need approval. Never shorten or lengthen them to make a test pass.

## A cycle that raises

Wrap the whole cycle (`src/dnsidfed/controller.py`). Within the grace period: HOLD
`CONTROLLER_ERROR`. After it: try to withdraw. If withdrawal also fails, record both errors and
clear the grace clock.

## Evidence to record

For every decision: the signer, `gi`, the record-signing entity-key thumbprint, the live status
(and whether the status URL is delegated outside `gi`), the logged state, the log reference, the
checkpoint origin, size, and root, the witness time and evidence age, the DNSSEC state (DNSid Local
reports `UNKNOWN`), the log policy's SHA-256, the statement hash and `seq`, and the installed SPKI
set. Write it to an append-only audit log. Never describe an ALLOW as DNSSEC-validated unless it
was.

## Enforcement liveness

A running process is not the same as active enforcement. The recipe's `GET /healthz` returns 503
when no cycle has completed for max(60 s, 6 × poll interval). State-changing endpoints
(`/reconcile`, `/rebootstrap`) require an admin token. Monitor the health check from outside.
