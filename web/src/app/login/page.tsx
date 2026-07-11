import Image from "next/image";
import { redirect } from "next/navigation";
import { AuthError } from "next-auth";
import { signIn, auth } from "@/auth";
import { authConfig, keycloakReady } from "@/lib/auth-config";

export const metadata = { title: "Sign in · Scopic Claude Analytics" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ callbackUrl?: string; error?: string }>;
}) {
  const { callbackUrl, error } = await searchParams;
  const cb = typeof callbackUrl === "string" ? callbackUrl : "/real-cost";

  // Already signed in (or auth disabled) → go straight to the dashboard.
  if (!authConfig.enabled) redirect(cb);
  const session = await auth();
  if (session?.user) redirect(cb);

  async function ssoSignIn() {
    "use server";
    await signIn("keycloak", { redirectTo: cb });
  }

  async function localSignIn(formData: FormData) {
    "use server";
    try {
      await signIn("local", {
        username: String(formData.get("username") ?? ""),
        password: String(formData.get("password") ?? ""),
        redirectTo: cb,
      });
    } catch (err) {
      // signIn throws a redirect on success — let that propagate.
      if (err instanceof AuthError) {
        redirect(`/login?error=credentials&callbackUrl=${encodeURIComponent(cb)}`);
      }
      throw err;
    }
  }

  return (
    <main className="brand-aura flex min-h-screen items-center justify-center px-6">
      <div className="panel w-full max-w-sm p-8">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <Image
            src="/scopic-logo.webp"
            alt="Scopic"
            width={160}
            height={57}
            priority
            unoptimized
            className="h-9 w-auto"
          />
          <div>
            <h1 className="text-lg font-semibold">AI Usage Analytics</h1>
            <p className="text-sm text-[var(--color-muted)]">Sign in to continue</p>
          </div>
        </div>

        {error && (
          <p className="mb-4 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {error === "AccessDenied"
              ? "Your account doesn't have access to this dashboard."
              : "Invalid credentials. Please try again."}
          </p>
        )}

        {keycloakReady && (
          <form action={ssoSignIn}>
            <button
              type="submit"
              className="flex w-full items-center justify-center gap-2 rounded-md bg-[var(--color-scopic)] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[var(--color-scopic-light)]"
            >
              Sign in with Scopic SSO
            </button>
          </form>
        )}

        {keycloakReady && authConfig.local.enabled && (
          <div className="my-5 flex items-center gap-3 text-xs uppercase tracking-wide text-[var(--color-muted)]">
            <span className="h-px flex-1 bg-[var(--color-panel-border)]" />
            or
            <span className="h-px flex-1 bg-[var(--color-panel-border)]" />
          </div>
        )}

        {authConfig.local.enabled && (
          <form action={localSignIn} className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-[var(--color-muted)]">
                Username
              </label>
              <input
                name="username"
                autoComplete="username"
                defaultValue=""
                className="w-full rounded-md border border-[var(--color-panel-border)] bg-[var(--color-ink)] px-3 py-2 text-sm outline-none focus:border-[var(--color-scopic)]"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-[var(--color-muted)]">
                Password
              </label>
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                className="w-full rounded-md border border-[var(--color-panel-border)] bg-[var(--color-ink)] px-3 py-2 text-sm outline-none focus:border-[var(--color-scopic)]"
              />
            </div>
            <button
              type="submit"
              className="w-full rounded-md border border-[var(--color-scopic)] px-4 py-2.5 text-sm font-semibold text-[var(--color-scopic-light)] transition-colors hover:bg-[var(--color-scopic)]/10"
            >
              Sign In
            </button>
          </form>
        )}

      </div>
    </main>
  );
}
