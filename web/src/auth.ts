import NextAuth, { type NextAuthConfig } from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Keycloak from "next-auth/providers/keycloak";
import { authConfig, keycloakReady } from "@/lib/auth-config";

/**
 * NextAuth (Auth.js v5) instance.
 *
 * Providers are assembled conditionally:
 * - Keycloak OIDC — only when fully configured (Scopic SSO button).
 * - Credentials — the local break-glass login (always available unless
 *   disabled), validated against LOCAL_USERNAME / LOCAL_PASSWORD.
 *
 * Session strategy is JWT (required for the Credentials provider and fine for
 * OIDC), so no session store is needed.
 */
const providers: NextAuthConfig["providers"] = [];

if (keycloakReady) {
  providers.push(
    Keycloak({
      issuer: authConfig.keycloak.issuer,
      clientId: authConfig.keycloak.clientId,
      clientSecret: authConfig.keycloak.clientSecret,
      authorization: { params: { scope: "openid email profile roles" } },
    }),
  );
}

/**
 * Pull the user's Keycloak roles out of the sign-in payload. Roles can surface
 * in a few shapes depending on the realm's mappers, so we union them all:
 * a flattened top-level `roles` claim (what Grafana reads), plus the standard
 * `realm_access` / `resource_access` arrays decoded from the access token.
 */
function rolesFromSignIn(
  profile: Record<string, unknown> | null | undefined,
  accessToken: string | undefined,
): Set<string> {
  const roles = new Set<string>();
  const add = (val: unknown) => {
    if (Array.isArray(val)) {
      for (const r of val) if (typeof r === "string") roles.add(r);
    }
  };

  add(profile?.roles);

  if (accessToken) {
    try {
      // Edge-safe base64url decode (this file is bundled into middleware, where
      // Node's Buffer isn't available — atob/TextDecoder are Web standards).
      const seg = accessToken.split(".")[1];
      if (seg) {
        const b64 = seg.replace(/-/g, "+").replace(/_/g, "/");
        const json = new TextDecoder().decode(
          Uint8Array.from(
            atob(b64.padEnd(Math.ceil(b64.length / 4) * 4, "=")),
            (c) => c.charCodeAt(0),
          ),
        );
        const payload = JSON.parse(json);
        add(payload.roles);
        add(payload.realm_access?.roles);
        for (const client of Object.values(payload.resource_access ?? {})) {
          add((client as { roles?: unknown })?.roles);
        }
      }
    } catch {
      // Malformed token → no roles extracted → treated as unauthorized below.
    }
  }

  return roles;
}

if (authConfig.local.enabled) {
  providers.push(
    Credentials({
      id: "local",
      name: "Local",
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" },
      },
      authorize(credentials) {
        const ok =
          credentials?.username === authConfig.local.username &&
          credentials?.password === authConfig.local.password;
        if (!ok) return null;
        return {
          id: "local-admin",
          name: authConfig.local.username,
          email: `${authConfig.local.username}@local`,
        };
      },
    }),
  );
}

export const { handlers, signIn, signOut, auth } = NextAuth({
  trustHost: true,
  secret: authConfig.secret,
  session: { strategy: "jwt" },
  providers,
  pages: { signIn: "/login", error: "/login" },
  callbacks: {
    /**
     * Role gate for SSO. Mirrors Grafana's strict role mapping: a Keycloak user
     * must hold one of authConfig.allowedRoles, otherwise sign-in is denied
     * (Auth.js redirects to /login?error=AccessDenied). The local break-glass
     * login bypasses this. An empty allowedRoles list disables the gate.
     */
    signIn({ account, profile }) {
      if (account?.provider !== "keycloak") return true;
      if (authConfig.allowedRoles.length === 0) return true;
      const roles = rolesFromSignIn(profile, account.access_token);
      return authConfig.allowedRoles.some((r) => roles.has(r));
    },
    /**
     * Gate used by middleware. When auth is disabled the dashboard is fully
     * open; otherwise everything except the login page, the auth endpoints, and
     * the healthcheck requires a session (a falsy return redirects to /login).
     */
    authorized({ auth: session, request }) {
      if (!authConfig.enabled) return true;
      const { pathname } = request.nextUrl;
      if (
        pathname.startsWith("/login") ||
        pathname.startsWith("/api/auth") ||
        pathname === "/api/health"
      ) {
        return true;
      }
      return !!session?.user;
    },
  },
});
