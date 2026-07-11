#!/usr/bin/env python3
"""Seed the LOCAL stack with synthetic demo data so the dashboards light up.

NOT for production — local testing/demo only. Emits:
  - claude_code.* OTLP metrics  -> OTEL collector -> Prometheus  (Working dashboard)
  - user_prompt log events       -> Loki (service_name=claude-code)  (prompt-language)
  - hook events (prompt/commit/pr/git_commit) -> Loki  (Engineering dashboard)

Env: OTLP_ENDPOINT (http://localhost:4318), OTEL_TOKEN (localtest), LOKI_URL (http://localhost:3100)
"""

import json
import os
import random
import time
import urllib.request

random.seed(7)
OTLP = os.environ.get("OTLP_ENDPOINT", "http://localhost:4318")
TOKEN = os.environ.get("OTEL_TOKEN", "localtest")
LOKI = os.environ.get("LOKI_URL", "http://localhost:3100")

USERS = [
    ("viet-anh.n@scopicsoftware.com", "vscode"),
    ("alex.t@scopicsoftware.com", "iTerm.app"),
    ("maria.g@scopicsoftware.com", "vscode"),
    ("ci-bot@scopicsoftware.com", "non-interactive"),
]
MODELS = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]
PROJECTS = ["roi-analytics", "mobile-app", "data-pipeline"]
REPOS = [
    ("scopic-software/claude-code-roi-analytics", "gitea"),
    ("scopic-software/mobile-app", "github.com"),
]
PROMPTS = {  # language -> sample prompts
    "en": [
        "Refactor the auth middleware and add unit tests",
        "Why is the build failing on CI for the payment module",
        "Add pagination to the users API endpoint",
    ],
    "es": ["Refactoriza el middleware de autenticación y añade pruebas"],
    "vi": ["Sửa lỗi đăng nhập và thêm kiểm thử cho middleware xác thực"],
    "fr": ["Corrige la fuite mémoire dans le service de cache"],
}


# ---------- OTEL metrics ----------
def seed_metrics():
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    exp = OTLPMetricExporter(
        endpoint=f"{OTLP}/v1/metrics", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    reader = PeriodicExportingMetricReader(exp, export_interval_millis=600000)
    mp = MeterProvider(metric_readers=[reader])
    m = mp.get_meter("seed")
    cost = m.create_counter("claude_code.cost.usage", unit="USD")
    tok = m.create_counter("claude_code.token.usage", unit="tokens")
    loc = m.create_counter("claude_code.lines_of_code.count")
    pr = m.create_counter("claude_code.pull_request.count")
    commit = m.create_counter("claude_code.commit.count")
    sess = m.create_counter("claude_code.session.count")

    for email, term in USERS:
        repo, host = random.choice(REPOS)
        base = {
            "user_email": email,
            "terminal_type": term,
            "repository_fullname": repo,
            "repository_host": host,
        }
        for _ in range(random.randint(8, 25)):
            model = random.choice(MODELS)
            proj = random.choice(PROJECTS)
            a = {**base, "model": model, "project_name": proj}
            cost.add(round(random.uniform(0.05, 4.0), 4), a)
            tok.add(random.randint(200, 5000), {**a, "type": "input"})
            tok.add(random.randint(500, 9000), {**a, "type": "output"})
            tok.add(random.randint(5000, 90000), {**a, "type": "cacheRead"})
            tok.add(random.randint(1000, 20000), {**a, "type": "cacheCreation"})
            sess.add(1, {"user_email": email})
        loc.add(random.randint(50, 1200), {"user_email": email, "type": "added"})
        loc.add(random.randint(10, 400), {"user_email": email, "type": "modified"})
        loc.add(random.randint(5, 300), {"user_email": email, "type": "deleted"})
        pr.add(random.randint(0, 6), {"user_email": email})
        commit.add(random.randint(2, 20), {"user_email": email})

    mp.force_flush(timeout_millis=10000)
    mp.shutdown()
    print("  OTEL metrics flushed to", OTLP)


def seed_metrics_live(duration=180, step=12):
    """Emit GROWING counters over `duration` seconds so Prometheus increase()/rate()
    queries (what the dashboards use) actually show data. A one-shot static counter
    yields increase()==0; this produces real growth the dashboards can chart."""
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    exp = OTLPMetricExporter(
        endpoint=f"{OTLP}/v1/metrics", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    reader = PeriodicExportingMetricReader(exp, export_interval_millis=step * 1000)
    mp = MeterProvider(metric_readers=[reader])
    m = mp.get_meter("seed-live")
    cost = m.create_counter("claude_code.cost.usage", unit="USD")
    tok = m.create_counter("claude_code.token.usage", unit="tokens")
    loc = m.create_counter("claude_code.lines_of_code.count")
    pr = m.create_counter("claude_code.pull_request.count")
    commit = m.create_counter("claude_code.commit.count")
    sess = m.create_counter("claude_code.session.count")
    end = time.time() + duration
    rounds = 0
    while time.time() < end:
        for email, term in USERS:
            repo, host = random.choice(REPOS)
            model = random.choice(MODELS)
            proj = random.choice(PROJECTS)
            a = {
                "user_email": email,
                "terminal_type": term,
                "repository_fullname": repo,
                "repository_host": host,
                "model": model,
                "project_name": proj,
            }
            cost.add(round(random.uniform(0.02, 0.6), 4), a)
            tok.add(random.randint(100, 2000), {**a, "type": "input"})
            tok.add(random.randint(200, 4000), {**a, "type": "output"})
            tok.add(random.randint(2000, 40000), {**a, "type": "cacheRead"})
            tok.add(random.randint(500, 8000), {**a, "type": "cacheCreation"})
            loc.add(random.randint(5, 120), {"user_email": email, "type": "added"})
            loc.add(random.randint(1, 40), {"user_email": email, "type": "modified"})
            loc.add(random.randint(0, 30), {"user_email": email, "type": "deleted"})
            sess.add(1, {"user_email": email})
            if random.random() < 0.3:
                pr.add(1, {"user_email": email})
            commit.add(random.randint(0, 2), {"user_email": email})
        rounds += 1
        time.sleep(step)
    mp.shutdown()
    print(f"  live metrics: {rounds} growing rounds over ~{duration}s")


# ---------- Loki ----------
_STREAMS = {}  # key -> (stream_dict, [(ts_ns, line)])


def _add(stream, line, ts_ns):
    k = tuple(sorted(stream.items()))
    _STREAMS.setdefault(k, (stream, []))[1].append((ts_ns, line))


def _flush_loki():
    total = 0
    for stream, vals in _STREAMS.values():
        vals.sort()  # Loki requires per-stream timestamps in ascending order
        payload = json.dumps(
            {"streams": [{"stream": stream, "values": [[str(t), line] for t, line in vals]}]}
        ).encode()
        req = urllib.request.Request(
            f"{LOKI}/loki/api/v1/push",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=15)
        total += len(vals)
    return total


def seed_loki():
    now = int(time.time())
    g = 0  # global nudge to keep timestamps unique

    # Loki rejects samples older than ~24h, so spread events across the last ~22h.
    def ts(secs_ago, sub):
        nonlocal g
        g += 1
        return (now - secs_ago + sub) * 10**9 + g

    # user_prompt log events (for prompt-language) under service_name=claude-code
    for i in range(40):
        lang = random.choices(list(PROMPTS), weights=[8, 2, 2, 1])[0]
        text = random.choice(PROMPTS[lang])
        email = random.choice(USERS)[0]
        _add(
            {"service_name": "claude-code", "event_name": "user_prompt"},
            json.dumps({"user_email": email, "prompt": text}),
            ts(random.randint(400, 79200), i),
        )
    # hook events: per session -> several prompts, a commit, sometimes a PR
    for s in range(12):
        email, _t = random.choice(USERS)
        sid = f"demo-sess-{s}"
        d = random.randint(400, 79200)
        for p in range(random.randint(2, 8)):
            _add(
                {"service_name": "claude-code-hooks", "event": "prompt"},
                json.dumps({"session_id": sid, "prompt_length": random.randint(20, 400)}),
                ts(d, p),
            )
        for c in range(random.randint(1, 3)):
            sha = f"{random.getrandbits(160):040x}"
            _add(
                {"service_name": "claude-code-hooks", "event": "commit"},
                json.dumps({"session_id": sid, "commit_sha": sha, "repo": "roi-analytics"}),
                ts(d, 100 + c),
            )
            ai = random.random() < 0.7
            _add(
                {"service_name": "claude-code-hooks", "event": "git_commit"},
                json.dumps(
                    {
                        "commit_sha": sha,
                        "author": email,
                        "branch": "main",
                        "repo": "roi-analytics",
                        "session_id": sid if ai else "",
                        "ai_assisted": ai,
                        "lines_added": random.randint(5, 250),
                        "lines_deleted": random.randint(0, 60),
                        "files": random.randint(1, 12),
                    }
                ),
                ts(d, 200 + c),
            )
        if random.random() < 0.5:
            _add(
                {"service_name": "claude-code-hooks", "event": "pr"},
                json.dumps({"session_id": sid, "pr_url": f"https://github.com/o/r/pull/{s}"}),
                ts(d, 300),
            )
    n = _flush_loki()
    print(f"  Loki: pushed {n} events to {LOKI}")


if __name__ == "__main__":
    import sys

    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which == "live":
        seed_loki()
        seed_metrics_live(int(sys.argv[2]) if len(sys.argv) > 2 else 180)
    else:
        if which in ("all", "metrics"):
            seed_metrics()
        if which in ("all", "loki"):
            seed_loki()
    print("done.")
