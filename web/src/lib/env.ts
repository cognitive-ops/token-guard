import "server-only";
import { z } from "zod";

/**
 * Server-side environment configuration.
 *
 * This module is `server-only`: importing it from a client component is a build
 * error. That guarantees datasource URLs (and, in a real deployment, any
 * credentials/tokens) never reach the browser bundle — the same isolation
 * Grafana gives you for free with `access: proxy` datasources.
 */
const EnvSchema = z.object({
  /** Prometheus HTTP API base, e.g. http://prometheus:9090 (in-cluster) or http://localhost:9090. */
  PROMETHEUS_URL: z.string().url().default("http://localhost:9090"),
  /** Loki HTTP API base, e.g. http://loki:3100. */
  LOKI_URL: z.string().url().default("http://localhost:3100"),
  /** Default lookback window for dashboards, in days. */
  DEFAULT_RANGE_DAYS: z.coerce.number().int().positive().max(365).default(30),
  /** Per-request timeout against the datasources, in milliseconds. */
  QUERY_TIMEOUT_MS: z.coerce.number().int().positive().default(15_000),
  /**
   * Cache TTL for query results, in seconds (cross-request + fetch revalidation).
   * Analytics tolerate staleness — the billing-exporter only refreshes every 6h
   * and OTEL rollups move slowly — so we default to 5 minutes to serve most
   * requests from cache (one datasource round-trip per window per 5 min).
   */
  REVALIDATE_SECONDS: z.coerce.number().int().nonnegative().default(300),

  /**
   * Anthropic Admin API key (sk-ant-admin…) for the API Cost dashboard. Provide
   * the key inline via ADMIN_KEY, or a file path via ADMIN_KEY_PATH (mounted
   * like the billing-exporter). Server-only; never sent to the browser. If
   * neither is set, the /api-cost dashboard reports "not configured".
   */
  ADMIN_KEY: z.string().optional(),
  ADMIN_KEY_PATH: z.string().optional(),
});

const parsed = EnvSchema.safeParse(process.env);

if (!parsed.success) {
  // Fail loud at boot rather than surfacing cryptic fetch errors later.
  throw new Error(
    `Invalid environment configuration:\n${parsed.error.toString()}`,
  );
}

export const env = parsed.data;
