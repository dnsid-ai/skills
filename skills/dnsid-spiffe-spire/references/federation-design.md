# Designing DNSid-gated SPIFFE federation

## Contents

- Roles
- Pattern A: the controller is the only writer (the reference implementation)
- Pattern B: gate SPIRE's own federation relationship (not validated)
- New federation or existing federation
- One-way and mutual federation
- Several peers
- The federation binding (a local convention)
- Bootstrap and continuity
- Coverage, not equality
- Federated entries

The reference implementation is cookbook recipe 16 (`recipes/16-spiffe-federation/`, in review as
https://github.com/dnsid-ai/dnsid-cookbook/pull/165). It gates **one** direction (Acme accepts
Rackloria) with Pattern A. Anything this file describes beyond that is design guidance that the
recipe does not demonstrate. Say so when you use it.

## Roles

| Role | Runs on | Does |
|---|---|---|
| **Publisher** | Peer side (the organization being trusted) | Reads the peer's current X.509 CA authorities, signs a binding statement with the peer's DNSid signer identity, and serves the compact JWS |
| **Controller** | Relying side | Every cycle: fetches the binding, verifies it and the signer with DNSid, fetches the peer's bundle endpoint, and installs, updates, or withdraws the peer's bundle in the relying SPIRE server |
| **Relying SPIRE server** | Relying side | Holds the peer's bundle and delivers it to workloads whose registration entries list the peer in `federatesWith` |
| **Peer bundle endpoint** | Peer side | SPIRE's standard bundle endpoint (`federation.bundle_endpoint` in the peer's `server.conf`) |

The signer is a DNSid identity **under** the peer's governance domain (in the recipe,
`spire-fed-<time>-<hex>.rackloria.test` under `rackloria.test`). It is not the organization's own
identity, so it can be revoked without touching the organization.

## Pattern A: the controller is the only writer (the reference implementation)

The relying `server.conf` has **no** `federates_with` block for the peer. If it had one, SPIRE
would fetch and refresh the peer's bundle by itself and bypass the gate. Recipe 16 states this in
`spire/acme/server.conf`. The controller writes through the SPIRE server CLI on the local admin
socket (`src/dnsidfed/spire.py`):

| Operation | Command |
|---|---|
| Read the installed peer bundle | `spire-server bundle list -id spiffe://<td> -format spiffe` |
| Install or update | `spire-server bundle set -format spiffe -id spiffe://<td>` (bundle JSON on stdin; X.509 authorities only) |
| Let an approved entry federate | `spire-server entry update -entryID … -federatesWith spiffe://<td>`. `entry update` replaces fields, so pass every existing selector and federation. Run it after `bundle set`. |
| Withdraw (enforcement) | `spire-server bundle delete -id spiffe://<td> -mode dissociate`. This also removes the trust domain from every entry's `federatesWith`. |
| Withdraw on orderly shutdown | `spire-server bundle delete -id spiffe://<td> -mode restrict`. It refuses while any other entry still federates with the trust domain, so relationships the controller does not manage are never cut. |
| Peer: read its own bundle | `spire-server bundle show -format spiffe` |

Consequences:

- **SPIRE never refreshes a bundle it does not federate with**, so the controller must be a
  **reconcile loop**, not a one-shot install. A one-shot install would miss the peer's CA changes
  and could keep a withdrawn authority trusted.
- The controller is the single point that keeps trust current. If it stops, installed trust stays
  as it is (see `operations.md`).

## Pattern B: gate SPIRE's own federation relationship (not validated)

The controller would create or delete SPIRE's federation relationship for the peer (with the
`https_spiffe` profile), and SPIRE would refresh the bundle. **Nothing in the reference implements
or tests this.** Present it only as an option to evaluate:

- confirm the commands and flags with `spire-server federation --help` on the user's version;
- test whether deleting the relationship removes the bundle and stops new handshakes, and how fast;
- SPIRE does not check DNSid coverage on its own refresh, so decide how the signed key set still
  constrains what gets installed.

## New federation or existing federation

**New federation.** Use Pattern A from the start. The relying side never gets a `federates_with`
block for the peer.

**Adding DNSid to an existing federation.** If the relying side already federates with the peer
(a `federates_with` block or a federation relationship), SPIRE is already a writer. A controller
next to it is a **competing writer**: SPIRE may restore what the controller withdrew. The reference
does not test this. Plan the cutover with the user:

1. Record a baseline, read-only: the installed bundle's SPKI hashes, the relationship, and the
   entries with `federatesWith`.
2. Run the controller without SPIRE writes first and compare its decisions with what is installed.
   Recipe 16 has **no** observe-only mode, so build one and test that it never writes.
3. Remove the static relationship (a `server.conf` change and a server restart, so get approval for
   it), then enable enforcement. Whether removing `federates_with` keeps or drops the installed
   bundle is not tested in the reference. Verify it outside production. Do not promise zero
   downtime.
4. Expect the first enforcing approval to be a **bootstrap** (below). If the user wants the existing
   bundle to seed continuity instead, say plainly that nothing DNSid-verified it.

## One-way and mutual federation

Each gated direction is independent and needs its **own** publisher on the trusted side and its
**own** controller and policy on the relying side.

- **One-way** (the reference): Acme accepts Rackloria only through DNSid. In the recipe, Rackloria
  accepts Acme through standard SPIFFE federation, which is deliberately not gated.
- **Mutual:** run the same pattern in both directions: a publisher and controller on each side,
  each with its own signer identity, policy, pins, and state. Neither side's controller may write
  the other side's trust. The reference gates only one direction, so mutual gating is untested;
  test each direction on its own (approval, revocation, withdrawal) before relying on it.

## Several peers

Use one policy per gated trust domain, with separate state for each (continuity anchors,
anti-rollback `seq`, grace clock, managed key set). At load time, reject two policies that name the
same trust domain or map it to different governance IDs. The recipe's policy loader
(`src/dnsidfed/policy.py`) handles one `[federation]` table, so multiple peers need either one
controller per peer or a loader you extend and test.

## The federation binding (a local convention)

> **Not part of DNSid.** The DNSid draft defines no binding for external key material such as
> SPIFFE trust domains or CA keys. DNSid verifies **who signed** the statement and **that the
> signer is still active**. What the statement means is relying-side policy. Never call it a DNSid
> standard or profile.

A compact JWS made with the SDK's JOSE profile (`JoseProfile.from_identity_manager(manager).create_jws(payload)`)
and signed by the signer identity's operational key. The payload (`src/dnsidfed/publisher.py`):

```json
{
  "typ": "dnsid-spiffe-federation+v0",
  "iss": "spire-fed-20261101000000-ab12.rackloria.test",
  "trust_domain": "rackloria.test",
  "bundle_endpoint": {"url": "https://rackloria-server:8443",
                      "spiffe_id": "spiffe://rackloria.test/spire/server"},
  "x509_authorities_spki_sha256": ["<base64url SHA-256 of each CA's SubjectPublicKeyInfo>"],
  "seq": 1795142956, "iat": 1795142956, "exp": 1795143856
}
```

- `iss` must equal the identity the **SDK verified** as the signer. Never trust it on its own.
- `seq` is a monotonic anti-rollback counter (the recipe uses the signing time).
- The recipe's statements live 900 s. The publisher checks periodically and re-signs when expiry
  is less than 300 s away, or when its own bundle's X.509 authority set has changed.
- **A longer lifetime widens the replay window.** A statement stays acceptable until it expires
  or exceeds the policy's maximum age, as long as its signer is still ACTIVE. Within one
  controller, the persisted `seq` holds an older statement (`BINDING_ROLLBACK`). On first
  contact, after an admin re-bootstrap, or after controller state is lost, there is no `seq` to
  compare against, so an older statement can be replayed for its whole remaining lifetime, for
  example one that still covers a CA the peer has since retired. Treat lifetime and maximum-age
  changes as policy changes, and keep them short.
- If the format changes, change `typ`.

Relying-side checks after DNSid verification (`src/dnsidfed/binding.py`). **D** withdraws
immediately; **I** holds within the grace period and then withdraws:

| Check | Reason | Class |
|---|---|---|
| JSON object, `typ` matches, required fields typed, `exp > iat`, non-empty SPKI list | `BINDING_MALFORMED` | I |
| Verified signer matches the policy's signer pattern under the approved governance ID | `SIGNER_NOT_ALLOWED` | D |
| `iss` equals the verified signer | `BINDING_ISSUER_MISMATCH` | D |
| `trust_domain` equals the policy's (one governance ID per trust domain) | `TRUST_DOMAIN_NOT_BOUND` | D |
| Endpoint URL and SPIFFE ID equal the policy's | `BUNDLE_ENDPOINT_MISMATCH` | D |
| `iat` not in the future beyond skew | `BINDING_NOT_YET_VALID` | I |
| Not expired and not older than the policy's maximum age | `BINDING_EXPIRED` | I |
| `seq` not below the last accepted (persisted) value | `BINDING_ROLLBACK` | I |

Known weakness: the operational key signs and the entity key does not. Whoever holds the
operational key can bind any CA until the identity is revoked. Continuity (below) narrows this
after the first approval; it does not remove it.

## Bootstrap and continuity

- **Bootstrap** (no approved key set yet, or after an explicit admin re-bootstrap): the controller
  fetches the peer's bundle endpoint over TLS **without** certificate verification. The material is
  accepted only if every served X.509 authority is in the DNSid-signed set.
- **Continuity** (after the first approval): the endpoint must present a certificate that chains
  to the **last approved authority set, persisted in controller state**, with the URI SAN equal to
  the policy's endpoint SPIFFE ID (`src/dnsidfed/bundle.py`). Otherwise the result is
  `CONTINUITY_FAILED` (HOLD). It never falls back to bootstrap on its own.
- Take the anchors from controller state, never from what SPIRE currently holds. Otherwise any
  forced withdrawal would push the controller back into an unauthenticated bootstrap.
- Only an authenticated admin action (`POST /rebootstrap` in the recipe) clears the anchors. It
  also withdraws the installed bundle.

## Coverage, not equality

Install an authority only if the peer **serves** it **and** the binding **signs** it (served ⊆
signed). Signed-but-not-yet-served authorities are allowed, so a rotation can be announced ahead.
A served authority that is not signed → `BUNDLE_NOT_COVERED` (I), and nothing new is installed.
Never install JWT authorities: the binding does not cover them.

## Federated entries

Grant `federatesWith` only to the relying-side entries the policy lists (in the recipe,
`spiffe://acme.test/purchasing`). Other workloads never receive the peer's bundle, so they cannot
authenticate the peer's workloads.
