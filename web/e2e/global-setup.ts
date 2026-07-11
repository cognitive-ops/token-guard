/**
 * Warms each dashboard once before the suite runs. The dashboards fan out many
 * datasource queries on a cold cache; the first request pays for it, then the
 * 30s/5m cache makes everything fast — exactly like the first real visitor.
 * Without this, whichever test hits a heavy page first can time out.
 */
async function globalSetup() {
  const port = process.env.E2E_PORT ?? "3024";
  const base = `http://localhost:${port}`;
  const routes = [
    "/overview",
    "/real-cost",
    "/real-cost?range=7d", // the range the time-picker test switches to
    "/usage-patterns",
    "/developer",
  ];
  await Promise.all(
    routes.map((r) =>
      fetch(base + r).then((res) => res.text()).catch(() => undefined),
    ),
  );
  // Second pass so any section that lost the first concurrency race is cached.
  await Promise.all(routes.map((r) => fetch(base + r).catch(() => undefined)));
}

export default globalSetup;
