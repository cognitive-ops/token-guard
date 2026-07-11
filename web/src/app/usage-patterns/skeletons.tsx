/** Suspense fallbacks — hold layout so streaming sections don't shift content. */

function Block({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-[var(--color-panel)] ${className}`} />;
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
