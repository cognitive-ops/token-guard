import type { LabelledValue } from "@/lib/prometheus/reduce";

/**
 * The cost-model join — the single clearest reason to own a view layer.
 *
 * In Grafana, "real cost per developer" and "extra usage per developer" are two
 * separate table panels, because joining two metrics on a shared label and
 * adding a derived column is awkward in PromQL/transformations. Here it's a few
 * lines of pure, tested TypeScript: one table, one source of truth for the math.
 *
 * Pure function (no I/O) so it can be unit-tested with fixture rows.
 */

export interface DeveloperCostRow {
  email: string;
  /** Flat seat fee + any metered overage (claude_dev_real_cost_usd). */
  realCost: number;
  /** Metered overage only (claude_dev_extra_usage_usd); 0 when within plan. */
  extraUsage: number;
  /** realCost - extraUsage: the portion covered by the flat seat fee. */
  seatFee: number;
}

/**
 * Join real-cost rows with extra-usage rows on developer email.
 *
 * @param realCost  rows from `claude_dev_real_cost_usd` (label = email)
 * @param extraUsage rows from `claude_dev_extra_usage_usd` (label = email)
 */
export function joinDeveloperCosts(
  realCost: LabelledValue[],
  extraUsage: LabelledValue[],
): DeveloperCostRow[] {
  const extraByEmail = new Map(extraUsage.map((r) => [r.label, r.value]));

  return realCost
    .map((r) => {
      const extra = extraByEmail.get(r.label) ?? 0;
      return {
        email: r.label,
        realCost: r.value,
        extraUsage: extra,
        // Seat fee is whatever real cost isn't overage; never report negative.
        seatFee: Math.max(0, r.value - extra),
      };
    })
    .sort((a, b) => b.realCost - a.realCost);
}

/** Org-level totals derived from the per-developer rows. */
export function summariseDeveloperCosts(rows: DeveloperCostRow[]) {
  return rows.reduce(
    (acc, r) => ({
      totalReal: acc.totalReal + r.realCost,
      totalSeatFees: acc.totalSeatFees + r.seatFee,
      totalExtraUsage: acc.totalExtraUsage + r.extraUsage,
      developersWithOverage:
        acc.developersWithOverage + (r.extraUsage > 0 ? 1 : 0),
    }),
    { totalReal: 0, totalSeatFees: 0, totalExtraUsage: 0, developersWithOverage: 0 },
  );
}
