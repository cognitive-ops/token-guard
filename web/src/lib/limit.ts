/**
 * Tiny async concurrency limiter. Dashboards fan out many datasource queries at
 * once; without a cap, a page can fire ~15 simultaneous 30-day scans and
 * saturate Loki/Prometheus, causing some to time out and panels to show
 * "No data". Limiting in-flight queries keeps each one fast and the load smooth.
 */
export function createLimiter(max: number) {
  let active = 0;
  const queue: Array<() => void> = [];

  const release = () => {
    active--;
    queue.shift()?.();
  };

  return function run<T>(fn: () => Promise<T>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const start = () => {
        active++;
        fn().then(resolve, reject).finally(release);
      };
      if (active < max) start();
      else queue.push(start);
    });
  };
}
