#!/usr/bin/env python3
"""Scan the repository for anything that looks like a credential.

Checks every file Git would commit or has already tracked (ignored files are skipped).
Prints the file, the line number and the kind of match, never the matched text.
Exit code 1 if anything is found, so it can block a push or fail a CI run.
Works offline and uses only the standard library.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PATTERNS = {
    "Anthropic API key": r"sk-ant-[A-Za-z0-9_\-]{8,}",
    "OpenAI-style key": r"sk-[A-Za-z0-9]{32,}",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{30,}",
    "AWS access key": r"AKIA[0-9A-Z]{16}",
    "x-api-key header with a value": r"""x-api-key["']?\s*[:=]\s*["'][A-Za-z0-9_\-]{20,}["']""",
    "ANTHROPIC_API_KEY assignment with a value": r"""ANTHROPIC_API_KEY\s*=\s*["']?[A-Za-z0-9_\-]{16,}""",
    "Bearer token": r"Bearer\s+[A-Za-z0-9._\-]{30,}",
    "Private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
}
RISKY_NAMES = (".env", ".pem", ".p12", ".pfx", ".key")


def candidate_files(root):
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             cwd=root, capture_output=True, check=True).stdout
        names = [n for n in out.decode("utf-8", "replace").split("\0") if n]
    except (OSError, subprocess.CalledProcessError):
        names = []
        for base, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules")]
            names += [os.path.relpath(os.path.join(base, f), root) for f in files]
    return names


def scan(root=ROOT, extra_text=None):
    """Return a list of (path, line_number, kind). extra_text scans a string instead of the repo."""
    compiled = {k: re.compile(v) for k, v in PATTERNS.items()}
    findings = []
    if extra_text is not None:
        for n, line in enumerate(extra_text.splitlines(), 1):
            findings += [("<text>", n, k) for k, rx in compiled.items() if rx.search(line)]
        return findings
    for name in candidate_files(root):
        base = os.path.basename(name).lower()
        if base.startswith(".env") or base.endswith(RISKY_NAMES[1:]):
            findings.append((name, 0, "file name suggests a secret"))
        path = os.path.join(root, name)
        try:
            if os.path.getsize(path) > 5_000_000:
                continue
            with open(path, "r", encoding="utf-8", errors="strict") as fh:
                for n, line in enumerate(fh, 1):
                    findings += [(name, n, k) for k, rx in compiled.items() if rx.search(line)]
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable
    return findings


def main():
    findings = scan()
    if not findings:
        print("No credentials found.")
        return 0
    print("Possible credentials found (matched text is not shown):")
    for path, line, kind in findings:
        print("  %s:%s  %s" % (path, line or "-", kind))
    return 1


if __name__ == "__main__":
    sys.exit(main())
