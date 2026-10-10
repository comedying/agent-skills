---
name: make-skill-and-publish
description: Turn a plain-language requirement, document, or repeatable process into a complete, validated Agent Skill and publish that skill to GitHub. Use when the user wants a skill authored from scratch, wants a capability packaged so an agent reuses it every time, or wants their own skill updated and released so others can install it - including when they never say "skill". Not for installing someone else's skill, or for publishing a non-skill project to GitHub.
license: MIT
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
3. **Exactly one hard gate, and it is explicit.** Preparing the working tree is allowed at any
   time: write `.gitignore`, run `git init -b main`, inspect with `git status`. Then **stop**.
   `git add`, `git commit`, creating a remote, and any upload all wait until the user has seen
   the step 6 output and said go. Never proceed past an unresolved HIGH finding.
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
- [ ] 7. **STOP - get the go-ahead, then commit**
- [ ] 8. Publish to GitHub
- [ ] 9. Verify and report

### 1. Turn the request into a skill spec

Mine whatever the user gave you (message, document, screenshots, existing code). Extract:
skill name (hyphen-case, matches the folder), one-line purpose, inputs, outputs, what is in
scope, what is explicitly out of scope, and hard constraints. Ask only when a missing detail
would change the skill's structure; otherwise infer and state the assumption.

### 2. Scaffold

Scaffold with the bundled initializer. It is self-contained (standard library only), so the
skill works even where the Codex `skill-creator` system skill is absent:

```bash
# from anywhere - call the script by path; it creates <output-dir>/<name>/
python "<skill-dir>/scripts/new_skill.py" <name> --path <repo>/skills [--resources references,scripts,assets]
```

- `--path` is the **parent** directory, not the skill directory: `--path <repo>/skills` yields
  `<repo>/skills/<name>/`, which is what the repo layout below requires.
- `agents/openai.yaml` is always created. It is not one of the `--resources` values; those
  only control the optional `references/`, `scripts/`, and `assets/` folders.
- The bare `python scripts/...` form used elsewhere in this file assumes you are already
  inside the skill directory. From anywhere else, call the script by its full path.

The host's `skill-creator` (`init_skill.py`) produces an equivalent skeleton and is fine to
use instead when present. Only if neither is available, create the files by hand: `SKILL.md`
(required) plus the optional pieces the workflow actually needs (`agents/openai.yaml`,
`scripts/`, `references/`, `assets/`). Do not create empty scaffolding.

### 3. Write the skill

- **Frontmatter.** `name` and `description` are required. Add `license: MIT` (or the license
  the user chose) before publishing - `gh skill publish` flags it as a recommended field when
  absent. `metadata.short-description` is optional UI metadata. Do not add other keys.
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
- Ready-to-use Chinese prompt templates for the spec, scaffolding, README, pre-publish check,
  `gh` login, and publishing stages are in
  [references/stage-prompts.md](references/stage-prompts.md). They are the chat-facing version
  of this workflow and are deliberately looser; when they disagree with this file, this file
  wins.

### 4. Test before publishing

Run the skill against at least one realistic request, not a toy one. Inspect the artifacts it
produced, not the wording. Fix what fails and re-run.

For triggering, write the query set first (8-10 that should fire, including phrasings that
never name the domain; 8-10 near-misses that should stay quiet), following
[references/stage-prompts.md](references/stage-prompts.md).
[assets/trigger-eval-queries.json](assets/trigger-eval-queries.json) is a worked example: the
20 queries used to test this skill itself, with their labels and the observed outcome.
Then actually run it: if you can
start a fresh agent session with the skill installed, do that and record hit/miss per query.
If you cannot produce a second session, save the query set as a file and mark it **not
executed** - do not describe triggering as verified when it was not.

### 5. Write the repo README

One README, at the repo root, not inside the skill folder. It must cover: the problem it
solves, main features, installation, usage, and an input/output example - and it must match
the real behavior.

### 6. Pre-publish checks, then stop

Run both and report their raw output:

```bash
python scripts/scan_publish_ready.py <repo-root>
python scripts/validate_skill.py <repo-root>
```

`scan_publish_ready.py` reports secrets, keys, tokens, PII, absolute paths, junk files and
oversized binaries, with any secret value masked (`--json` for structured output,
`--fail-on medium` to be strict). `validate_skill.py` checks the Agent Skills rules offline -
name/directory match, description limits, `allowed-tools` shape, leftover `[TODO: ...]`,
broken reference links - so it still works when `gh` is unavailable.

Then **stop and wait for the go-ahead.** Do not continue to step 7 on your own.

### 7. Commit (gated)

Only after the user approves the step 6 output. Writing `.gitignore`, running `git init -b main`
and reading `git status` are allowed before the gate; `git add` and `git commit` are not.

Use the `.gitignore` starter in [references/publish-github.md](references/publish-github.md),
check with `git status --porcelain --ignored` that scratch directories are excluded, then
stage and commit with a clear message. Do not commit ignored files or test debris.

### 8. Publish to GitHub

Read [references/publish-github.md](references/publish-github.md) for the exact commands.
Start with `gh --version`. If `gh` is not installed, say so and give the host's install command
(winget / brew / apt / dnf, per the reference) - do not work around it by hand-rolling a push.
Then `gh auth status`; if not authenticated, hand off to the user for `gh auth login`.

Two paths, often used together:

- **Repo + push:** `gh repo create ... --source . --push` publishes the code.
- **Validate + release:** `gh skill publish` validates against the Agent Skills spec and cuts
  a GitHub release, which makes the skill installable with `gh skill install`.

### 9. Verify and report

If you stopped at the gate, report the local state instead and say plainly what is pending:
files created, scan and validation results, and the exact command that would publish. Never
describe unpublished work as published.

After publishing, confirm the remote actually has the content (`gh repo view`,
`git ls-remote`, or open the release) and report the repo URL, the release URL, how to install
it, and anything you could not verify.

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
        |-- scripts/
        `-- assets/
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
