import type { ReactNode } from "react";
import { InfoButton } from "@/components/info-button";
import type { MetricDoc } from "@/lib/metric-docs";

/** A panel container matching a polished Grafana panel. Optional (i) metric doc. */
export function Panel({
  title,
  subtitle,
  info,
  action,
  children,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  info?: MetricDoc;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel panel-hover p-5 ${className}`}>
      {title && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-1.5">
              <h2 className="text-sm font-semibold text-[var(--color-text)]">{title}</h2>
              {info && <InfoButton doc={info} />}
            </div>
            {subtitle && (
              <p className="mt-0.5 text-xs text-[var(--color-muted)]">{subtitle}</p>
            )}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

/** A blue-accented section divider/heading. */
export function SectionHeading({
  title,
  hint,
  info,
}: {
  title: string;
  hint?: string;
  info?: MetricDoc;
}) {
  return (
    <div className="mb-4 mt-8 flex items-baseline gap-3">
      <div className="flex items-center gap-1.5">
        <h2 className="text-base font-semibold text-[var(--color-scopic)]">{title}</h2>
        {info && <InfoButton doc={info} />}
      </div>
      {hint && <span className="text-xs text-[var(--color-muted)]">{hint}</span>}
      <span className="accent-rule ml-1 h-[2px] flex-1 self-center rounded-full opacity-70" />
    </div>
  );
}
