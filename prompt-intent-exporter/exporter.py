#!/usr/bin/env python3
"""Prompt-intent exporter.

Reads `user_prompt` events from Loki, classifies each developer prompt by INTENT
and BEHAVIOR with a local fine-tuned model (ONNX int8, onnxruntime + tokenizers —
no torch/transformers), and exposes per-intent / per-behavior / per-command counts
to Prometheus for the "Prompt Analysis" dashboard.

Light enough for the analytics box (2 vCPU / ~8 GB RAM): the int8 ONNX model is
~135 MB and inference is ~30 ms/prompt. A per-prompt cache means each poll only
classifies prompts it has not seen before.

Model artifacts (model.int8.onnx, tokenizer.json, meta.json) are mounted at
MODEL_DIR (default /model) — produced by prompt-intent-classifier/src/export_onnx.py.
"""

import json
import logging
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np
import onnxruntime as ort
import requests
from prometheus_client import Gauge, start_http_server
from tokenizers import Tokenizer

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("prompt-intent-exporter")

LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "3600"))
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "29"))  # Loki rejects >30d1h
PAGE_LIMIT = int(os.environ.get("PAGE_LIMIT", "5000"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9107"))
MODEL_DIR = os.environ.get("MODEL_DIR", "/model")
INTENT_THRESHOLD = float(os.environ.get("INTENT_THRESHOLD", "0.0"))  # 0 = no abstain
BEHAVIOR_THRESHOLD = float(os.environ.get("BEHAVIOR_THRESHOLD", "0.5"))
ORT_THREADS = int(os.environ.get("ORT_THREADS", "2"))
LOKI_QUERY = os.environ.get("LOKI_QUERY", '{service_name="claude-code"} | event_name=`user_prompt`')
# Write classifications back to Loki (timestamped at the original prompt time) so the
# dashboard panels honor the Grafana time picker. Disable with WRITE_LOKI=0.
WRITE_LOKI = os.environ.get("WRITE_LOKI", "1") == "1"
PUSH_URL = LOKI_URL.rstrip("/") + "/loki/api/v1/push"
S_INTENT = "claude-code-intent"  # 1 entry/prompt            → {intent, user_email}
S_BEHAVIOR = "claude-code-behavior"  # 1 entry/(prompt,behavior) → {behavior, user_email}
S_COMMAND = "claude-code-command"  # 1 entry/control prompt    → {command, user_email}

# --- metrics (claude_prompt_* namespace, matching prompt-lang-exporter) ---
INTENT = Gauge(
    "claude_prompt_intent_count",
    "User prompts by classified intent and developer",
    ["intent", "user_email"],
)
BEHAVIOR = Gauge(
    "claude_prompt_behavior_count",
    "Behavior-tag occurrences by developer (multi-label)",
    ["behavior", "user_email"],
)
COMMAND = Gauge(
    "claude_prompt_command_count",
    "Slash-command usage by developer (regex, no model)",
    ["command", "user_email"],
)
PROC = Gauge(
    "claude_prompt_intent_prompts_total", "Real prompts classified over the lookback window"
)
LAST_OK = Gauge("claude_prompt_intent_exporter_last_success_timestamp", "Unix ts of last good poll")
ERRORS = Gauge("claude_prompt_intent_exporter_errors", "1 if last poll failed, else 0")

# --- preprocessing (mirrors the classifier's preprocess.py) ---
_INJECTED = (
    "<observed_from_primary_session>",
    "<task-notification>",
    "<system-reminder>",
    "<command-",
)
_CONFIRM = re.compile(
    r"^(y|yes|yep|yeah|ok|okay|sure|no|nope|continue|go|go ahead|do it|proceed|"
    r"next|stop|thanks|thank you|ty|y post|yes post|\d+)\b",
    re.I,
)
_SLASH = re.compile(r"^/([a-zA-Z][\w-]*)")


def categorize(p):
    s = (p or "").strip()
    if not s:
        return "empty"
    if s.startswith(_INJECTED):
        return "injected"
    if re.match(r"^/[a-zA-Z]", s):
        return "control"
    if len(s) < 15 and _CONFIRM.match(s):
        return "control"
    return "real"


# --- model ---
class Model:
    def __init__(self, d):
        self.meta = json.load(open(os.path.join(d, "meta.json")))
        self.tok = Tokenizer.from_file(os.path.join(d, "tokenizer.json"))
        self.tok.enable_truncation(max_length=self.meta["maxlen"])
        so = ort.SessionOptions()
        so.intra_op_num_threads = ORT_THREADS
        name = (
            "model.int8.onnx"
            if os.path.exists(os.path.join(d, "model.int8.onnx"))
            else "model.onnx"
        )
        self.sess = ort.InferenceSession(
            os.path.join(d, name), so, providers=["CPUExecutionProvider"]
        )
        self.has_behaviors = bool(self.meta.get("behaviors"))
        # per-behavior thresholds (tuned) override the global default when present
        self.bthr = self.meta.get("behavior_thresholds", {})
        log.info(
            "loaded model %s (intents=%s, behaviors=%s, thresholds=%s)",
            name,
            self.meta["intents"],
            self.meta.get("behaviors"),
            self.bthr or "default",
        )

    def classify(self, text):
        enc = self.tok.encode(text)
        ids = np.array([enc.ids], dtype=np.int64)
        mask = np.array([enc.attention_mask], dtype=np.int64)
        out = self.sess.run(None, {"input_ids": ids, "attention_mask": mask})
        il = out[0][0]
        e = np.exp(il - il.max())
        p = e / e.sum()
        top = int(p.argmax())
        conf = float(p[top])
        intent = self.meta["intents"][top] if conf >= INTENT_THRESHOLD else "unclassified"
        behaviors = []
        if self.has_behaviors and len(out) > 1:
            bl = out[1][0]
            bp = 1 / (1 + np.exp(-bl))
            behaviors = [
                self.meta["behaviors"][j]
                for j in range(len(self.meta["behaviors"]))
                if bp[j] >= self.bthr.get(self.meta["behaviors"][j], BEHAVIOR_THRESHOLD)
            ]
        return intent, behaviors


def loki_prompts(session, end_ns, start_ns):
    """Yield (labels-dict) for every user_prompt event in the window (paginated)."""
    nxt = start_ns
    while True:
        r = session.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={
                "query": LOKI_QUERY,
                "start": str(nxt),
                "end": str(end_ns),
                "limit": str(PAGE_LIMIT),
                "direction": "forward",
            },
            timeout=290,
        )
        r.raise_for_status()
        result = r.json().get("data", {}).get("result", [])
        page_n, max_ts = 0, nxt
        for stream in result:
            labels = stream.get("stream", {})
            for ts, _line in stream.get("values", []):
                page_n += 1
                ts = int(ts)
                if ts > max_ts:
                    max_ts = ts
                yield ts, labels
        if page_n < PAGE_LIMIT or max_ts <= nxt:
            break
        nxt = max_ts + 1


PUSH_CHUNK = int(os.environ.get("PUSH_CHUNK", "1000"))


def push_loki(session, streams):
    """streams: {service_name: [[ts_ns_str, line, metadata_dict], ...]}. Idempotent —
    deterministic lines let Loki dedupe on re-push. Posts each stream in separate
    requests of PUSH_CHUNK entries (one giant request 400s)."""
    total = 0
    for svc, values in streams.items():
        if not values:
            continue
        values = sorted(values, key=lambda v: int(v[0]))  # per-stream time order
        for i in range(0, len(values), PUSH_CHUNK):
            chunk = values[i : i + PUSH_CHUNK]
            r = session.post(
                PUSH_URL,
                json={"streams": [{"stream": {"service_name": svc}, "values": chunk}]},
                timeout=60,
            )
            r.raise_for_status()
            total += len(chunk)
    return total


def poll_once(session, model, cache, pushed):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_DAYS)
    end_ns, start_ns = int(end.timestamp() * 1e9), int(start.timestamp() * 1e9)

    # collect events, group by session ordered by event_sequence
    by_sess = defaultdict(list)
    for ts, lb in loki_prompts(session, end_ns, start_ns):
        by_sess[lb.get("session_id")].append((ts, lb))

    def seq(item):
        try:
            return int(item[1].get("event_sequence") or 0)
        except (TypeError, ValueError):
            return 0

    icount = defaultdict(lambda: defaultdict(int))  # intent -> email -> n
    bcount = defaultdict(lambda: defaultdict(int))
    ccount = defaultdict(lambda: defaultdict(int))
    total = 0
    streams = {S_INTENT: [], S_BEHAVIOR: [], S_COMMAND: []}  # Loki back-write buffers

    for sid, evs in by_sess.items():
        evs.sort(key=lambda e: (seq(e), e[0]))
        history = []
        for ts, lb in evs:
            text = (lb.get("prompt") or "").strip()
            email = lb.get("user_email") or "unknown"
            cat = categorize(text)
            if cat in ("injected", "empty"):
                continue
            tsr = str(ts)
            pid = lb.get("prompt_id") or f"{sid}:{seq((ts, lb))}:{ts}"
            if cat == "control":
                m = _SLASH.match(text)
                if m:
                    cmd = m.group(1).lower()
                    ccount[cmd][email] += 1
                    if WRITE_LOKI and pid not in pushed:
                        streams[S_COMMAND].append([tsr, pid, {"command": cmd, "user_email": email}])
                history.append(text)
                continue
            # real prompt -> classify (with prior-prompt context for sequence tags)
            prev = history[-1] if history else ""
            if pid in cache:
                intent, behaviors = cache[pid]
            else:
                ctx = (prev + model.meta["sep"] + text) if prev else text
                intent, behaviors = model.classify(ctx)
                cache[pid] = (intent, behaviors)
                if WRITE_LOKI:
                    streams[S_INTENT].append([tsr, pid, {"intent": intent, "user_email": email}])
                    for b in behaviors:
                        streams[S_BEHAVIOR].append(
                            [tsr, f"{pid}:{b}", {"behavior": b, "user_email": email}]
                        )
            icount[intent][email] += 1
            for b in behaviors:
                bcount[b][email] += 1
            total += 1
            history.append(text)

    if WRITE_LOKI:
        pushed_n = push_loki(session, streams)
        for v in streams[S_COMMAND]:
            pushed.add(v[1])
        if pushed_n:
            log.info("wrote %d classified events back to Loki (intent/behavior/command)", pushed_n)

    INTENT.clear()
    BEHAVIOR.clear()
    COMMAND.clear()
    for intent, by in icount.items():
        for email, n in by.items():
            INTENT.labels(intent=intent, user_email=email).set(n)
    for b, by in bcount.items():
        for email, n in by.items():
            BEHAVIOR.labels(behavior=b, user_email=email).set(n)
    for c, by in ccount.items():
        for email, n in by.items():
            COMMAND.labels(command=c, user_email=email).set(n)
    PROC.set(total)
    log.info(
        "poll ok: %d real prompts classified (cache=%d), %d commands, %d intents",
        total,
        len(cache),
        sum(len(v) for v in ccount.values()),
        len(icount),
    )


def main():
    log.info(
        "prompt-intent-exporter on :%d (Loki=%s, lookback %dd, poll %ds, model=%s)",
        LISTEN_PORT,
        LOKI_URL,
        LOOKBACK_DAYS,
        POLL_INTERVAL,
        MODEL_DIR,
    )
    start_http_server(LISTEN_PORT)
    model = Model(MODEL_DIR)
    session = requests.Session()
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session.mount(
        "http://", HTTPAdapter(max_retries=Retry(total=5, connect=5, read=5, backoff_factor=1.5))
    )
    cache = {}
    pushed = set()
    while True:
        try:
            poll_once(session, model, cache, pushed)
            LAST_OK.set(time.time())
            ERRORS.set(0)
        except Exception as e:  # noqa: BLE001
            ERRORS.set(1)
            log.exception("poll failed: %s", e)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
