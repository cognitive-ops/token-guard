import { auth, signOut } from "@/auth";
import { authConfig } from "@/lib/auth-config";

/**
 * Shows the signed-in user + a sign-out button. Renders nothing when auth is
 * disabled, so the dashboard looks the same in open/PoC mode.
 */
export async function UserMenu() {
  if (!authConfig.enabled) return null;
  const session = await auth();
  if (!session?.user) return null;

  async function doSignOut() {
    "use server";
    await signOut({ redirectTo: "/login" });
  }

  return (
    <div className="flex items-center gap-3">
      <span className="hidden text-sm text-[var(--color-muted)] sm:block">
        {session.user.email ?? session.user.name}
      </span>
      <form action={doSignOut}>
        <button
          type="submit"
          className="rounded-md border border-[var(--color-panel-border)] px-3 py-1 text-sm text-[var(--color-muted)] transition-colors hover:border-[var(--color-scopic)] hover:text-[var(--color-text)]"
        >
          Sign out
        </button>
      </form>
    </div>
  );
}
