---
name: make-skill-and-publish
description: Turn a plain-language requirement, document, or workflow into a complete, validated Agent Skill and publish it to GitHub. Use when the user wants a skill created, wants to package a repeatable capability for an agent, or wants to open-source, release, share, or install a skill from a repo - including when they describe the capability without saying "skill" and just want the agent to be able to do X reliably.
metadata:
  short-description: Create an Agent Skill and publish it to GitHub
---

# Make Skill and Publish

Take a requirement all the way to a published skill: scope it, scaffold it, write and test it,
scan it for anything private, commit it, and publish it to GitHub. Treat publishing as an
external mutation: the human authorizes it, you do the mechanical work.

## Hard rules

1. **Never handle credentials.** Do not ask for, echo, or accept passwords, tokens, or 2FA
   codes in the conversation, and never write them into a command, file, or environment
   variable. Authentication is the human's job.
2. **Pause at authorization.** Run read-only checks freely (`gh auth status`, `git status`,
   `gh repo view`). The moment a browser, verification code, 2FA, or account password is
   required, stop and hand control back to the user.
3. **Nothing leaves the machine before the scan.** Run the pre-publish scan, report the raw
   findings, and get an explicit go-ahead before `git commit`, any remote, or any upload.
   Never proceed past an unresolved HIGH finding.
4. **Do not fabricate.** The README, description, and examples must describe what the skill
   actually does. If the requirement is under-specified, say what is missing instead of
   padding it.
5. **Keep it portable.** Relative paths only inside the skill; no machine-specific absolute
   paths, usernames, private data, or local test debris in the published tree.
6. **Follow the Agent Skills spec.** `name` matches its directory and is lowercase-hyphen
   (a-z, 0-9, `-`, no leading/trailing/consecutive hyphens, max 64); `description` max 1024
   chars; keep `SKILL.md` under ~500 lines and push detail into `references/`.

## Workflow

- [ ] 1. Turn the request into a skill spec
- [ ] 2. Scaffold the skill folder
- [ ] 3. Write `SKILL.md` and its resources
- [ ] 4. Test it against a realistic request
- [ ] 5. Write the repo README
- [ ] 6. Run the pre-publish scan and report
- [ ] 7. Commit
- [ ] 8. Publish to GitHub
- [ ] 9. Verify and report

### 1. Turn the request into a skill spec

Mine whatever the user gave you (message, document, screenshots, existing code). Extract:
skill name (hyphen-case, matches the folder), one-line purpose, inputs, outputs, what is in
scope, what is explicitly out of scope, and hard constraints. Ask only when a missing detail
would change the skill's structure; otherwise infer and state the assumption.

### 2. Scaffold

Prefer the bundled initializer so the required files are consistent:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/init_skill.py" <name> \
  --path <output-dir> [--resources references,scripts,assets] [--interface short_description="..."]
```

If that script is unavailable, create the folder by hand: `SKILL.md` (required), plus only
the optional pieces the workflow needs (`agents/openai.yaml`, `scripts/`, `references/`,
`assets/`). Do not create empty scaffolding.

### 3. Write the skill

- **`description` is the routing surface.** It is the only thing loaded before the skill
  activates. Write it as an instruction: "Use when ...". Describe the user's intent, list the
  contexts where it applies even if the user never names the domain, and keep it under 1024
  characters. `references/stage-prompts.md` has a trigger-testing recipe.
- **Body: only what the agent would not already know.** Prefer procedures over declarations.
  Add a `## Gotchas` list for non-obvious, environment-specific facts that defy a reasonable
  assumption - these are usually the highest-value lines in a skill.
- **Push detail out.** Move long procedures, schemas, and examples into `references/` and link
  each one with the condition for reading it ("read `references/x.md` when ..."). Bundle a
  tested script in `scripts/` when the same logic would otherwise be rewritten every run.
- Ready-to-use Chinese prompt templates for every stage are in
  [references/stage-prompts.md](references/stage-prompts.md).

### 4. Test before publishing

Run the skill against at least one realistic request, not a toy one. Inspect the artifacts it
produced, not the wording. Fix what fails and re-run. Sanity-check triggering in both
directions: it should fire on a realistic phrasing that does not name the domain, and stay
quiet on a near-miss that shares vocabulary but needs something else.

### 5. Write the repo README

One README, at the repo root, not inside the skill folder. It must cover: the problem it
solves, main features, installation, usage, and an input/output example - and it must match
the real behavior.

### 6. Pre-publish scan

```bash
python scripts/scan_publish_ready.py <repo-root>
```

It reports secrets, keys, tokens, PII, absolute paths, junk files, and oversized binaries,
masking any secret values in its output. Report the findings verbatim and wait for
confirmation. Add `--json` for structured output, or `--fail-on medium` to make it strict.

### 7. Commit

Add a `.gitignore` (see [references/publish-github.md](references/publish-github.md) for a
starter), then `git init -b main`, stage, and commit with a clear message. Do not commit
ignored files or test debris.

### 8. Publish to GitHub

Read [references/publish-github.md](references/publish-github.md) for the exact commands.
Check `gh auth status` first; if not authenticated, hand off to the user for `gh auth login`.
Two paths, often used together:

- **Repo + push:** `gh repo create ... --source . --push` publishes the code.
- **Validate + release:** `gh skill publish` validates against the Agent Skills spec and cuts
  a GitHub release, which makes the skill installable with `gh skill install`.

### 9. Verify and report

Confirm the remote actually has the content (`gh repo view`, `git ls-remote`, or open the
release). Report the repo URL, what was published, how to install it, and anything you could
not verify.

## Repo layout

```text
<repo>/
|-- README.md
|-- LICENSE            # optional
|-- .gitignore
`-- skills/
    `-- <skill-name>/
        |-- SKILL.md
        |-- agents/
        |-- references/
        `-- scripts/
```

`gh skill publish` discovers skills at `skills/*/SKILL.md`, `skills/{scope}/*/SKILL.md`,
`*/SKILL.md` (root-level), and `plugins/{scope}/skills/*/SKILL.md`, so keeping the skill under
`skills/<name>/` makes it both publishable and installable.

## Gotchas

- A skill folder does not need its own README; the README belongs to the repo that hosts it.
- `description` cannot contain `<` or `>` (a common validation failure).
- The folder name and the frontmatter `name` must be identical, or validation fails.
- `allowed-tools` is a single space-separated string, not a YAML list.
- Never publish a `.env`, key material, or a machine-specific absolute path; scan before
  every first push, even for a "small" change.
