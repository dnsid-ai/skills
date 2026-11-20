# Lifecycle and operations

## Contents

- Revocation and withdrawal
- Established TLS sessions
- Signer identities: preserve, never replace automatically
- Restarting safely
- Orderly shutdown and crashes
- The peer's CA rotation (not validated in recipe 16)
- DNSid key rotation (not exercised)
- Bootstrap and re-bootstrap
- Recovering the checkpoint store
- Configuration changes

## Revocation and withdrawal

When the signer identity is revoked, the next cycle's fresh verification fails definitively and the
controller withdraws the bundle. Detection is **poll-based**: latency is at least the poll interval,
plus one verification, plus SPIRE propagating the change to workloads.

**Any one lifecycle signal is enough to DENY.** In recipe 16's live run, the first signal was the
registry's live status (`STATUS_NOT_ACTIVE`), and later cycles failed on the signer's JWKS answering
HTTP 410. The local C2SP log recorded the revocation about a minute later. Withdrawal did not wait
for the log, and the checkpoint store did not advance on revocation, because the cycle stopped before
the log was consulted. Log evidence is still required for every ALLOW.

Measured in that run (local, macOS, poll interval 5 s). These are **measurements, not bounds**:

| From the revoke call | Elapsed |
|---|---|
| Registry reports REVOKED | 0.19 s |
| Controller decides DENY / WITHDRAWN `IDENTITY_NOT_ACTIVE` | 3.9 s |
| Peer bundle gone from the relying SPIRE server | 4.4 s |
| First new cross-domain handshake fails | 8.3 s |

Measure these in the user's environment. Revoke only the federation signer, never the
organization's own identity. **Revocation is permanent**: get explicit approval each time.

## Established TLS sessions

**Withdrawing the bundle does not end established TLS sessions.** It only stops new handshakes
from validating the peer. In recipe 16, a connection opened before revocation stayed established,
kept getting HTTP 200, and the peer's application kept authorizing each request against the
identity presented at handshake. Once that connection closed, reconnecting failed at the SPIFFE
layer.

If sessions must end, that is **connection policy**, added and tested separately: a maximum
connection age on servers and proxies, or applications that watch Workload API bundle updates and
close connections to a trust domain that has left the bundle set. Never describe withdrawal as
disconnecting the peer.

## Signer identities: preserve, never replace automatically

- Reuse an existing signer only after the registry **positively** reports it ACTIVE.
- A timeout, connection error, HTTP 5xx, or unreadable status is **uncertain**, not absent. Stop
  and report. Never issue a replacement because of it.
- A revoked, retired, or missing signer stops the deployment with an explanation. A revoked signer
  is never reused.
- Issue a new signer only on an explicitly authorized first enrollment, with no earlier signer,
  pin, checkpoint store, or registry signer present.
- Never re-pin silently. If the pinned entity key is no longer served, stop; do not adopt the new
  key.

Recipe 16 implements these in `scripts/identity.py` (`ensure-active --first-enrollment`, `pin`,
`pin --check`). Consequence: after its Act 3 revokes the signer, the lifecycle can be repeated only
in a new isolated environment. There is no rotation command yet; designing one is a separate,
reviewed change.

## Restarting safely

A restart must resume the same trust, never start a new trust history:

- **Same signer, same pin, same checkpoint store.** Each restart check fails closed with a named
  reason. The recipe's reasons are `RESOLVER`, `REGISTRY UNCERTAIN`, `SIGNER UNUSABLE`, `MALFORMED
  RECORD`, `GOVERNANCE MISMATCH`, `ENTITY-KEY MISMATCH`, `CHECKPOINT STORE`, `SPIRE REGISTRATION`,
  and `CONTROLLER CONTAINER`.
- **Read DNS only from the resolver you have verified.** On DNSid Local, establish the resolver
  from the instance's own configuration and confirm the running instance publishes it. Do not
  trust an environment value alone. A known compatibility issue: after a restart, `dnsid local env`
  (CLI `2026.10.29-537b773`) can report the default DNS port although the instance serves another,
  and the default port may belong to a different local instance. Recipe 16 compares the CLI's value
  and reports it, but never uses it.
- **Registration entries:** create one only when its absence is confirmed. Accept an existing one
  only if its SPIFFE ID, parent, selectors, federation relationships, and other constraints match
  exactly. Never overwrite or delete an unexpected entry to make a start succeed. Capture the whole
  lookup output before matching it: `spire-server … | grep -q` under `pipefail` can report a present
  entry as absent.
- **Containers on a recreated network:** `dnsid local down`/`up` recreates the registry's Docker
  network under the same name with a new ID. A stopped controller container then cannot start.
  Recreate only that container, and only when ownership is confirmed and its state is
  bind-mounted. Never restart a running, healthy controller.

## Orderly shutdown and crashes

- **Orderly stop** (SIGTERM): finish the current cycle, then withdraw only trust the controller can
  prove it installed (a persisted record of the exact authority set). Delete in `restrict` mode,
  and stop federating only the policy's own entries. If ownership cannot be established, change
  nothing and say so (recipe 16's `architecture.md`, "Operational limits").
- **Crash, SIGKILL, or host failure:** nothing runs, so **installed trust stays**. SPIRE federated
  bundles have no expiry. On restart, the first cycle re-verifies. Until then the exposure is the
  downtime plus one cycle. Monitor the health check from outside, and consider a watchdog or HA;
  none of these is built in the reference.

## The peer's CA rotation (not validated in recipe 16)

The publisher signs the X.509 authorities in the peer's bundle and re-signs when that set changes.
Coverage (served ⊆ signed) lets an announced, signed-but-not-yet-served authority pass. A rotation
(`spire-server localauthority x509 prepare`, `activate`, then retiring the old authority) should
therefore produce UPDATED decisions, possibly with a short HOLD `BUNDLE_NOT_COVERED` if an authority
is served before it is signed. **Recipe 16 does not exercise this.** Test it before relying on it,
and check whether the user's SPIRE version includes prepared authorities in `bundle show`.

## DNSid key rotation (not exercised)

- **Entity-key rotation:** the pin no longer matches → `GOVERNANCE_NOT_APPROVED`, which withdraws.
  `TrustedEntity` accepts several thumbprints, so confirm the new thumbprint out of band and add it
  **before** the peer rotates, then remove the old one. Each policy change needs approval.
- **Operational-key rotation:** a statement signed just before rotation may fail until the
  publisher re-signs. Test the outcome (HOLD or DENY) before relying on it.

## Bootstrap and re-bootstrap

The first approval is the most exposed moment: the bundle endpoint is fetched unauthenticated, and
a stolen operational key alone could bind an attacker's CA. Where possible, confirm the first signed
key set with the peer out of band. Re-bootstrap is an explicit, authenticated admin action that
withdraws the bundle and clears the anchors. Use it only when the peer has legitimately lost
continuity.

## Recovering the checkpoint store

`CHECKPOINT_STORE_FAILED` means the controller is denying on purpose. Find out why the store is
missing or changed. Then either restore a known-good copy, or accept a new baseline explicitly with
a recorded reason while the controller is stopped (recipe 16: `make checkpoints-status`,
`make checkpoints-reset REASON="…"`). A reset keeps the old file and journals the reason. Never
delete the store to make the controller start.

## Configuration changes

The policy is loaded at startup. Make sure a change actually reaches the running controller, and
re-run the positive and negative tests after every policy change.
