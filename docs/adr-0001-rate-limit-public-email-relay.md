# ADR-0001: Rate limiting for the public email relay (`POST /emails/send`)

**Status:** Proposed
**Date:** 2026-09-17
**Deciders:** Marcos / DevButter

## Context

`POST /emails/send` (added in this slice, see `app/emails/`) lets any tenant DevButter has issued an `X-Api-Key` to send transactional email through our Brevo account, from any sender domain it has registered and verified (`app/sender_domains/`). Authentication (`app/tenants/dependencies.py::require_client_api_key`) and domain ownership (`app/emails/service.py::EmailService.send`) are both enforced today — but nothing bounds *how many* emails a given tenant can send per unit of time.

That gap matters specifically because this is a *relay*: every message goes out under DevButter's own Brevo sending reputation, not the tenant's. A compromised tenant key, or just a bug in a tenant's app (a retry loop, a broken batch job), can:
- burn through DevButter's Brevo plan quota/cost on that tenant's behalf,
- get DevButter's shared sending domain/IP reputation flagged for spam, degrading deliverability for every *other* tenant using the same relay,
- go undetected until the Brevo bill or a deliverability complaint surfaces it.

No SLA/volume numbers exist yet for this product (no tenants are onboarded). This ADR proposes a default posture rather than tuning against real traffic.

## Decision

Add a per-tenant rate limit (token bucket) enforced as a FastAPI dependency on `POST /emails/send`, alongside the existing `CurrentTenantDep` gate, following the same dependency-based auth pattern already used for `require_service_api_key` / `require_internal_api_key` / `require_client_api_key` (`app/core/dependencies.py`, `app/tenants/dependencies.py`) rather than pushing enforcement to a reverse proxy or gateway layer.

Recommended limiter: **Redis-backed token bucket, keyed by `tenant_id`**, with the bucket capacity/refill rate stored per-tenant (defaulting to a global setting, overridable per tenant later the same way `DiagnosisRuntimeSettings` already overrides a global default per-flow). A `Retry-After` header is returned on a 429.

## Options Considered

### Option A: Postgres-backed counter (no new infra)

Count/increment rows in the existing `butter_mind` Postgres DB — either a fixed-window counter table (`tenant_id`, `window_start`, `count`) upserted per request, or a rolling count via `SELECT count(*) FROM email_logs WHERE tenant_id = ... AND created_at > now() - interval`.

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low — one more table + repository method, same stack as everything else in `app/tenants/` |
| Cost | None (reuses the existing shared Postgres) |
| Scalability | Weak past moderate throughput — the counting query/upsert adds a write (or a `count()` scan) to Postgres on every send; a fixed window also has the classic edge-of-window burst problem |
| Team familiarity | High — same SQLAlchemy/Alembic pattern used everywhere else in this repo |

**Pros:** zero new operational dependency; trivial to reason about; fits `fastapibuilder-api` layering exactly (repository method, no new infra concept).
**Cons:** row-level contention under concurrent sends from the same tenant needs care (`SELECT ... FOR UPDATE` or an atomic upsert) to avoid a race that lets a burst slip through; a naive implementation is *not* actually atomic and would need real testing to trust under load; couples rate-limit state to the same DB that holds business data.

### Option B: Redis-backed token bucket (recommended)

Each tenant gets a bucket key (`ratelimit:emails:{tenant_id}`) with capacity + refill rate; each send does one atomic Redis operation (`INCR`+`EXPIRE`, or a Lua script for a true token bucket) before calling Brevo.

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low-Medium — one new dependency (`redis`/`redis-py` async client), one new settings var (`REDIS_URL`), a small `RateLimiter` class alongside `app/core/` |
| Cost | Low — a `redis:7-alpine` container already exists in this machine's local infra stack (`infra-redis-1`), but butter_mind does not currently depend on Redis anywhere (`grep -r redis` across `app/`, `pyproject.toml`, `docker-compose.yml` returns nothing) |
| Scalability | Strong — O(1) atomic ops, no contention with the business DB, natural TTL-based windows, handles bursts correctly with a real token-bucket algorithm |
| Team familiarity | New to this repo specifically, but a standard, well-documented pattern |

**Pros:** correct under concurrency without extra care; doesn't add load to Postgres; industry-standard approach for exactly this problem; supports smooth bursts (token bucket) instead of Postgres fixed-window's edge case.
**Cons:** new infra dependency for this service — needs confirming Redis is provisioned (not just present locally) in every target environment, including the Hostinger deploy (`docker-compose.hostinger.yml`) this repo already ships; introduces a new failure mode to decide explicitly: does Redis being unreachable **fail open** (allow sends, degrade protection) or **fail closed** (block sends, one dependency outage takes down the whole relay)? This ADR proposes fail-open with an emitted metric (`emit_metrics`, same pattern as the existing auth gates), since availability of the relay itself should not hinge on the rate limiter.

### Option C: Gateway/reverse-proxy rate limiting (nginx `limit_req`, Hostinger/Cloudflare edge)

Enforce limits outside the FastAPI app entirely, keyed by IP or a request header.

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low in isolation, but inconsistent across environments — local dev (no proxy in front), `docker-compose.yml`, and `docker-compose.hostinger.yml` would each need their own config kept in sync |
| Cost | None beyond existing infra |
| Scalability | Fine, but coarser: keying by `X-Api-Key` value in nginx is possible but clunky, and per-tenant *remaining quota* can't easily be reported back in the response body the way an in-app dependency can |
| Team familiarity | Low for this repo (no reverse-proxy rate-limit config exists in it today) |

**Pros:** zero app code; battle-tested at the infra layer.
**Cons:** breaks the `fastapibuilder-api` convention of cross-cutting concerns living as FastAPI dependencies (`RequireInternalApiKey`-style), splits the auth/authorization story across two layers (app-level API key auth + infra-level rate limit), and doesn't let `POST /emails/send` return a useful `X-RateLimit-Remaining`-style body/header to the tenant.

## Trade-off Analysis

The real choice is **A vs. B** — C is ruled out mainly for consistency-across-environments and because it fights this repo's established pattern of expressing access control as FastAPI dependencies, not infra config.

Between A and B: A costs nothing operationally but needs real concurrency testing to trust (the naive version is easy to get subtly wrong), and adds write load to the same Postgres instance every other domain in this app depends on. B is the textbook-correct tool for this exact problem and doesn't touch Postgres at all, but is a new infra dependency for a service that currently has none — the deciding question is really *"is Redis already an acceptable dependency for butter_mind to take on, given it's reachable in Hostinger too?"* rather than a technical one.

Given the relay is brand new (zero tenants onboarded, no real traffic pattern yet) and correctness-under-concurrency is the actual risk this ADR exists to close, **Option B** is recommended — but only once Redis's availability in every deploy target (not just this machine's local `infra-redis-1`) is confirmed. If that confirmation doesn't land quickly, **Option A** is an acceptable fallback to ship first (with `SELECT ... FOR UPDATE` on the counter row, tested explicitly for the race condition) and can be swapped for B later without changing the dependency's call site (`RequireEmailRateLimit`-style, mirroring `RequireServiceApiKey`).

## Consequences

- **Easier:** abuse from a single compromised/buggy tenant key is bounded automatically; DevButter's shared Brevo reputation is protected; a 429 with `Retry-After` gives tenant developers a clear, actionable signal instead of silent throttling upstream at Brevo.
- **Harder:** one more moving part to operate (Redis) if Option B is chosen — needs monitoring, and the fail-open/fail-closed decision needs to be visible in an on-call runbook, not just this ADR.
- **To revisit:** default bucket size/refill rate are guesses with no traffic data behind them (propose starting conservative, e.g. 100 emails/tenant/minute with burst 20, and loosening per-tenant via a settings override once real usage is observed — same override pattern as `DiagnosisRuntimeSettings`); whether limits should also exist per sender-domain (not just per tenant) once a tenant has multiple verified domains with different reputations.

## Action Items

1. [ ] Marcos confirms Redis is provisioned (or can be) in every deploy target this repo ships to, not just local dev infra
2. [ ] Decide fail-open vs. fail-closed on limiter backend unavailability (this ADR proposes fail-open + metric)
3. [ ] Pick initial bucket capacity/refill defaults (placeholder above: 100/min, burst 20)
4. [ ] Implement `app/core/rate_limit/` (provider abstraction, mirroring `app/core/email/`) + `RequireEmailRateLimit` dependency in `app/emails/dependencies.py`
5. [ ] Add `REDIS_URL` to `app/settings/config.py` + `.env.example`, and to both `docker-compose.yml` and `docker-compose.hostinger.yml` if Option B is confirmed
6. [ ] Tests: concurrent-request test proving the limiter is atomic under load (this is the specific risk Option A needs to survive, and Option B needs to demonstrate too)
