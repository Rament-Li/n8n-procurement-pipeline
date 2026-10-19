#!/usr/bin/env python3
"""Run the procurement email extraction evals against the Anthropic API.

The API key is read from the ANTHROPIC_API_KEY environment variable only. It is never
accepted as an argument, never read from a file, never printed and never written to the
results files. Use --dry-run to see exactly what would be sent without any network call.

Usage (from the repository root):
    python3 evals/run_evals.py --prompt evals/prompts/v1_baseline.txt
    python3 evals/run_evals.py --prompt evals/prompts/v2_explicit_rules.txt --repeat 3
    python3 evals/run_evals.py --prompt evals/prompts/v1_baseline.txt --dry-run
"""
import argparse
import datetime
import json
import re
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scoring  # noqa: E402

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = os.environ.get("EVAL_MODEL", "claude-sonnet-5-5")


def build_user_message(prompt, case):
    """Same layout the n8n 'Classify procurement message' node sends."""
    return (prompt.strip() + "\n\nReceived: " + case["received"] + "\nSubject: " + case["subject"]
            + "\nFrom: " + case["from"] + "\n\nBody:\n" + case["body"])


def safe_error_detail(err):
    """Return ' (type: message)' from the API error body, redacted and truncated. Never the raw body or headers."""
    try:
        body = json.loads(err.read().decode("utf-8"))
        info = body.get("error", {})
        detail = "%s: %s" % (str(info.get("type", ""))[:40], str(info.get("message", ""))[:160])
    except Exception:
        return ""
    detail = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "[redacted]", detail)
    return " (" + detail + ")"


def call_model(api_key, model, user_message):
    payload = json.dumps({"model": model, "max_tokens": 2000,
                          "messages": [{"role": "user", "content": user_message}]}).encode("utf-8")
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    for attempt in range(3):
        request = urllib.request.Request(API_URL, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
            parts = [p.get("text", "") for p in data.get("content", []) if p.get("type") == "text"]
            return "".join(parts), None
        except urllib.error.HTTPError as err:
            if err.code in (429, 500, 529) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            return None, "http_%d%s" % (err.code, safe_error_detail(err))  # never headers; body reduced to type + short message
        except (urllib.error.URLError, TimeoutError):
            if attempt < 2:
                time.sleep(2)
                continue
            return None, "network_error"
    return None, "failed"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompt", required=True, help="path to a prompt file")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--cases", default=os.path.join(HERE, "cases.json"))
    ap.add_argument("--limit", type=int, default=0, help="only run the first N cases")
    ap.add_argument("--repeat", type=int, default=1, help="run each case N times (outputs vary between runs)")
    ap.add_argument("--dry-run", action="store_true", help="print the first request and exit, no network")
    args = ap.parse_args()

    prompt = open(args.prompt, encoding="utf-8").read()
    cases = json.load(open(args.cases, encoding="utf-8"))
    if args.limit:
        cases = cases[:args.limit]
    name = os.path.splitext(os.path.basename(args.prompt))[0]

    if args.dry_run:
        print("DRY RUN. Model: %s. Cases: %d. No network call, no key needed.\n" % (args.model, len(cases)))
        print(build_user_message(prompt, cases[0]))
        return 0

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ANTHROPIC_API_KEY is not set. Set it in this terminal session only (see evals/README.md).")
        return 2

    records, case_results = [], []
    for case in cases:
        for run in range(args.repeat):
            text, error = call_model(api_key, args.model, build_user_message(prompt, case))
            output = scoring.parse_model_json(text) if text else None
            result = scoring.score_case(output, case["expected"])
            case_results.append(result)
            records.append({"id": case["id"], "tag": case["tag"], "run": run + 1, "error": error,
                            "passed": result["passed"], "fields": result["fields"],
                            "invalid_json": result["invalid_json"], "got": output if output is not None else text,
                            "expected": case["expected"]})
            print("%s run %d: %s" % (case["id"], run + 1, "PASS" if result["passed"] else "FAIL" + (" (" + error + ")" if error else "")))

    summary = scoring.summarise(case_results)
    out = {"meta": {"prompt": os.path.relpath(args.prompt), "model": args.model, "repeat": args.repeat,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
           "summary": summary, "cases": records}
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    path = os.path.join(HERE, "results", name + ".json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    print("\n%s: %d of %d passed (%d invalid JSON)" % (name, summary["passed"], summary["cases"], summary["invalid_json"]))
    for f, v in summary["fields"].items():
        print("  %-11s %d/%d" % (f, v["correct"], v["scored"]))
    print("Saved " + os.path.relpath(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
