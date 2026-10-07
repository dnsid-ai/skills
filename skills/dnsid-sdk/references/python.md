# Python SDK (`dnsid`)

Full API reference: https://docs.dnsid.ai/reference/py/overview

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

The package is **not on PyPI**. Install it from git, and pin a commit in real
projects:

```bash
pip install "git+https://github.com/dnsid-ai/dnsid-py.git"
pip install "dnsid[aws] @ git+https://github.com/dnsid-ai/dnsid-py.git"     # + AWS KMS
uv add "dnsid @ git+https://github.com/dnsid-ai/dnsid-py.git"               # uv projects
```

There is one package, and everything (HTTP signatures, JOSE, OIDC, C2SP log)
is included. The API is **synchronous**: `verify_domain` blocks on DNS,
HTTPS, and log fetches. In async code, call it through
`await asyncio.to_thread(...)`. The one exception is
`create_signed_async_http_client`, which returns an async httpx client.

## Create a manager

```python
from dnsid import (
    identity_manager_from_environment,  # DNSID_* env (dnsid local run / dnsid local env)
    identity_manager_from_dnsid,        # ~/.dnsid written by the CLI
    identity_manager_from_file,         # deployment JSON: {dnsid, logTrust, registry}
    IdentityManager, IdentityManagerDependencies, DnsidConfig,
)

manager = identity_manager_from_environment()
```

The signature of each loader is `(source=None, overlay=None, key_provider=None,
deps=None)`. Use `overlay=DnsidConfig(...)` to add verification policy. If
`DNSID_DOMAIN` is set, the environment loader also expects the rest of the
identity variables. With no `DNSID_DOMAIN`, it builds a verify-only manager.

A verify-only manager with DNSid-managed log trust, for production
verification of identities on `log.dnsid.ai`:

```python
from dnsid import IdentityManager, IdentityManagerDependencies
from dnsid.c2sp_tlog import create_dnsid_managed_verification_registry

manager = IdentityManager(deps=IdentityManagerDependencies(
    log_registry=create_dnsid_managed_verification_registry()))
```

## Verify a peer domain

```python
from dnsid import VerificationCode, VerificationError

try:
    vd = manager.verify_domain("alice.test")
    print(vd.domain, vd.cached_state(), vd.record.gi, vd.expiry())
    # alice.test ACTIVE alice.test 2026-10-07 20:17:47+00:00
except VerificationError as err:
    # err.code is a VerificationCode enum (e.g. VerificationCode.STATUS_NOT_ACTIVE),
    # err.transient: bool, err.agent_state
    if err.code == VerificationCode.STATUS_NOT_ACTIVE:
        ...  # revoked or retired
    raise
```

For a name with no `_dnsid` record, Python currently raises `RECORD_INVALID`
(not transient). Go and TypeScript use their DNS-resolution code for the same
case. Treat every `VerificationError` as "not verified".

All SDK exceptions derive from `dnsid.DNSidError`. `VerificationError` is the
subclass for failed verifications.

## Accept only known counterparties

```python
from dnsid import DnsidConfig, TrustedEntity, VerificationConfig

manager = identity_manager_from_environment(overlay=DnsidConfig(
    verification=VerificationConfig(trusted_entities=[TrustedEntity(governance_id="acme.example")]),
))
```

A peer whose `gi` is not on the list fails with
`VerificationCode.COUNTERPARTY_NOT_ACCEPTED`, which is always permanent.

## Protect an HTTP endpoint (inbound RFC 9421)

The verifier takes a `dnsid.models.HttpRequest` built from the **public** URL
and the **raw** body. This ASGI middleware works under FastAPI, Starlette,
and any other ASGI app. It is adapted from cookbook recipe 31
(`langchain-dnsid`).

```python
import asyncio, json, time
from urllib.parse import urlsplit
from dnsid import DNSidError, HttpMessageSignatureConfig, HttpSignatureProfile, IdentityManager
from dnsid.models import HttpRequest, HttpVerificationOptions, SignatureParams

MAX_BODY = 1 << 20

class DnsidAuthMiddleware:
    """Admit only DNSid-signed requests; put the verified domain on scope["state"]["dnsid_caller"]."""

    def __init__(self, app, manager: IdentityManager, *, public_url: str, tag: str):
        origin = urlsplit(public_url)                 # pinned config, never the Host header
        if origin.scheme != "https" or not origin.hostname:
            raise ValueError("public_url must be an https origin")
        self.app, self.authority, self.tag = app, origin.netloc, tag
        self.sig_config = HttpMessageSignatureConfig()  # max_age=300s, clock_skew=5s by default
        self.profile = HttpSignatureProfile.from_identity_manager(manager, self.sig_config)
        self.seen: dict[tuple[str, str], float] = {}  # per process; use a shared store across replicas

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body, more = b"", True                        # content-digest covers exact bytes: buffer first
        while more:
            msg = await receive()
            body += msg.get("body", b"")
            more = msg.get("more_body", False)
            if len(body) > MAX_BODY:
                return await _reply(send, 413, "request body too large")

        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
        headers["host"] = self.authority
        path = (scope.get("raw_path") or scope["path"].encode()).decode("latin-1")
        query = scope.get("query_string", b"").decode("latin-1")
        url = f"https://{self.authority}{path}" + (f"?{query}" if query else "")
        try:
            caller = await asyncio.to_thread(
                self.profile.verify_signed_http_request,
                HttpRequest(method=scope["method"], url=url, headers=headers, body=body or None),
                HttpVerificationOptions(required_tag=self.tag),
            )
        except DNSidError:
            return await _reply(send, 401, "unauthorized")   # log the code server-side
        if self._replayed(headers, caller.domain):
            return await _reply(send, 401, "unauthorized")

        scope = {**scope, "state": {**scope.get("state", {}), "dnsid_caller": caller.domain}}
        sent = False
        async def replay_body():
            nonlocal sent
            if sent:
                return await receive()
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await self.app(scope, replay_body, send)

    def _replayed(self, headers, domain) -> bool:
        now = time.time()
        self.seen = {k: t for k, t in self.seen.items() if t > now}
        params = [p for p in SignatureParams.parse_dictionary(headers["signature-input"]).values()
                  if p.tag == self.tag and p.key_id.startswith(f"{domain}#")]
        if not params or any(not p.nonce or (p.key_id, p.nonce) in self.seen for p in params):
            return True
        for p in params:
            self.seen[(p.key_id, p.nonce)] = (p.created or now) + self.sig_config.max_age.total_seconds() + 1
        return False

async def _reply(send, status, message):
    body = json.dumps({"error": message}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": body})
```

Usage with FastAPI:
`app.add_middleware(DnsidAuthMiddleware, manager=manager, public_url="https://bob.example", tag="example-orders-v1")`.
Then read `request.state.dnsid_caller` in your handlers, and authorize on
that value.

Flask and other WSGI apps: build `HttpRequest(method, url, headers, body)` in
a `before_request` hook, using the pinned public URL and
`request.get_data(cache=True)`.

## Sign outbound requests

```python
import httpx
from dnsid import HttpSignatureProfile
from dnsid.models import HttpRequest, HttpSigningOptions

profile = HttpSignatureProfile.from_identity_manager(manager)   # manager holds the agent's key
opts = HttpSigningOptions(tag="example-orders-v1")

client = profile.create_signed_http_client(httpx.Client(), opts)          # sync: every request signed
aclient = profile.create_signed_async_http_client(opts=opts)              # async httpx.AsyncClient
resp = client.post("https://orders.example/v1/orders", json={"qty": 1})

# One-off request
signed = profile.create_signed_http_request(
    HttpRequest(method="POST", url="https://orders.example/v1/orders",
                headers={"content-type": "application/json"}, body=b'{"qty":1}'), opts)
```

`HttpSigningOptions` fields: `tag`, `additional_components` (for example
`["content-type"]`), `expires_in_seconds`, and `label`.

To verify the destination before signing when a model chooses the URL, attach
an httpx request hook. Recipe 31's `egress.py` is the reference version:

```python
async def verify_peer(request: httpx.Request) -> None:
    await asyncio.to_thread(manager.verify_domain, request.url.host)   # raises if not a live identity
aclient.event_hooks["request"] = [verify_peer]
```

## Tokens (JOSE / OIDC)

- `dnsid.jose`: `create_jwt`, `verify_jwt`, `create_jws`, `verify_jws`
- `dnsid.oidc`: `create_oidc_assertion`, `mint_oidc_token` (assertion
  exchange), `verify_oidc_token` (checks claims and the subject's DNSid
  identity)

Get constructors and option dataclasses from
https://docs.dnsid.ai/reference/py/profile-jose and
https://docs.dnsid.ai/reference/py/profile-oidc. Cookbook recipe 28 mints
DNSid OIDC tokens from Python for AgentCore Gateway.

## Publish a self-managed record

```python
from dnsid import DnsidConfig, IdentityConfig, IdentityManager, IdentityManagerDependencies, LocalKeyProvider

manager = IdentityManager(
    DnsidConfig(identity=IdentityConfig(
        domain="agent.example",
        governance_id="example.com",
        log_ref="c2sp-tlog:public:https://log.example.com#<fresh-random-stream-id>",
        status_url="https://agent.example/.well-known/dnsid/status.json",
        ek_url="https://example.com/.well-known/dnsid/ek.json",   # host must be gi or below
        ku_url="https://agent.example/.well-known/jwks.json",
    )),
    LocalKeyProvider.load("agent-keys.json", create_if_missing=True),            # operational key
    IdentityManagerDependencies(
        entity_key_provider=LocalKeyProvider.load("entity-keys.json", create_if_missing=True)),  # different key
)
txt = manager.create_txt_record()   # TXT value for _dnsid.agent.example
```

## Smoke test on DNSid Local

```bash
dnsid local up
dnsid local agent ensure alice --upstream http://localhost:4001
eval "$(dnsid local env alice)" && dnsid log issue --domain alice.test
dnsid local run bob --port 4555 -- uvicorn app:app --port 4555    # bob verifies callers
```

To exercise the endpoint, run as alice. Sign a request for
`https://bob.test/...`, then send the signed headers and body to
`http://127.0.0.1:4555/...`, the way a reverse proxy would. Plain httpx
cannot resolve `*.test` names.
