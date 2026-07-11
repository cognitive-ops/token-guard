function Block({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-[var(--color-panel)] ${className}`} />;
}

export function KpiSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
      {Array.from({ length: 5 }).map((_, i) => (
        <Block key={i} className="h-24" />
      ))}
    </div>
  );
}

export function PanelSkeleton({ height = "h-80" }: { height?: string }) {
  return <Block className={height} />;
}
