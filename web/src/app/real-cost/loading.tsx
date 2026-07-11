import { KpiSkeleton } from "./skeletons";

export default function Loading() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 h-8 w-48 animate-pulse rounded bg-[var(--color-panel)]" />
      <KpiSkeleton />
    </main>
  );
}
