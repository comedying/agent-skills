#!/usr/bin/env python3
"""Pre-publish scan for a repo that contains an Agent Skill.

Finds secrets, keys, tokens, PII, machine-specific absolute paths, junk files and
oversized binaries before anything is committed or pushed. Secret values are masked
in the output so the report itself is safe to paste.

Usage:
    python scan_publish_ready.py [PATH ...] [options]

Options:
    --json                 Emit a JSON report instead of text.
    --fail-on {high,medium,low,none}
                           Exit non-zero when a finding at this level or above is
                           present. Default: high.
    --max-file-mb N        Flag files larger than N MB, and skip reading their
                           contents. Default: 5. Files over the limit are reported
                           as content-not-scanned so a clean report never hides
                           a file that was never read.
    --exclude GLOB         Skip paths matching a glob (repeatable). A glob that
                           matches a directory prunes that whole directory, so
                           both `--exclude scratch` and `--exclude scratch/*` work.
    -q, --quiet            Print counts only (text mode).

Exit codes:
    0  no finding at or above the --fail-on level
    1  findings at or above that level
    2  usage / path error

No network access, no writes, no interactive prompts. Standard library only.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover - older streams
    pass

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}

SKIP_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".cache",
    ".next", ".nuxt", ".output", "dist", "build", "target",
    ".idea", ".vs", ".gradle", ".terraform",
}

JUNK_FILE_PATTERNS = (
    "Thumbs.db", ".DS_Store", "desktop.ini",
    "*.tmp", "*.temp", "*.log", "*.bak", "*.orig", "*.rej",
    "*.swp", "*.swo", "*~", "~$*", "*.pyc", "*.pyo",
)

SECRET_FILENAMES = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa", "id_ed25519")

# (severity, rule, compiled regex, mask?)
CONTENT_RULES = [
    ("high", "private-key-block",
     re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"), True),
    ("high", "aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), True),
    ("high", "github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), True),
    ("high", "github-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"), True),
    ("high", "openai-key", re.compile(r"\bsk-(?!ant-)[A-Za-z0-9_\-]{20,}\b"), True),
    ("high", "anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"), True),
    ("high", "google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), True),
    ("high", "slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b"), True),
    ("high", "stripe-live-key", re.compile(r"\b[rs]k_live_[0-9a-zA-Z]{20,}\b"), True),
    ("high", "npm-token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"), True),
    ("high", "gitlab-pat", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20}\b"), True),
    ("high", "huggingface-token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"), True),
    ("high", "jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"), True),
    # These two deliberately do NOT carry a `[\w.\-]*` prefix. It added nothing
    # (a zero-length prefix matches anywhere the keyword does, and only group 1 is
    # ever read) but cost O(n^2): on a single 8 KB line it burned ~3 s, and the
    # 2 MB content cap did not save any real file - minified JS or a one-line JSON
    # dump blew up long before that. Verified equivalent to the old form over
    # 60k randomized inputs plus handcrafted edge cases.
    ("medium", "generic-secret-assignment",
     re.compile(
         r"(?i)(?:api[_-]?key|apikey|secret|client[_-]?secret|access[_-]?token|"
         r"auth[_-]?token|refresh[_-]?token|token|password|passwd|pwd)\b"
         r"\s*[:=]\s*[\"']([^\"'\n]{8,})[\"']"
     ), True),
    ("medium", "generic-secret-unquoted",
     re.compile(
         r"(?i)(?:api[_-]?key|apikey|secret|access[_-]?token|auth[_-]?token|"
         r"refresh[_-]?token|bearer[_-]?token|token|password|passwd|pwd)\b"
         r"\s*[:=]\s*([^\s\"'#]{8,})"
     ), True),
    ("medium", "bearer-token",
     re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]{20,}=*"), True),
    # The separator before the profile folder is optional because `[A-Za-z]:\\` has
    # already consumed the one right after the drive, so a required `\Users\` could
    # never match the first segment - i.e. it missed <drive>:\Users\<name>, the most
    # common shape of a leaked path, and only fired on deeper ones. The prefix is
    # bounded to keep the scan linear. (Written as `<drive>:` on purpose: a literal
    # example here would itself trip this rule and redden the repo's own gate.)
    ("medium", "windows-user-path",
     re.compile(r"[A-Za-z]:\\[^\n\"'<>|]{0,512}"
                r"(?:\\?(?:Users|AppData|Documents|Desktop|Downloads|OneDrive)\\)"
                r"[^\n\"'<>|]*"), False),
    ("medium", "unix-home-path",
     re.compile(r"(?<![\w.])/(?:home|Users)/[A-Za-z0-9._-]+/"), False),
    # Local part and domain are bounded to the RFC 5321 lengths. Unbounded `+`
    # quantifiers made this O(n^2) on a long dot-separated run (~100 s per 256 KB
    # of "a.a.a..."), and no real address exceeds these limits.
    ("medium", "email-address",
     re.compile(r"\b[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,253}\.[A-Za-z]{2,}\b"), False),
    ("medium", "cn-mobile-number", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), False),
    ("medium", "cn-id-number", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), False),
]

GENERIC_SECRET_RULES = {"generic-secret-assignment", "generic-secret-unquoted"}

BLOCKED_EMAIL_DOMAINS = (".invalid",)
ALLOWED_EMAIL_DOMAINS = (
    "example.com", "example.org", "example.net", "example.edu",
    "test.com", "localhost.com", "domain.com", "your-domain.com",
)
PLACEHOLDER_VALUES = {
    "", "none", "null", "true", "false", "changeme", "your_api_key",
    "your_token", "your_secret", "placeholder", "todo", "fixme", "dummy",
}


def mask(value: str) -> str:
    value = value.strip()
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}...{value[-2:]} (masked)"


def is_placeholder(value: str) -> bool:
    raw = value.strip()
    low = raw.lower()
    if low in PLACEHOLDER_VALUES:
        return True
    if re.fullmatch(r"[<\[{].*[>\]}]", raw):          # <YOUR_KEY>, ${TOKEN}
        return True
    if re.fullmatch(r"[*xX.\-_]{3,}", raw):            # ***, xxx, ...
        return True
    if raw.startswith(("$", "%")):
        return True
    return any(w in low for w in ("example", "placeholder", "changeme", "dummy",
                                  "redacted", "sample", "your_", "my_", "todo"))


def is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return b"\x00" in fh.read(8192)
    except OSError:
        return True


def add(finding_list, severity, rule, rel, line, preview):
    finding_list.append({
        "severity": severity, "rule": rule, "path": rel,
        "line": line, "preview": preview,
    })


def scan_file(path: Path, rel: str, max_bytes: int, findings: list) -> None:
    try:
        size = path.stat().st_size
    except OSError as exc:
        add(findings, "low", "unreadable", rel, 0, str(exc))
        return

    oversized = size > max_bytes
    if oversized:
        add(findings, "low", "large-file", rel, 0,
            f"{size / 1024 / 1024:.1f} MB > {max_bytes / 1024 / 1024:.1f} MB")
        # A file we never read must never look clean. Report the gap rather than
        # returning silently, or a secret in a 2-5 MB file ships unnoticed.
        add(findings, "medium", "content-not-scanned", rel, 0,
            f"contents were NOT scanned: {size / 1024 / 1024:.1f} MB exceeds the "
            f"{max_bytes / 1024 / 1024:.1f} MB --max-file-mb limit")

    name = path.name
    if any(fnmatch.fnmatch(name, pat) for pat in SECRET_FILENAMES):
        add(findings, "high", "secret-file", rel, 0, f"sensitive filename: {name}")
    elif any(fnmatch.fnmatch(name, pat) for pat in JUNK_FILE_PATTERNS):
        add(findings, "low", "junk-file", rel, 0, f"junk filename: {name}")

    if oversized or is_binary(path):
        return

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        add(findings, "low", "unreadable", rel, 0, str(exc))
        return

    for lineno, line in enumerate(text.splitlines(), 1):
        for severity, rule, regex, mask_value in CONTENT_RULES:
            for match in regex.finditer(line):
                if rule in GENERIC_SECRET_RULES:
                    if is_placeholder(match.group(1)):
                        continue
                    preview = mask(match.group(1)) if mask_value else match.group(1)
                elif rule == "email-address":
                    addr = match.group(0)
                    low = addr.lower()
                    if low.endswith(BLOCKED_EMAIL_DOMAINS) or any(
                        low.endswith(f"@{dom}") for dom in ALLOWED_EMAIL_DOMAINS
                    ):
                        continue
                    preview = addr
                else:
                    preview = mask(match.group(0)) if mask_value else match.group(0)
                add(findings, severity, rule, rel, lineno, preview.strip())


def iter_files(root: Path, excludes: list):
    def excluded(rel_path: str) -> bool:
        return any(fnmatch.fnmatch(rel_path, pat) for pat in excludes)

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        # Match an --exclude glob against a directory's relative path AND its bare
        # name, so `--exclude scratch` prunes the tree instead of silently doing
        # nothing (only `scratch/*` used to work).
        kept = []
        for dname in dirnames:
            full_dir = Path(dirpath) / dname
            try:
                rel_dir = full_dir.relative_to(root).as_posix()
            except ValueError:
                rel_dir = full_dir.as_posix()
            if excluded(rel_dir) or excluded(dname):
                continue
            kept.append(dname)
        dirnames[:] = kept

        for fname in filenames:
            full = Path(dirpath) / fname
            try:
                rel = full.relative_to(root).as_posix()
            except ValueError:
                rel = full.as_posix()
            if excluded(rel):
                continue
            yield full, rel


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan a repo for anything that should not be published.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("paths", nargs="*", default=["."],
                        help="Files or directories to scan (default: current directory)")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--fail-on", choices=["high", "medium", "low", "none"],
                        default="high", help="Exit non-zero at this level or above")
    parser.add_argument("--max-file-mb", type=float, default=5.0,
                        help="Flag files larger than this, and skip reading their contents "
                             "(default: 5)")
    parser.add_argument("--exclude", action="append", default=[],
                        help="Skip paths matching a glob (repeatable)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Counts only")
    args = parser.parse_args(argv)

    roots = [Path(p) for p in args.paths]
    for r in roots:
        if not r.exists():
            print(f"error: path does not exist: {r}", file=sys.stderr)
            return 2

    max_bytes = int(args.max_file_mb * 1024 * 1024)
    findings: list = []
    file_count = 0

    for root in roots:
        base = root if root.is_dir() else root.parent
        if root.is_file():
            file_count += 1
            scan_file(root, root.name, max_bytes, findings)
        else:
            # Path('.').name is '' - prefixing blindly turned every finding into
            # '/k.pem', which reads as an absolute path and loses the root.
            prefix = base.name
            for full, rel in iter_files(root, args.exclude):
                file_count += 1
                scan_file(full, f"{prefix}/{rel}" if prefix else rel, max_bytes, findings)

    findings.sort(key=lambda f: (-SEVERITY_RANK[f["severity"]], f["path"], f["line"]))
    counts = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        counts[f["severity"]] += 1

    if args.json:
        json.dump({"root": [str(r) for r in roots], "files_scanned": file_count,
                   "counts": counts, "findings": findings},
                  sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"scanned {file_count} file(s) under: " + ", ".join(str(r) for r in roots))
        print(f"findings: HIGH={counts['high']}  MEDIUM={counts['medium']}  LOW={counts['low']}")
        if not args.quiet:
            for severity in ("high", "medium", "low"):
                group = [f for f in findings if f["severity"] == severity]
                if not group:
                    continue
                print(f"\n[{severity.upper()}]")
                for f in group:
                    loc = f["path"] + (f":{f['line']}" if f["line"] else "")
                    print(f"  {loc}  [{f['rule']}]  {f['preview']}")
        if counts["high"]:
            print("\nHIGH findings must be resolved before publishing.")

    threshold = args.fail_on
    if threshold == "none":
        return 0
    limit = SEVERITY_RANK[threshold]
    return 1 if any(SEVERITY_RANK[f["severity"]] >= limit for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
