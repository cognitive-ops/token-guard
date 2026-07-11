import { NextResponse } from "next/server";
import { getApiCost, currentMonth } from "@/lib/data/api-cost";

/**
 * CSV export for Finance: per-client billed cost for a month.
 * GET /api-cost/export?month=YYYY-MM  → text/csv download.
 * (Behind the same auth as the dashboard via middleware.)
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const param = url.searchParams.get("month");
  const month = param && /^\d{4}-\d{2}$/.test(param) ? param : currentMonth();
  const data = await getApiCost(month);

  if (!data.configured) {
    return NextResponse.json({ error: "Admin API key not configured" }, { status: 503 });
  }

  const esc = (s: string) => `"${s.replace(/"/g, '""')}"`;
  const rows = [
    ["workspace", "workspace_id", "cost_usd", "share_pct"],
    ...data.clients.map((c) => [c.client, c.workspaceId, c.cost.toFixed(2), (c.share * 100).toFixed(2)]),
    ["TOTAL", "", data.totalCost.toFixed(2), "100.00"],
  ];
  const csv = rows.map((r) => r.map((v) => esc(String(v))).join(",")).join("\r\n") + "\r\n";

  return new NextResponse(csv, {
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": `attachment; filename="api-cost-${month}.csv"`,
      "cache-control": "no-store",
    },
  });
}
