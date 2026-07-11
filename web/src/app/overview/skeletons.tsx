/** Suspense fallbacks — hold layout so streaming sections don't shift content. */

function Block({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-[var(--color-panel)] ${className}`} />;
}

export function KpiSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Block key={i} className="h-24" />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Block key={i} className="h-16" />
        ))}
      </div>
    </div>
  );
}

export function PanelSkeleton({ height = "h-80" }: { height?: string }) {
  return <Block className={height} />;
}

export function GridSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        <Block key={i} className="h-72" />
      ))}
    </div>
  );
}
