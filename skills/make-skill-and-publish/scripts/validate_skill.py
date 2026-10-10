#!/usr/bin/env python3
"""Deterministic Agent Skills checks that need no network and no GitHub CLI.

Use this when `gh skill publish --dry-run` is unavailable (gh not installed, or the
`gh skill` preview command missing on the host). It checks the mechanical rules only;
it cannot tell you whether the skill makes good decisions.

Usage:
    python validate_skill.py <path> [<path> ...] [--json] [-q]

A path may be a skill directory (contains SKILL.md) or a repo root, in which case
the same layouts `gh skill publish` discovers are searched (see DISCOVERY_PATTERNS).
Exit codes: 0 no errors, 1 errors found, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MAX_NAME = 64
MAX_DESCRIPTION = 1024
RECOMMENDED_MAX_BODY_LINES = 500
ALLOWED_FRONTMATTER = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}

# YAML block scalar indicators: `description: >` / `|`, optionally with a chomping
# or indentation modifier. The indicator is syntax, not content.
BLOCK_SCALAR = re.compile(r"^[|>][-+]?\d*$")

# Where `gh skill publish` looks for skills. Verified against gh 2.102.0 by
# planting a skill in each layout and checking which ones gh reported finding -
# "not a git repository"/"Dry run complete" on all six, "no skills found" only
# when the repo was truly empty. Keep this in sync with gh, not with its --help
# (which, at 2.102.0, omits the two `{prefix}/skills/...` rows its own error
# message lists).
DISCOVERY_PATTERNS = (
    "skills/*/SKILL.md",
    "skills/*/*/SKILL.md",
    "*/skills/*/SKILL.md",
    "*/skills/*/*/SKILL.md",
    "*/SKILL.md",
    "plugins/*/skills/*/SKILL.md",
)


def parse_frontmatter(text: str):
    if not text.startswith("---"):
        return None, {}
    match = re.match(r"^---\r?\n(.*?)(?:\r?\n---\r?\n?|\Z)", text, re.DOTALL)
    if not match:
        return None, {}
    raw_front = match.group(1)
    values, lists, key = {}, set(), None
    for raw in raw_front.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if re.match(r"^\s", raw):
            if key and raw.strip().startswith("- "):
                lists.add(key)
                values.setdefault(key, []).append(raw.strip()[2:].strip())
            elif key:
                values.setdefault(key, []).append(raw.strip())
            continue
        item = re.match(r"^([A-Za-z0-9_.\-]+)\s*:\s*(.*)$", raw)
        if not item:
            continue
        key = item.group(1)
        values.setdefault(key, [])
        if item.group(2).strip():
            values[key].append(item.group(2).strip())
    flat = {}
    for k, v in values.items():
        # Fold a block scalar: drop the `>`/`|` indicator and join the indented
        # lines. Keeping the indicator as content made a valid `description: >`
        # fail with a bogus "must not contain '>'" - and gh accepts that file.
        if v and BLOCK_SCALAR.match(v[0].strip()):
            flat[k] = " ".join(part.strip() for part in v[1:]).strip()
        else:
            flat[k] = "\n".join(v).strip()
    return flat, {"_lists": lists, "_body_start": match.end()}


def unquote(value: str) -> str:
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1].replace('\\"', '"').replace("\\n", " ")
    return value


def check(skill_dir: Path):
    errors, warnings = [], []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"SKILL.md not found in {skill_dir}"], warnings

    text = skill_md.read_text(encoding="utf-8", errors="ignore")
    if text.startswith("﻿"):
        # gh rejects a BOM too, but reports "missing required field: name", which
        # sends you looking at the frontmatter instead of the encoding. Notepad and
        # "UTF-8 with BOM" both produce this on Windows.
        errors.append("SKILL.md starts with a UTF-8 BOM - re-save it as 'UTF-8' without BOM "
                      "(a BOM makes gh skill publish report missing name/description)")
        text = text.lstrip("﻿")

    front, meta = parse_frontmatter(text)
    if front is None:
        errors.append("SKILL.md must start with a '---' YAML frontmatter block")
        return errors, warnings

    for key in front:
        if key not in ALLOWED_FRONTMATTER:
            # gh accepts unknown keys, so failing here would block a repo the real
            # validator publishes. Point at the right home for the data instead.
            warnings.append(f"unknown frontmatter key '{key}' - gh skill publish accepts it, "
                            f"but only {', '.join(sorted(ALLOWED_FRONTMATTER))} are meaningful; "
                            "put custom data under 'metadata'")

    name = unquote(front.get("name", ""))
    if not name:
        errors.append("frontmatter is missing 'name'")
    else:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            errors.append(f"name '{name}' must be lowercase hyphen-case with no leading/trailing/consecutive hyphens")
        if len(name) > MAX_NAME:
            errors.append(f"name is {len(name)} chars (max {MAX_NAME})")
        if name != skill_dir.name:
            errors.append(f"name '{name}' must equal the directory name '{skill_dir.name}'")

    description = unquote(front.get("description", ""))
    if not description:
        errors.append("frontmatter is missing 'description'")
    else:
        if len(description) > MAX_DESCRIPTION:
            errors.append(f"description is {len(description)} chars (max {MAX_DESCRIPTION})")
        if "<" in description or ">" in description:
            errors.append("description must not contain '<' or '>'")
        if description.lower().startswith("helps with") or len(description) < 20:
            warnings.append("description looks too vague to route reliably; say what it does and when to use it")

    if "allowed-tools" in front:
        if "allowed-tools" in meta.get("_lists", set()) or front["allowed-tools"].strip().startswith("["):
            errors.append("allowed-tools must be a single space-separated string, not a list")

    if not front.get("license"):
        warnings.append("no 'license' field: 'gh skill publish' reports it as a recommended field")

    body = text[meta["_body_start"]:]
    body_lines = body.splitlines()
    if len(body_lines) > RECOMMENDED_MAX_BODY_LINES:
        warnings.append(f"SKILL.md body is {len(body_lines)} lines; the spec recommends under {RECOMMENDED_MAX_BODY_LINES}")

    if re.search(r"^\s*\[TODO:", body, re.MULTILINE):
        errors.append("SKILL.md still contains an unfinished [TODO: ...] placeholder")

    # new_skill.py puts a [TODO: ...] in the description as well as the body. A body-only
    # check let a skill through with the placeholder still in its description - the one
    # field that decides whether the skill ever runs - and gh does not catch it either.
    for key, value in front.items():
        if "[TODO:" in value:
            errors.append(f"frontmatter '{key}' still contains an unfinished [TODO: ...] placeholder")

    for target in re.findall(r"\]\(([^)\s]+)\)", body):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if not (skill_dir / target.split("#")[0]).exists():
            errors.append(f"linked file does not exist: {target}")

    if not (skill_dir / "agents" / "openai.yaml").exists():
        warnings.append("agents/openai.yaml is missing (optional, but the initializer creates it)")

    return errors, warnings


def discover(path: Path):
    if path.is_file() and path.name == "SKILL.md":
        return [path.parent]
    if (path / "SKILL.md").exists():
        return [path]
    found = set()
    for pattern in DISCOVERY_PATTERNS:
        found |= {p.parent for p in path.glob(pattern)}
    return sorted(found)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate skills against the Agent Skills spec, offline.")
    parser.add_argument("paths", nargs="+", help="Skill directories or repo roots")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true", help="Only print a summary line")
    args = parser.parse_args(argv)

    results, total_errors = [], 0
    for raw in args.paths:
        path = Path(raw)
        if not path.exists():
            print(f"error: path does not exist: {path}", file=sys.stderr)
            return 2
        dirs = discover(path)
        if not dirs:
            print(f"error: no SKILL.md found under {path}", file=sys.stderr)
            return 2
        for skill_dir in dirs:
            errors, warnings = check(skill_dir)
            total_errors += len(errors)
            results.append({"skill": str(skill_dir), "errors": errors, "warnings": warnings})

    if args.json:
        json.dump({"ok": total_errors == 0, "results": results}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        for item in results:
            status = "OK  " if not item["errors"] else "FAIL"
            print(f"[{status}] {item['skill']}")
            if not args.quiet:
                for message in item["errors"]:
                    print(f"  error  : {message}")
                for message in item["warnings"]:
                    print(f"  warn   : {message}")
        if args.quiet:
            print(f"{len(results)} skill(s), {total_errors} error(s)")

    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
