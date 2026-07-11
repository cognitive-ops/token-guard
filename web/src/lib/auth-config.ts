import "server-only";
import { z } from "zod";

/**
 * Auth configuration, kept separate from the NextAuth instance so it can be
 * read by middleware and the login page without importing provider code.
 *
 * Mirrors the Grafana auth model in docker-compose.yml: optional Keycloak SSO
 * (the KEYCLOAK_* env), plus a local break-glass login that always works (the
 * equivalent of Grafana's local admin). Auth as a whole is gated by
 * AUTH_ENABLED so the dashboard can run open in a pure-PoC / CI context.
 */
const AuthEnvSchema = z.object({
  AUTH_ENABLED: z
    .enum(["true", "false"])
    .default("false")
    .transform((v) => v === "true"),
  // NextAuth signing secret. Required when auth is enabled.
  AUTH_SECRET: z.string().optional(),

  // Local break-glass credentials (the "separate login button for local").
  LOCAL_LOGIN_ENABLED: z
    .enum(["true", "false"])
    .default("true")
    .transform((v) => v === "true"),
  LOCAL_USERNAME: z.string().default("admin"),
  LOCAL_PASSWORD: z.string().default("admin"),

  // Keycloak OIDC (same vars the Grafana service consumes).
  KEYCLOAK_ENABLED: z
    .enum(["true", "false"])
    .default("false")
    .transform((v) => v === "true"),
  KEYCLOAK_URL: z.string().optional(),
  KEYCLOAK_REALM: z.string().optional(),
  KEYCLOAK_CLIENT_ID: z.string().optional(),
  KEYCLOAK_CLIENT_SECRET: z.string().optional(),

  // Comma-separated Keycloak roles allowed to sign in (mirrors Grafana's strict
  // role mapping). Empty disables the gate (any authenticated user may enter).
  ALLOWED_ROLES: z.string().default("grafana-viewer,grafana-admin"),
});

const parsed = AuthEnvSchema.parse(process.env);

export const authConfig = {
  enabled: parsed.AUTH_ENABLED,
  secret: parsed.AUTH_SECRET ?? "dev-only-insecure-secret-change-me",
  local: {
    enabled: parsed.LOCAL_LOGIN_ENABLED,
    username: parsed.LOCAL_USERNAME,
    password: parsed.LOCAL_PASSWORD,
  },
  keycloak: {
    enabled: parsed.KEYCLOAK_ENABLED,
    issuer:
      parsed.KEYCLOAK_URL && parsed.KEYCLOAK_REALM
        ? `${parsed.KEYCLOAK_URL.replace(/\/$/, "")}/realms/${parsed.KEYCLOAK_REALM}`
        : undefined,
    clientId: parsed.KEYCLOAK_CLIENT_ID,
    clientSecret: parsed.KEYCLOAK_CLIENT_SECRET,
  },
  allowedRoles: parsed.ALLOWED_ROLES.split(",")
    .map((r) => r.trim())
    .filter(Boolean),
} as const;

/** True when Keycloak is fully configured and can be offered on the login page. */
export const keycloakReady =
  authConfig.keycloak.enabled &&
  !!authConfig.keycloak.issuer &&
  !!authConfig.keycloak.clientId &&
  !!authConfig.keycloak.clientSecret;
