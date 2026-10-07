# TypeScript SDK (`@dnsid-ai/*`)

Full API reference: https://docs.dnsid.ai/reference/ts

## Contents

- Install
- Create a manager
- Verify a peer domain
- Accept only known counterparties
- Protect an HTTP endpoint (inbound RFC 9421)
- Sign outbound requests
- Tokens (JOSE / OIDC)
- Publish a self-managed record
- Smoke test on DNSid Local

## Install

```bash
npm install @dnsid-ai/sdk                   # core + Node transport helpers (@dnsid-ai/sdk/node)
npm install @dnsid-ai/http-signatures       # RFC 9421
npm install @dnsid-ai/log-c2sp-tlog         # only for managed/explicit log trust in code
npm install @dnsid-ai/jose @dnsid-ai/oidc   # only for tokens
npm install @dnsid-ai/key-aws @aws-sdk/client-kms   # only for AWS KMS keys
```

The root `@dnsid-ai/sdk` does not depend on any runtime. Node-specific
constructors come from `@dnsid-ai/sdk/node`. The packages ship both ESM and
CJS. Top-level `await` needs ESM, so use `"type": "module"` or `.mts`. In a
CJS project, wrap the code in an async function.

## Create a manager

```ts
import {
  createNodeIdentityManagerFromEnvironment, // DNSID_* env (dnsid local run / dnsid local env)
  createNodeIdentityManagerFromDnsid,       // ~/.dnsid written by the CLI
  createNodeIdentityManagerFromFile,        // deployment JSON: { dnsid, logTrust, registry }
  createNodeIdentityVerifier,               // verify-only, explicit deps
  createNodeIdentityManager,                // explicit config + keyProvider
} from '@dnsid-ai/sdk/node';

const idm = await createNodeIdentityManagerFromEnvironment();
```

The loader functions take an optional `overlay`: `(env?, overlay?, deps?)` for
the environment loader, and `(dir?, overlay?, deps?)` for the CLI-directory
loader. Use the overlay to add verification policy on top of what the loader
found.

A verify-only manager with DNSid-managed log trust, for production
verification of identities on `log.dnsid.ai`:

```ts
import { createDnsidManagedVerificationRegistry } from '@dnsid-ai/log-c2sp-tlog';
import { createNodeIdentityVerifier } from '@dnsid-ai/sdk/node';

const registry = await createDnsidManagedVerificationRegistry();
const idm = await createNodeIdentityVerifier({}, { logRegistry: registry });
```

Instead of code, a deployment file works too: `{"logTrust":{"managed":true}}`
with `createNodeIdentityManagerFromFile`.

## Verify a peer domain

```ts
import { VerificationCode, VerificationError } from '@dnsid-ai/sdk';

try {
  const vd = await idm.verifyDomain('alice.test');
  console.log(vd.domain, vd.cachedState(), vd.record.gi, vd.expiry());
  // alice.test ACTIVE alice.test 2026-10-07T20:17:26.640Z
} catch (err) {
  if (!(err instanceof VerificationError)) throw err;
  // err.code is a VerificationCode, e.g. 'DNSResolution'; err.transient: boolean; err.agentState
  if (err.code === VerificationCode.StatusNotActive) { /* revoked or retired */ }
  throw err;
}
```

`vd.record` holds the parsed record (`gi`, `ku`, `su`, `lr`, …).
`vd.cachedState()` returns the state while it is still fresh. `vd.expiry()`
says how long the verdict may be cached. For high-value operations, call
`vd.requiresLogCheck()` and then `await vd.verifyNonRevocation()` (see
`log-trust-and-keys.md`).

## Accept only known counterparties

```ts
const idm = await createNodeIdentityManagerFromEnvironment(process.env, {
  verification: { trustedEntities: [{ governanceId: 'acme.example' }] },
});
// or: createNodeIdentityVerifier({ verification: { trustedEntities: [...] } }, { logRegistry })
```

A peer whose `gi` is not on the list fails with
`VerificationCode.CounterpartyNotAccepted`. That error is always permanent and
never cached. Matching is exact, with no wildcards. An entry can also pin
entity-key thumbprints.

## Protect an HTTP endpoint (inbound RFC 9421)

This works with any Node server. The verifier needs a WHATWG `Request` with
the **public** URL and the **raw** body.

```ts
import { createServer } from 'node:http';
import { VerificationError } from '@dnsid-ai/sdk';
import { createNodeIdentityManagerFromEnvironment } from '@dnsid-ai/sdk/node';
import { HttpSignaturesProfile } from '@dnsid-ai/http-signatures';

const PUBLIC_ORIGIN = process.env.PUBLIC_ORIGIN ?? `https://${process.env.DNSID_DOMAIN}`; // pinned, never from Host
const TAG = 'example-orders-v1';     // must match the signer's tag
const MAX_BODY = 1 << 20;
const MAX_AGE_S = 300;               // profile default signature max age

// Build once: holds the verification cache and the log checkpoint store.
const idm = await createNodeIdentityManagerFromEnvironment(process.env, {
  verification: { trustedEntities: [{ governanceId: 'acme.example' }] },
});
const profile = HttpSignaturesProfile.fromIdentityManager(idm);

// Replay guard. Verification checks freshness, not reuse.
// In-memory and per process. Across replicas, use a shared store (e.g. Redis SET NX EX).
const seen = new Map<string, number>();
function isReplay(signatureInput: string): boolean {
  const now = Date.now();
  for (const [k, until] of seen) if (until < now) seen.delete(k);
  const keyid = /keyid="([^"]+)"/.exec(signatureInput)?.[1];
  const nonce = /nonce="([^"]+)"/.exec(signatureInput)?.[1];
  if (!keyid || !nonce) return true;
  const key = `${keyid} ${nonce}`;
  if (seen.has(key)) return true;
  seen.set(key, now + (MAX_AGE_S + 5) * 1000);
  return false;
}

createServer(async (req, res) => {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const c of req) {
    size += c.length;
    if (size > MAX_BODY) { res.writeHead(413).end(); return; }
    chunks.push(c);
  }
  const body = Buffer.concat(chunks);
  const headers = new Headers();
  for (const [k, v] of Object.entries(req.headers)) if (typeof v === 'string') headers.set(k, v);
  const request = new Request(new URL(req.url ?? '/', PUBLIC_ORIGIN), {
    method: req.method, headers, body: body.length ? body : undefined,
  });

  try {
    const caller = await profile.verifySignedHttpRequest(request, { requiredTag: TAG });
    if (isReplay(headers.get('signature-input') ?? '')) throw new Error('replayed signature');
    // caller.domain is the verified identity. Authorize on it, not on headers.
    res.writeHead(200, { 'content-type': 'application/json' })
       .end(JSON.stringify({ caller: caller.domain }));
  } catch (err) {
    console.error('rejected:', err instanceof VerificationError ? err.code : (err as Error).message);
    res.writeHead(401).end('unauthorized');
  }
}).listen(Number(process.env.PORT));
```

To adapt this for a framework:

- **Express:** mount `express.raw({ type: '*/*', limit: '1mb' })` before the
  verifier so that `req.body` is the raw `Buffer`. Do not verify after
  `express.json()` has parsed and discarded the original bytes.
- **Hono, Next.js route handlers, and Workers** already give you a `Request`.
  Clone it with the pinned public URL before you verify:
  `const u = new URL(req.url); const pub = new Request(PUBLIC_ORIGIN + u.pathname + u.search, req);`.
  Verify `pub`, and if your handler also reads the body, give it the buffered
  bytes.
- `verifySignedHttpRequest(request, { requiredComponents, requiredTag })`:
  `requiredComponents` defaults to `@method`, `@authority`, `@target-uri`.
  When a body is present, `content-digest` is enforced automatically.
- Freshness settings: `HttpSignaturesProfile.fromIdentityManager(idm, { maxAge: 60, clockSkew: 5 })`
  (in seconds; the defaults are 300 and 5). Use a short `maxAge` for routes
  that change state.

## Sign outbound requests

```ts
import { HttpSignaturesProfile } from '@dnsid-ai/http-signatures';

const profile = HttpSignaturesProfile.fromIdentityManager(idm); // idm must have the agent's key

// Every request through signedFetch is signed. Wrap once and reuse.
const signedFetch = profile.createSignedFetch({ fetch, signing: { tag: 'example-orders-v1' } });
const res = await signedFetch('https://orders.example/v1/orders', {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify(order),
});

// One-off: returns a signed copy
const signed = await profile.createSignedHttpRequest(request, { tag: 'example-orders-v1' });
```

The signature covers `@method`, `@authority`, and `@target-uri`, plus
`content-digest` when there is a body. It carries `keyid="<domain>#<kid>"`,
`created`, and a random `nonce`. Signing options: `tag`,
`additionalComponents` (for example `['content-type']`), `expiresInSeconds`,
and `label`.

If a model chooses the destination, verify the destination first, so that a
prompt cannot steer signed traffic to an arbitrary host:

```ts
async function callPeer(url: string, init: RequestInit) {
  await idm.verifyDomain(new URL(url).hostname); // throws VerificationError if not a live DNSid identity
  return signedFetch(url, init);
}
```

For the Claude Agent SDK, the plugin `@dnsid-ai/agent-sdk-plugin` already
does this. See dnsid-integrations.

## Tokens (JOSE / OIDC)

- `@dnsid-ai/jose`: `JoseProfile.fromIdentityManager(idm)` creates and
  verifies DNSid JWTs and compact JWS.
- `@dnsid-ai/oidc`: `OIDCProfile.fromIdentityManager(idm, config)` mints an
  RFC 7523 assertion, exchanges it at an issuer, and verifies tokens, which
  includes verifying the subject's DNSid identity.

Look up the exact option names in
https://docs.dnsid.ai/reference/ts/dnsid-jose and
https://docs.dnsid.ai/reference/ts/dnsid-oidc. Always pin `audience` and
`issuer` on the verifier side.

## Publish a self-managed record

```ts
import { createNodeIdentityManager, LocalKeyProvider } from '@dnsid-ai/sdk/node';

const idm = await createNodeIdentityManager(
  {
    identity: {
      domain: 'agent.example',
      governanceId: 'example.com',
      logRef: 'c2sp-tlog:public:https://log.example.com#<fresh-random-stream-id>',
      statusUrl: 'https://agent.example/.well-known/dnsid/status.json',
      ekUrl: 'https://example.com/.well-known/dnsid/ek.json',  // host must be gi or below it
      kuUrl: 'https://agent.example/.well-known/jwks.json',
      // optional: policyFlags ('logchk'), maxKeyAge ('30d'), capabilitiesUrl
    },
  },
  {
    keyProvider: await LocalKeyProvider.load('agent-keys.json', true),        // operational key
    entityKeyProvider: await LocalKeyProvider.load('entity-keys.json', true), // a DIFFERENT key
  },
);
const txt = await idm.createTxtRecord(); // the TXT value to publish at _dnsid.agent.example
```

Serve each key's public JWKS (active and retained keys, never pending ones)
at the matching URL. Then publish the TXT value with your DNS tooling, and
check it with `dnsid record verify --domain agent.example`.

## Smoke test on DNSid Local

```bash
dnsid local up
dnsid local agent ensure alice --upstream http://localhost:4001
eval "$(dnsid local env alice)" && dnsid log issue --domain alice.test
dnsid local run bob --port 4555 -- npx tsx server.mts   # bob verifies callers; allowlist alice.test
# in another shell, as alice: sign a request to https://bob.test/... and send it to http://127.0.0.1:4555
eval "$(dnsid local env alice)" && npx tsx client.mts
```

Plain Node `fetch` cannot resolve `*.test`. In local tests, sign the request
for its public URL (`https://bob.test/orders`) and send the signed headers
and body to `http://127.0.0.1:<port>`. This is exactly what a reverse proxy
does in production, so it also tests that your public-origin handling is
right.
