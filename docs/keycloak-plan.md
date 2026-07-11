# Keycloak SSO for Grafana

Status: **implemented & tested** (server, 2026-06-09) · Target service: `grafana` (docker-compose)

## Goal

Replace the single shared admin login on Grafana with **Keycloak SSO (OIDC)**, where a
designated subset of users get **Admin**, a designated subset get read-only **Viewer**,
and everyone else is **denied**. Keep the local `admin` account as break-glass.

## Why only Grafana

Grafana is the only authenticated, public-facing service in the stack
(`grafana.claude-analytics.scopicdev.com`). Prometheus, Loki, and the exporters are
internal-network-only behind the ALB and are not directly exposed. So auth work is
scoped to the `grafana` service alone.

## Approach

Grafana has first-class **generic OAuth (OIDC)** support, so this is a config-only
change — environment variables on the `grafana` service plus a Keycloak client. No
custom image changes.

### Role model — two roles, deny-by-default

Access and role are decided at login by a JMESPath expression over the OIDC
token/userinfo claims, combined with **strict mode**:

```
GF_AUTH_GENERIC_OAUTH_ROLE_ATTRIBUTE_PATH=contains(roles[*], 'grafana-admin') && 'Admin' || contains(roles[*], 'grafana-viewer') && 'Viewer'
GF_AUTH_GENERIC_OAUTH_ROLE_ATTRIBUTE_STRICT=true
```

- `roles` claim contains `grafana-admin` → **Admin** (Org Admin: manage dashboards,
  data sources, users within the org).
- `roles` claim contains `grafana-viewer` → **Viewer** (read-only).
- **Neither role → login DENIED.** With no default role in the path and
  `ROLE_ATTRIBUTE_STRICT=true`, Grafana refuses the login instead of granting access.
  This is the real deny-by-default — only the two designated sets of users get in.

The left-hand strings (`grafana-admin`/`grafana-viewer`) are arbitrary **Keycloak role
names** we chose; the right-hand strings (`Admin`/`Viewer`) are Grafana's **built-in org
roles** (fixed vocabulary: `Viewer`, `Editor`, `Admin`). Rename the roles freely as long
as both sides stay in sync.

**Server admin** (instance superuser) is intentionally NOT granted via SSO — it stays as
the local break-glass `admin` account. (If ever needed, gate it behind
`GF_AUTH_GENERIC_OAUTH_ALLOW_ASSIGN_GRAFANA_ADMIN`.)

## How it's wired (as deployed)

- **Keycloak client:** `claude-code-analytics` (confidential, authorization-code flow).
- **Roles:** two **client roles** on that client — `grafana-admin` and `grafana-viewer`.
- **Realm / URL / secret:** supplied via `.env` (`KEYCLOAK_URL`, `KEYCLOAK_REALM`,
  `KEYCLOAK_CLIENT_ID=claude-code-analytics`, `KEYCLOAK_CLIENT_SECRET`).

### Grafana — env vars on the `grafana` service (`docker-compose.yml`)

All values come from `.env`; OAuth is gated off (`KEYCLOAK_ENABLED=false`) until filled:

```
GF_AUTH_GENERIC_OAUTH_ENABLED=${KEYCLOAK_ENABLED:-false}
GF_AUTH_GENERIC_OAUTH_NAME=Token Guard SSO
GF_AUTH_GENERIC_OAUTH_CLIENT_ID=${KEYCLOAK_CLIENT_ID}          # claude-code-analytics
GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET=${KEYCLOAK_CLIENT_SECRET}
GF_AUTH_GENERIC_OAUTH_SCOPES=openid email profile roles
GF_AUTH_GENERIC_OAUTH_AUTH_URL=${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/auth
GF_AUTH_GENERIC_OAUTH_TOKEN_URL=${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token
GF_AUTH_GENERIC_OAUTH_API_URL=${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/userinfo
GF_AUTH_GENERIC_OAUTH_ROLE_ATTRIBUTE_PATH=contains(roles[*], 'grafana-admin') && 'Admin' || contains(roles[*], 'grafana-viewer') && 'Viewer'
GF_AUTH_GENERIC_OAUTH_ROLE_ATTRIBUTE_STRICT=true
GF_AUTH_GENERIC_OAUTH_ALLOW_SIGN_UP=true
# Local break-glass admin login stays enabled — do NOT set GF_AUTH_DISABLE_LOGIN_FORM.
```

`KEYCLOAK_*` live in `.env` (gitignored) — never committed. `GF_SERVER_ROOT_URL` must be
`https://grafana.claude-analytics.scopicdev.com` (the redirect URI derives from it).

### Keycloak client setup

1. Confidential client `claude-code-analytics` (standard / authorization-code flow).
2. **Valid redirect URI:** `https://grafana.claude-analytics.scopicdev.com/login/generic_oauth`
3. Create two **client roles** on the client: `grafana-admin`, `grafana-viewer`.
4. Add the roles mapper (below) so the roles reach Grafana as a flat `roles` claim.

### The roles mapper — critical gotcha

Grafana reads a **top-level `roles`** claim (`roles[*]`). By default Keycloak nests roles
(`resource_access.<client>.roles`), so Grafana sees nothing and **strict mode denies
everyone** with *"IdP did not return a role attribute."* Fix with an explicit mapper.

On this (legacy) Keycloak admin console, mappers live on the client's **Mappers** tab
(not a `<client>-dedicated` scope). **Clients → `claude-code-analytics` → Mappers →
Create**, then:

| Field | Value |
|---|---|
| Name | `roles` *(label only)* |
| Mapper Type | **User Client Role** (because the roles are client roles) |
| Client ID | `claude-code-analytics` |
| Client Role prefix | *(blank)* |
| Multivalued | **On** |
| **Token Claim Name** | **`roles`** |
| Claim JSON Type | **String** |
| Add to ID token / access token / userinfo | **On** (userinfo is essential — Grafana reads it) |

> Use **User Realm Role** instead only if the roles are realm-level. Don't keep two
> mappers writing to the same `roles` claim — they collide.

**Verify** before testing: Clients → `claude-code-analytics` → Client Scopes → **Evaluate**
→ pick a user → **Generated User Info** → confirm `"roles": ["grafana-admin"]`.

### Assigning users

**Users → (user, search by email) → Role Mappings →** assign `grafana-admin` or
`grafana-viewer` (client roles). Leave others unassigned → denied. Add/remove access is a
role assignment in Keycloak — no Grafana redeploy. After changes, sign in again (use an
incognito window) so a fresh token is minted.

## Decisions (resolved)

1. **Keycloak instance** — used an **existing** Scopic Keycloak (realm/URL in `.env`); no
   new Keycloak service stood up.
2. **Tiers** — **two-tier** (Admin / Viewer).
3. **Break-glass** — local `admin` login **kept enabled** (`GF_AUTH_DISABLE_LOGIN_FORM`
   unset).

## Verification checklist (tested on server, 2026-06-09)

- [x] "Sign in with Token Guard SSO" button present on the login page.
- [x] `grafana-admin` user → Admin in Grafana.
- [x] `grafana-viewer` user → Viewer (read-only).
- [x] User with no role → denied (deny-by-default, strict mode).
- [x] Local `admin` break-glass login still functions.

## Notes / follow-ups

- `.env` on the server: keep `KEYCLOAK_ENABLED=true` only with a real `KEYCLOAK_URL` +
  `KEYCLOAK_CLIENT_SECRET`; placeholder values + enabled = a broken SSO button.
- Optional later: a `grafana-editor` role + a third JMESPath branch for an Editor tier;
  `GF_AUTH_OAUTH_AUTO_LOGIN=true` to skip the chooser; hide the login form once SSO is
  trusted org-wide.
