import "server-only";
import { cached, rangeFromToken, promByLabel } from "./common";

/**
 * Distinct developer emails seen in the last 30 days, for the Developer page's
 * user picker. Cached under a fixed key (the roster changes slowly).
 */
export const getUserList = () =>
  cached("user-list", "30d", async (): Promise<string[]> => {
    const r = rangeFromToken("30d");
    // increase() over the window is robust to the coarse reduce-step (a bare
    // selector can fall in a gap on sparse/historical data); any user with usage
    // appears.
    const rows = await promByLabel(
      "userList",
      "sum by (user_email)(increase(claude_code_cost_usage_USD_total[2592000s]))",
      "user_email",
      r,
    );
    // promByLabel returns rows sorted by usage desc, so the Developer page
    // defaults to the most-active developer (a fully-populated view), while the
    // picker's search box makes finding anyone else easy.
    return rows.map((x) => x.label).filter(Boolean);
  });
