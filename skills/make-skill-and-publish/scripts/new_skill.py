#!/usr/bin/env python3
"""Create a new Agent Skill folder with a valid skeleton.

Self-contained (standard library only) so the skill works on a machine that does not
have the Codex `skill-creator` system skill.

Usage:
    python new_skill.py <skill-name> --path <output-dir>
                        [--resources references,scripts,assets]
                        [--interface display_name="..." --interface short_description="..."]

The generated SKILL.md contains TODO placeholders on purpose: fill them in before
publishing. Exit codes: 0 ok, 1 usage or I/O error, 2 target already exists.
(A malformed command line also exits 2 - that is argparse's own usage code - so
treat 2 as "nothing was created".)
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

MAX_NAME = 64
ALLOWED_RESOURCES = ("scripts", "references", "assets")

SKILL_TEMPLATE = """---
name: {name}
description: "[TODO: what this skill does and when to use it - write it as 'Use when ...']"
---

# {title}

[TODO: only the guidance the agent would not already know. Prefer procedures over
descriptions, and add a `## Gotchas` list for non-obvious environment facts.]
"""


def normalize(name: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", name.strip().lower())).strip("-")


def title_of(name: str) -> str:
    small = {"and", "or", "to", "of", "the", "with"}
    words = []
    for i, w in enumerate(name.split("-")):
        words.append(w.lower() if i and w.lower() in small else w.capitalize())
    return " ".join(words)


def quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_openai_yaml(skill_dir: Path, name: str, interface: dict) -> None:
    display = interface.get("display_name") or title_of(name)
    short = interface.get("short_description") or f"Help with {display} tasks and workflows"
    short = short[:64]
    lines = ["interface:", f"  display_name: {quote(display)}", f"  short_description: {quote(short)}"]
    for key, value in interface.items():
        if key not in ("display_name", "short_description"):
            lines.append(f"  {key}: {quote(value)}")
    (skill_dir / "agents").mkdir(parents=True, exist_ok=True)
    (skill_dir / "agents" / "openai.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_interface(raw: list) -> dict:
    out = {}
    for item in raw:
        if "=" not in item:
            raise ValueError(f"invalid --interface '{item}', expected key=value")
        key, value = item.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Create a new Agent Skill folder.")
    parser.add_argument("skill_name")
    parser.add_argument("--path", required=True, help="Directory to create the skill in")
    parser.add_argument("--resources", default="", help="Comma-separated: scripts,references,assets")
    parser.add_argument("--interface", action="append", default=[], help="key=value (repeatable)")
    args = parser.parse_args(argv)

    name = normalize(args.skill_name)
    if not name:
        print("error: skill name must contain at least one letter or digit", file=sys.stderr)
        return 1
    if len(name) > MAX_NAME:
        print(f"error: name too long ({len(name)} > {MAX_NAME})", file=sys.stderr)
        return 1
    if name != args.skill_name:
        print(f"note: normalized name to '{name}'")

    try:
        interface = parse_interface(args.interface)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # dict.fromkeys dedupes and keeps order: `--resources scripts,scripts` used to
    # die with an uncaught FileExistsError on the second mkdir of the same folder.
    resources = list(dict.fromkeys(r.strip() for r in args.resources.split(",") if r.strip()))
    bad = [r for r in resources if r not in ALLOWED_RESOURCES]
    if bad:
        print(f"error: unknown resource(s): {', '.join(bad)}", file=sys.stderr)
        return 1

    parent = Path(args.path).expanduser().resolve()
    if parent.exists() and not parent.is_dir():
        print(f"error: --path is not a directory: {parent}", file=sys.stderr)
        return 1

    skill_dir = parent / name
    if skill_dir.exists():
        print(f"error: target already exists: {skill_dir}", file=sys.stderr)
        return 2

    # Roll the whole thing back if any step fails. A half-written skill directory is
    # worse than none: the retry hits "target already exists" with no way forward.
    try:
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            SKILL_TEMPLATE.format(name=name, title=title_of(name)), encoding="utf-8"
        )
        write_openai_yaml(skill_dir, name, interface)
        for resource in resources:
            (skill_dir / resource).mkdir()
    except OSError as exc:
        shutil.rmtree(skill_dir, ignore_errors=True)
        print(f"error: could not create the skill, nothing was left behind: {exc}",
              file=sys.stderr)
        return 1

    print(f"created {skill_dir}")
    for path in sorted(skill_dir.rglob("*")):
        print("  " + str(path.relative_to(skill_dir)))
    print("\nnext: fill in the TODO placeholders, then test with a realistic request.")
    print("      do not publish while any [TODO: ...] remains.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
