"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="mx-auto max-w-2xl px-6 py-16 text-center">
      <h1 className="text-lg font-semibold text-red-400">
        Could not load Real Cost
      </h1>
      <p className="mt-2 text-sm text-[var(--color-muted)]">
        A datasource query failed. Check that Prometheus and Loki are reachable
        from the web service.
      </p>
      <pre className="mt-4 overflow-x-auto rounded bg-[var(--color-panel)] p-3 text-left text-xs text-[var(--color-muted)]">
        {error.message}
      </pre>
      <button
        onClick={reset}
        className="mt-4 rounded bg-[var(--color-scopic)] px-4 py-2 text-sm font-semibold text-white"
      >
        Retry
      </button>
    </main>
  );
}
