#!/usr/bin/env python3
"""Prompt-language exporter.

Reads `user_prompt` events from Loki, detects the natural language of each prompt
with langdetect (pure-Python, offline, free), and exposes per-language /
per-developer counts to Prometheus so Grafana can show prompt-language usage.

langdetect is unreliable on dev prompts: short text, code/paths/identifiers, and
terse English imperatives ("Ok work on X") get confidently mislabelled as random
languages (af, ro, cy, …). Dev prompts are overwhelmingly English; the value of
this metric is surfacing the *genuinely* non-English ones, so we bias hard toward
precision over recall:

  1. strip code/paths/identifiers/URLs before detection (they're language noise);
  2. require a minimum length and a confidence floor (LANG_CONFIDENCE);
  3. trust a NON-English label only when the text actually contains non-ASCII
     letters (diacritics/CJK) — a non-English guess on plain ASCII is almost
     always misdetected English. Real vi/zh/es-with-accents carry non-ASCII;
  4. and only when the text is long enough (NONENGLISH_MIN_CHARS) that the guess
     doesn't hinge on one stray character — a single input-method diacritic
     leaking into an English word ("Regểnate docx") otherwise flips a 12-char
     prompt to a confident foreign language (ro). Real non-English prompts are
     full sentences that clear the floor;
  5. fold whatever is left undetermined into each developer's dominant language
     (UND_FALLBACK).
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests
from langdetect import DetectorFactory, LangDetectException, detect_langs
from prometheus_client import Gauge, start_http_server

DetectorFactory.seed = 0  # deterministic

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("prompt-lang-exporter")

LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "3600"))  # 1h
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "30"))  # Loki retention is 2160h (90d)
MIN_CHARS = int(os.environ.get("MIN_CHARS", "20"))  # min ASCII length below which -> "und"
# Non-ASCII (CJK/diacritic) text is dense; allow a shorter floor for it.
NONASCII_MIN_CHARS = int(os.environ.get("NONASCII_MIN_CHARS", "8"))
# A NON-English label is only trusted on text at least this long: below it a
# single stray non-ASCII char (an input-method diacritic leaking into an English
# word) flips the guess to a random foreign language. Real non-English prompts
# are sentences/paragraphs that clear this; tuned against real prod data so it
# drops the misdetections without losing genuine fr/vi/ru/es usage.
NONENGLISH_MIN_CHARS = int(os.environ.get("NONENGLISH_MIN_CHARS", "25"))
# Minimum detector confidence to accept a language (langdetect over-guesses).
LANG_CONFIDENCE = float(os.environ.get("LANG_CONFIDENCE", "0.90"))
# Resolve a developer's undetermined (short/ambiguous) prompts to their dominant
# detected language instead of leaving them "und". Set to "0" to keep raw "und".
UND_FALLBACK = os.environ.get("UND_FALLBACK", "1") == "1"
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9106"))
PAGE_LIMIT = int(os.environ.get("PAGE_LIMIT", "5000"))  # smaller pages survive a flaky SSM tunnel
LOKI_QUERY = os.environ.get("LOKI_QUERY", '{service_name="claude-code"} | event_name="user_prompt"')
# Candidate JSON keys that may hold the prompt text / the user identity.
TEXT_KEYS = os.environ.get("TEXT_KEYS", "prompt,prompt_text,body,message,content").split(",")
EMAIL_KEYS = os.environ.get("EMAIL_KEYS", "user_email,user.email,email").split(",")

PROMPT_LANG = Gauge(
    "claude_prompt_language_count",
    "Count of user prompts by detected language and developer over the lookback window",
    ["language", "user_email"],
)
PROMPTS_SEEN = Gauge(
    "claude_prompt_language_prompts_total",
    "Total user_prompt events processed in the last poll",
)
LAST_SUCCESS = Gauge(
    "claude_prompt_lang_exporter_last_success_timestamp",
    "Unix timestamp of the last successful poll",
)
SCRAPE_ERRORS = Gauge(
    "claude_prompt_lang_exporter_errors", "1 if the last poll failed, 0 otherwise"
)
# --- Materialized prompt-pattern views (so Grafana reads cheap gauges, not live Loki) ---
PROMPT_COUNT = Gauge(
    "claude_prompt_count", "User prompts over the lookback window, by developer", ["user_email"]
)
PROMPT_LEN_SUM = Gauge(
    "claude_prompt_length_sum",
    "Sum of prompt lengths (chars) over the window, by developer",
    ["user_email"],
)
PROMPT_LEN_MAX = Gauge(
    "claude_prompt_length_max",
    "Longest prompt (chars) over the window, by developer",
    ["user_email"],
)
PROMPT_BY_TERMINAL = Gauge(
    "claude_prompt_count_by_terminal",
    "User prompts over the window, by terminal/IDE",
    ["terminal_type"],
)
PROMPT_BY_OS = Gauge(
    "claude_prompt_count_by_os", "User prompts over the window, by OS", ["os_type"]
)


def _first(d, keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k):
            return d[k]
    return None


def extract(stream_labels, line):
    """Return (text, email) from a Loki log entry, tolerating several shapes.

    Real Claude Code telemetry stores the prompt + user_email as Loki *structured
    metadata* (stream labels); the log line body is just "claude_code.user_prompt".
    Older/seed data instead puts them in a JSON log line. Check structured metadata
    first, then fall back to the line body.
    """
    text = _first(stream_labels, TEXT_KEYS)
    email = _first(stream_labels, EMAIL_KEYS)
    if not text:
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                text = _first(obj, TEXT_KEYS)
                # OTEL log bodies are sometimes nested under "body" as a dict/string
                if isinstance(text, dict):
                    text = text.get("stringValue") or text.get("value")
                email = email or _first(obj, EMAIL_KEYS)
                # attributes sub-object
                attrs = obj.get("attributes") or {}
                if isinstance(attrs, dict):
                    text = text or _first(attrs, TEXT_KEYS)
                    email = email or _first(attrs, EMAIL_KEYS)
        except (ValueError, TypeError):
            pass
    if not text:
        # not JSON and no structured field -> treat the raw line as the prompt,
        # but never the bare OTEL event-name body.
        text = (
            line
            if line and not line.startswith("{") and not line.startswith("claude_code.")
            else None
        )
    return (text or "").strip(), (email or "unknown")


# Strip language-noise: fenced/inline code, file paths, URLs, and code
# identifiers (camelCase / snake_case), which langdetect reads as foreign text.
def _strip_code(t):
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"`[^`]*`", " ", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"\S*[/\\]\S*", " ", t)
    t = re.sub(r"[A-Za-z]+[_A-Z]\w*", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _has_nonascii_letter(s):
    return any(ord(c) >= 128 and c.isalpha() for c in s)


def classify(text):
    s = _strip_code(text)
    nonascii = _has_nonascii_letter(s)
    if len(s) < (NONASCII_MIN_CHARS if nonascii else MIN_CHARS):
        return "und"
    try:
        langs = detect_langs(s)
    except LangDetectException:
        return "und"
    if not langs or langs[0].prob < LANG_CONFIDENCE:
        return "und"
    lang = langs[0].lang
    # A non-English label needs more evidence than English, which langdetect
    # over-guesses on short/odd dev prompts. Fold back via UND_FALLBACK when the
    # text has no non-ASCII letters (a misdetected English imperative) OR is too
    # short for the guess to rest on more than a single stray diacritic.
    if lang != "en" and (not nonascii or len(s) < NONENGLISH_MIN_CHARS):
        return "und"
    return lang


def poll_once(session):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_DAYS)
    counts = {}
    pcount, plen_sum, pterm, pos, pmax = {}, {}, {}, {}, {}
    total = 0
    next_start_ns = int(start.timestamp() * 1e9)
    end_ns = int(end.timestamp() * 1e9)
    while True:
        r = session.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={
                "query": LOKI_QUERY,
                "start": str(next_start_ns),
                "end": str(end_ns),
                "limit": str(PAGE_LIMIT),
                "direction": "forward",
            },
            timeout=290,
        )
        r.raise_for_status()
        result = r.json().get("data", {}).get("result", [])
        max_ts = next_start_ns
        n = 0
        for stream in result:
            labels = stream.get("stream", {})
            for ts, line in stream.get("values", []):
                n += 1
                total += 1
                ts = int(ts)
                if ts > max_ts:
                    max_ts = ts
                text, email = extract(labels, line)
                lang = classify(text)
                counts[(lang, email)] = counts.get((lang, email), 0) + 1
                pcount[email] = pcount.get(email, 0) + 1
                try:
                    plen = float(labels.get("prompt_length") or len(text))
                except (TypeError, ValueError):
                    plen = float(len(text))
                plen_sum[email] = plen_sum.get(email, 0.0) + plen
                if plen > pmax.get(email, 0.0):
                    pmax[email] = plen
                term = labels.get("terminal_type") or "unknown"
                pterm[term] = pterm.get(term, 0) + 1
                osn = labels.get("os_type") or "unknown"
                pos[osn] = pos.get(osn, 0) + 1
        if n < PAGE_LIMIT or max_ts <= next_start_ns:
            break
        next_start_ns = max_ts + 1  # paginate forward past the last entry

    # Resolve 'und' (short/ambiguous prompts) to each developer's dominant detected
    # language — a dev's "ok"/"continue" is in the language they actually work in.
    if UND_FALLBACK:
        by_user = {}
        for (lang, email), c in counts.items():
            d = by_user.setdefault(email, {})
            d[lang] = d.get(lang, 0) + c
        counts = {}
        for email, lc in by_user.items():
            und = lc.pop("und", 0)
            if lc:  # user has at least one detectable prompt -> fold und into dominant
                dom = max(lc, key=lc.get)
                lc[dom] = lc.get(dom, 0) + und
            elif und:  # nothing detectable for this user -> keep und
                lc["und"] = und
            for lang, c in lc.items():
                counts[(lang, email)] = c

    PROMPT_LANG.clear()
    for (lang, email), c in counts.items():
        PROMPT_LANG.labels(language=lang, user_email=email).set(c)
    for g in (PROMPT_COUNT, PROMPT_LEN_SUM, PROMPT_LEN_MAX, PROMPT_BY_TERMINAL, PROMPT_BY_OS):
        g.clear()
    for email, c in pcount.items():
        PROMPT_COUNT.labels(user_email=email).set(c)
    for email, s in plen_sum.items():
        PROMPT_LEN_SUM.labels(user_email=email).set(s)
    for email, m in pmax.items():
        PROMPT_LEN_MAX.labels(user_email=email).set(m)
    for t, c in pterm.items():
        PROMPT_BY_TERMINAL.labels(terminal_type=t).set(c)
    for o, c in pos.items():
        PROMPT_BY_OS.labels(os_type=o).set(c)
    PROMPTS_SEEN.set(total)
    langs = {}
    for (lang, _), c in counts.items():
        langs[lang] = langs.get(lang, 0) + c
    log.info(
        "poll ok: %d prompts, languages=%s", total, dict(sorted(langs.items(), key=lambda x: -x[1]))
    )


def main():
    log.info(
        "prompt-lang-exporter on :%d (Loki=%s, lookback %dd, poll %ds)",
        LISTEN_PORT,
        LOKI_URL,
        LOOKBACK_DAYS,
        POLL_INTERVAL,
    )
    start_http_server(LISTEN_PORT)
    session = requests.Session()
    # Retry transient connection drops (e.g. an SSM tunnel/relay resetting the
    # connection under load). On production Loki there's no tunnel, but this keeps
    # polls resilient either way.
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session.mount(
        "http://",
        HTTPAdapter(max_retries=Retry(total=5, connect=5, read=5, backoff_factor=1.5)),
    )
    while True:
        try:
            poll_once(session)
            LAST_SUCCESS.set(time.time())
            SCRAPE_ERRORS.set(0)
        except Exception as e:  # noqa: BLE001
            SCRAPE_ERRORS.set(1)
            log.exception("poll failed: %s", e)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
