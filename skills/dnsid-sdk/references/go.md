# Go SDK (`github.com/dnsid-ai/dnsid-go`)

The Go module is the reference implementation of the protocol. Full API
reference: https://docs.dnsid.ai/reference/go/overview

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
go get github.com/dnsid-ai/dnsid-go
go mod tidy          # needed: go get resolves only the root package, tidy pulls what config/httpsig need
go get github.com/dnsid-ai/dnsid-go/key/aws   # separate module, only for AWS KMS
```

Packages: `dnsid` (root: manager, records, keys, errors), `config` (env and
CLI loaders), `httpsig`, `webbotauth`, `jose`, `oidc`, `log`, and
`log/c2sptlog`.

## Create a manager

```go
import (
    dnsid "github.com/dnsid-ai/dnsid-go"
    "github.com/dnsid-ai/dnsid-go/config"
)

// DNSID_* env (dnsid local run / dnsid local env). getenv nil = os.Getenv.
idm, err := config.IdentityManagerFromEnvironment(ctx, nil, dnsid.Config{}, config.Dependencies{})

// ~/.dnsid written by the CLI ("" = default dir)
idm, err := config.IdentityManagerFromDnsid(ctx, "", dnsid.Config{}, config.Dependencies{})

// Explicit
idm, err := dnsid.NewIdentityManager(cfg, keyProvider, dnsid.WithLogRegistry(reg) /*, dnsid.WithEntityKeyProvider(ekp) */)
verifier, err := dnsid.NewVerifier(dnsid.WithLogRegistry(reg))   // verify-only, no key
```

The third argument to the `config` loaders (`dnsid.Config`) is an overlay.
Use it to add verification policy. `config.Dependencies` lets you inject
`LogRegistry`, `KeyProvider`, `EntityKeyProvider`, `DNSResolver`,
`HTTPClient`, and `IdentityCache`.

A verify-only manager with DNSid-managed log trust, for production
verification of identities on `log.dnsid.ai`:

```go
import "github.com/dnsid-ai/dnsid-go/log/c2sptlog"

reg, err := c2sptlog.NewDnsidManagedVerificationRegistry(ctx, c2sptlog.DnsidManagedVerificationConfig{})
if err != nil { return err }
verifier, err := dnsid.NewVerifier(dnsid.WithLogRegistry(reg))
```

## Verify a peer domain

```go
vd, err := idm.VerifyDomain(ctx, "alice.test")
if err != nil {
    var ve *dnsid.VerificationError
    if errors.As(err, &ve) {
        // ve.Code() e.g. dnsid.VerificationCodeStatusNotActive; ve.Transient(); ve.AgentState()
        log.Printf("not verified: code=%s transient=%t", ve.Code(), ve.Transient())
    }
    return err
}
fmt.Println(vd.Domain(), vd.Status().State, vd.Record().GovernanceID)
// alice.test ACTIVE alice.test
```

Compare against the constants `dnsid.VerificationCode*`. Their string values
are snake_case, for example `dns_resolution`. Go also has
`VerificationCodeJWKSUnavailable` (`jwks_unavailable`), which the other SDKs
do not have. `VerifyDomain` runs under an internal deadline
(`dnsid.VerificationContext`). Still pass a context with a timeout from your
request.

For high-value operations: `if vd.RequiresLogCheck() || localPolicy {
idm.VerifyLogEvidence(ctx, vd, time.Time{}) }`. See
`log-trust-and-keys.md`.

## Accept only known counterparties

```go
idm, err := config.IdentityManagerFromEnvironment(ctx, nil, dnsid.Config{
    Verification: dnsid.VerificationConfig{
        TrustedEntities: []dnsid.TrustedEntity{{GovernanceID: "acme.example"}},
    },
}, config.Dependencies{})
```

A peer not on the list fails with `counterparty_not_accepted`, which is
always permanent.

## Protect an HTTP endpoint (inbound RFC 9421)

```go
import (
    "context"
    "errors"
    "log"
    "net/http"
    "regexp"
    "sync"
    "time"

    dnsid "github.com/dnsid-ai/dnsid-go"
    "github.com/dnsid-ai/dnsid-go/httpsig"
)

type callerKey struct{}

// requireDNSid verifies every request against the pinned public host and passes
// the verified *dnsid.VerifiedDomain to next via the request context.
func requireDNSid(profile *httpsig.Profile, publicHost string, guard *replayGuard, next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        r.Body = http.MaxBytesReader(w, r.Body, 1<<20)
        pub := r.Clone(r.Context())
        u := *r.URL
        u.Scheme, u.Host = "https", publicHost // signature covers the public URL; never trust r.Host
        pub.URL, pub.Host = &u, publicHost

        caller, err := profile.VerifyHTTPRequest(r.Context(), pub)
        if err != nil {
            var ve *dnsid.VerificationError
            if errors.As(err, &ve) {
                log.Printf("dnsid rejected: %s", ve.Code())
            }
            http.Error(w, "unauthorized", http.StatusUnauthorized)
            return
        }
        if !guard.firstUse(r.Header.Get("Signature-Input")) {
            http.Error(w, "unauthorized", http.StatusUnauthorized)
            return
        }
        next.ServeHTTP(w, pub.WithContext(context.WithValue(pub.Context(), callerKey{}, caller)))
    })
}

// replayGuard accepts each (keyid, nonce) once within the signature max age.
// In-memory and per process. Across replicas, use a shared store (e.g. Redis SET NX EX).
type replayGuard struct {
    mu   sync.Mutex
    seen map[string]time.Time
    ttl  time.Duration // >= httpsig max age (default 5m) + skew
}

var (
    keyidRe = regexp.MustCompile(`keyid="([^"]+)"`)
    nonceRe = regexp.MustCompile(`nonce="([^"]+)"`)
)

func (g *replayGuard) firstUse(sigInput string) bool {
    k, n := keyidRe.FindStringSubmatch(sigInput), nonceRe.FindStringSubmatch(sigInput)
    if k == nil || n == nil {
        return false
    }
    key, now := k[1]+" "+n[1], time.Now()
    g.mu.Lock()
    defer g.mu.Unlock()
    for s, until := range g.seen {
        if now.After(until) {
            delete(g.seen, s)
        }
    }
    if _, dup := g.seen[key]; dup {
        return false
    }
    g.seen[key] = now.Add(g.ttl)
    return true
}

// Wiring (idm built once at startup):
//   profile := httpsig.NewFromIdentityManagerKeyProvider(idm, httpsig.Config{}) // MaxAge, ClockSkew
//   guard := &replayGuard{seen: map[string]time.Time{}, ttl: 5*time.Minute + 10*time.Second}
//   http.Handle("/orders", requireDNSid(profile, "orders.example", guard, ordersHandler))
// In the handler:
//   caller := r.Context().Value(callerKey{}).(*dnsid.VerifiedDomain); authorize on caller.Domain()
```

Notes:

- `VerifyHTTPRequest` accepts at most two eligible signatures and rejects a
  request with more than one valid one. When a body is present, it enforces
  that `content-digest` is covered and matches. The Go verifier has no
  required-tag option. If you use tags, parse `Signature-Input` and check the
  tag yourself, as the replay guard does for the nonce.
- Rate-limit inbound requests before verification. Every new signer domain
  costs DNS, HTTPS, and log fetches.
- `httpsig.Config{MaxAge, ClockSkew}` sets freshness (defaults 5m and 5s).
  Use a short `MaxAge` for routes that change state.

## Sign outbound requests

```go
profile := httpsig.NewFromIdentityManagerKeyProvider(idm, httpsig.Config{})

// Every request through client is signed. Build once and reuse.
client := profile.CreateSignedHTTPClient(http.DefaultClient, httpsig.SigningOptions{Tag: "example-orders-v1"})
resp, err := client.Post("https://orders.example/v1/orders", "application/json", body)

// One-off
signed, err := profile.CreateSignedHTTPRequest(req, httpsig.SigningOptions{Tag: "example-orders-v1"})
```

`SigningOptions`: `Tag`, `AdditionalComponents`, `ExpiresIn`, and `Label`.
When a body is present, the signer adds `Content-Digest` and covers it. If a
model chooses the URL, call `idm.VerifyDomain(ctx, req.URL.Hostname())` before
you send.

## Tokens (JOSE / OIDC)

- `jose`: `jose.NewFromIdentityManagerKeyProvider(idm, jose.Config{})` gives
  `CreateJWT`, `VerifyJWT`, `CreateJWS`, and `VerifyJWS`.
- `oidc`: `oidc.NewFromIdentityManagerKeyProvider(idm, oidc.Config{})` gives
  `GetOIDCToken` (assertion plus exchange), `CreateOIDCAssertion`,
  `DiscoverOIDCIssuer`, and `VerifyOIDCToken` (which checks claims, then
  verifies the subject's DNSid identity).

Cookbook recipe 29 (`dnsid-message-board`) is a complete Go OIDC example. It
pins the issuer and audience, requires `jti`, and applies an environment
policy. Option structs:
https://docs.dnsid.ai/reference/go/jose and
https://docs.dnsid.ai/reference/go/oidc.

## Publish a self-managed record

```go
kp, err := dnsid.LoadOrCreateLocalKeyProvider("agent-keys.json", dnsid.JoseAlgEdDSA)   // operational
ekp, err := dnsid.LoadOrCreateLocalKeyProvider("entity-keys.json", dnsid.JoseAlgEdDSA) // entity: different key

idm, err := dnsid.NewIdentityManager(dnsid.Config{
    Identity: &dnsid.IdentityConfig{
        Domain:       "agent.example",
        GovernanceID: "example.com",
        LogRef:       "c2sp-tlog:public:https://log.example.com#<fresh-random-stream-id>",
        StatusURL:    "https://agent.example/.well-known/dnsid/status.json",
        EntityKeyURL: "https://example.com/.well-known/dnsid/ek.json", // ek=, host must be gi or below
        KeyURL:       "https://agent.example/.well-known/jwks.json",  // ku=
    },
}, kp, dnsid.WithEntityKeyProvider(ekp))

rec, err := idm.CreateTXTRecord()
txt := rec.Serialize() // value for _dnsid.agent.example
```

Serve the JWKS documents with `idm.GetKeySet()` (operational) and
`idm.GetEntityKeySet()` (entity). The C2SP ISSUANCE goes through the log
APIs (`GenerateIssuanceEvent`, `SignAndWriteEvent`).

## Smoke test on DNSid Local

```bash
dnsid local up
dnsid local agent ensure alice --upstream http://localhost:4001
eval "$(dnsid local env alice)" && dnsid log issue --domain alice.test
go build -o bin/server ./server && dnsid local run bob --port 4556 -- ./bin/server
```

As alice, sign a request for `https://bob.test/orders` and send it to
`http://127.0.0.1:4556/orders`, the way a reverse proxy would. Go's default
resolver cannot resolve `*.test`.
