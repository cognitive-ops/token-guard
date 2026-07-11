export { auth as middleware } from "@/auth";

/**
 * Run the auth gate on everything except static assets and the public images.
 * The `authorized` callback in src/auth.ts decides what actually requires a
 * session (and short-circuits entirely when AUTH_ENABLED is false).
 */
export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|token-guard-logo.png|scopic-icon.png).*)",
  ],
};
