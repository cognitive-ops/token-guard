#!/usr/bin/env python3
"""Stage 3 (scrub): drop any prompt containing a secret, via gitleaks.

Input : data/interim/clean.jsonl   (may contain secrets)
Output: data/processed/labelable.jsonl              (SECRET-FREE - safe for a DVC remote)
        data/processed/secret_quarantine_ids.txt    (prompt_ids only - audit trail, no secrets)

Each row's prompt AND its prior_prompts context are written to one file in a
private temp dir, scanned with `gitleaks dir --redact`, and any row with a
finding is removed. Context is scanned because it is shipped in the output: a
secret pasted in an earlier prompt rides along in later rows' prior_prompts, so
scanning only `prompt` would leak it. The temp dir (which holds the raw secret
text) is always deleted. Requires gitleaks on PATH.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

IN = os.environ.get("CLEAN_IN", "data/interim/clean.jsonl")
OUT = os.environ.get("LABELABLE_OUT", "data/processed/labelable.jsonl")
QUAR = os.environ.get("QUAR_OUT", "data/processed/secret_quarantine_ids.txt")


def main():
    if not shutil.which("gitleaks"):
        sys.exit("ERROR: gitleaks not on PATH — install it (https://github.com/gitleaks/gitleaks)")
    rows = [json.loads(l) for l in open(IN)]

    work = tempfile.mkdtemp(prefix="scrub_")
    scan = os.path.join(work, "scan")
    os.makedirs(scan)
    report = os.path.join(work, "report.json")  # kept OUT of the scanned dir
    try:
        for i, it in enumerate(rows):
            # Scan the prompt AND its context — prior_prompts ships in the output,
            # so a secret in earlier-turn text must flag (and drop) the row too.
            texts = [it.get("prompt") or "", *(it.get("prior_prompts") or [])]
            with open(os.path.join(scan, f"{i}.txt"), "w") as f:
                f.write("\n".join(texts))
        subprocess.run(
            [
                "gitleaks",
                "dir",
                scan,
                "--report-format",
                "json",
                "--report-path",
                report,
                "--redact",
                "--no-banner",
                "--exit-code",
                "0",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        findings = json.load(open(report)) if os.path.getsize(report) else []
        flagged = {
            int(os.path.basename(f["File"])[:-4])
            for f in findings
            if str(f.get("File", "")).endswith(".txt")
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)  # deletes files holding raw secrets

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    kept = [it for i, it in enumerate(rows) if i not in flagged]
    with open(OUT, "w") as f:
        for it in kept:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    with open(QUAR, "w") as f:
        f.write("\n".join(rows[i].get("prompt_id", "") for i in sorted(flagged)) + "\n")
    print(f"scanned={len(rows)} secrets_removed={len(flagged)} -> {len(kept)} labelable -> {OUT}")


if __name__ == "__main__":
    main()
