# Log trust, non-revocation checks, and keys

Read this file when verification has to work outside DNSid Local, before a
high-value operation that needs a `logchk` check, or when you work with key
storage, rotation, or KMS. Snippets are from the docs at
https://docs.dnsid.ai/sdk-transparency-log and
https://docs.dnsid.ai/sdk-key-providers. Where code below differs from the
API reference, trust the reference.

## Contents

- Choosing log trust
- Durability and freshness
- Enforcing `logchk` before high-value operations
- Reading verified history
- Key providers
- Rotation

## Choosing log trust

Every `VerifyDomain` verifies the peer's lifecycle log, so every verifier
needs a log registry that it trusts. There are three choices. A deployment
picks exactly one.

| Choice | When | Env / file | Code |
|---|---|---|---|
| DNSid-managed | Peers on `https://log.dnsid.ai` or `https://log.dev.dnsid.ai` (scope `public`) | Deployment file `{"logTrust":{"managed":true}}`. There is no environment variable for it. | Go `c2sptlog.NewDnsidManagedVerificationRegistry`. TS `createDnsidManagedVerificationRegistry` (`@dnsid-ai/log-c2sp-tlog`). Py `dnsid.c2sp_tlog.create_dnsid_managed_verification_registry` |
| Trust profile | A deployment that publishes a C2SP trust profile (one exact scope and prefix, with policy and bundle-signer keys) | `DNSID_LOG_TRUST_PROFILE_FILE`, or `{"logTrust":{"profile":{…}}}` | The generic C2SP factories |
| Policy document | DNSid Local, or a deployment that distributes a `tlog-policy` | `DNSID_LOG_POLICY_FILE` or `DNSID_LOG_POLICY_URL`, or `{"logTrust":{"policyUrl":"…"}}` | The generic C2SP factories |

Rules:

- A loaded `logTrust` must contain exactly one of `managed`, `profile`,
  `policyDocument`, or `policyUrl`. A `logRegistry` passed in explicitly
  overrides loaded trust.
- The managed factory accepts only the canonical `public` references to the
  two DNSid logs. Any other scope or prefix fails closed, which includes the
  `testnet` scope used by DNSid Local. This is how production verifiers keep
  local identities out.
- Obtain the policy location through a channel you trust: your own config,
  a secrets store, or a pinned file. Never derive it from `lr=`, never append
  `/dnsid-policy` to a log prefix, and never use a policy that a log or a
  mirror advertises about itself.
- For private or test deployments, give the generic factory the same DNS, CA,
  and private-host transport settings as the identity manager.

## Durability and freshness

- The default store of trusted checkpoints lasts only as long as the
  registry object. **Reuse one registry and one manager** across
  verifications. If rollback protection must survive restarts, supply a
  durable checkpoint store. A new, empty store accepts the first checkpoint
  it sees for each origin.
- The managed, environment, and deployment-file constructors apply a
  **10-minute** checkpoint freshness to the non-revocation check. A generic
  registry needs `CheckpointMaxAge` (Go), `checkpointMaxAge` (TS), or
  `checkpoint_freshness_ms` (Py) to be set. Without it, non-revocation checks
  fail closed.
- Managed trust prefers signed per-domain stream bundles and falls back to a
  bounded full-log scan. Full scans are expensive on large logs. Use the
  generic factories' `requireStreamBundle`-style options when you need to
  force the bundle path.

## Enforcing `logchk` before high-value operations

Ordinary verification proves the issuance binding and the key chain. Before
an irreversible operation (payment, deletion, a privileged action), also
prove that **nothing was revoked** up to a fresh checkpoint. Do this when the
record carries `fl=logchk`, *or* when your own policy says the operation
needs it. Run the check immediately before the operation.

```go
vd, err := verifier.VerifyDomain(ctx, domain)
if err != nil { return err }
if highValue && (vd.RequiresLogCheck() || localPolicyRequiresLogCheck) {
    if _, err := verifier.VerifyLogEvidence(ctx, vd, time.Time{}); err != nil { return err } // zero time = now
}
```

```ts
const vd = await idm.verifyDomain(domain);
if (highValue && (vd.requiresLogCheck() || localPolicyRequiresLogCheck)) {
  const evidence = await vd.verifyNonRevocation(); // throws VerificationError on incomplete/stale/revoked
}
```

```python
vd = manager.verify_domain(domain)
if high_value and (vd.requires_log_check() or local_policy_requires_log_check):
    evidence = manager.verify_log_evidence(vd)  # raises VerificationError
```

Log evidence does **not** refresh `su=` status. If the operation also needs
fresh status, verify the domain again first.

## Reading verified history

For audits ("which key, and which accountable entity, applied at time T?"),
load the events that passed proof checks and take a snapshot:

- Go: `log, _ := verifier.LoadDomainLog(ctx, vd); snap, _ := log.SnapshotAt(t)`, then use `snap.HistoricalState` and `snap.ActiveKeyThumbprint`
- TS: `(await idm.loadDomainLog(vd)).snapshotAt(date).historicalState`
- Py: `manager.load_domain_log(vd).snapshot_at(dt).historical_state`

A snapshot shows logged history. It never tells you the current status. All
three SDKs can also verify signed `dnsid-c2sp-stream-bundle@v1` bundles
offline (`VerifyStreamBundle`, `verifyC2spStreamBundle`,
`verify_c2sp_stream_bundle`).

## Key providers

Every signing operation goes through a `KeyProvider`. Each provider tracks
keys in three states: **pending** (generated but not published, and usable
only for proof of possession during rotation), **active** (the one signing
key), and **retained** (rotated out, still published so that old signatures
verify, and never used to sign again).

| | Go | TypeScript | Python |
|---|---|---|---|
| Local file (mode 0600, Ed25519 or ES256) | `dnsid.LoadOrCreateLocalKeyProvider(path, dnsid.JoseAlgEdDSA)` | `await LocalKeyProvider.load(path, true)` (`@dnsid-ai/sdk/node`) | `LocalKeyProvider.load(path, create_if_missing=True)` |
| A CLI key for a domain | `config.IdentityManagerFromDnsid`, or `dnsid.NewLocalKeyProvider(".../private.jwk")` | `LocalKeyProvider.fromDomain('agent.example')` (read-only) | `LocalKeyProvider.from_domain("agent.example")` (read-only) |
| AWS KMS | `awskms.Load(ctx, awskms.SDKClient{…}, awskms.Config{…})` (module `key/aws`) | `AwsKmsKeyProvider.load(new AwsSdkKmsFacade(kms), {…})` (`@dnsid-ai/key-aws`) | `AwsKmsKeyProvider.load(BotoKmsFacade(boto3.client("kms")), AwsKmsConfig(…))` (`[aws]` extra) |
| GCP KMS | — | `@dnsid-ai/key-gcp` | — |

KMS notes:

- Supported algorithms are `ECDSA_SHA_256` (ES256) and `ED25519_SHA_512`
  (EdDSA). The minimum IAM permissions are `kms:GetPublicKey` and `kms:Sign`.
- KMS rotation state (which key is active, retained, or pending) lives **only
  in memory**. Save `provider.State()` / `stateSnapshot()` /
  `state_snapshot()` after every change, and restore it at startup.
- The SDK environment loaders do not read KMS settings. Construct the KMS
  provider in code and pass it in. The Claude Agent SDK plugin is the
  exception: it reads `DNSID_AWS_KMS_KEY_ID` itself.

To write a custom provider (another HSM or KMS), implement the interface
(Go `dnsid.KeyProvider`, 8 methods; TS `KeyProvider`; Py
`dnsid.interfaces.KeyProvider`), using the AWS provider as a model. A key ID
must never contain `#`, because signers are identified as `domain#kid`.

**Serving the JWKS:** publish one entry for each listed key ID: the active key
and the retained keys, never pending ones. In Go, use `idm.GetKeySet()` and
`idm.GetEntityKeySet()`.

## Rotation

Calling `GenerateKey`, `Activate`, or `Supersede` changes **only the local
key material**. The protocol requires every change of operational key to
appear as a signed `KEY_ROTATION` event in the lifecycle log. In that event
the old key authorizes the new key, and the new key proves possession. If
the event is missing, verifiers reject the new key with `KEY_CONTINUITY`.
Rotate with the SDK's rotation flow, which writes the event:

- Go: `c2sptlog.RotateManagedOperationalKey` / `ResumeManagedOperationalKeyRotation`
- TypeScript: `rotateManagedOperationalKey` (`@dnsid-ai/sdk`)
- Python: `manager.rotate_operational_key` / `resume_key_rotation` / `activate_rotated_key`

These flows can be resumed: they persist intermediate state so that a crash
between log submission and activation can recover. Keep the old key in the
retained state until every verifier's caches have expired.

Keys under `~/.dnsid` belong to the CLI. TypeScript and Python load them
read-only, so a rotation made there in memory is lost on restart. Go's file
provider *can* write to the CLI's key file. Avoid that unless the CLI is out
of the picture. When the SDK manages rotation, give it its own key store.
