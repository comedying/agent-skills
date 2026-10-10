"""Regression tests for the scripts bundled with `make-skill-and-publish`.

Run from the repository root:

    python -m unittest discover -s tests

Standard library only, like the scripts themselves. Each test class corresponds to
one script; the comments name the bug each regression test pins down.

NOTE: `scan_publish_ready.py .` runs over this repository in CI, so this file must
stay scan-clean. Every synthetic secret, path and PII value below is assembled at
runtime from pieces - inlining a whole credential-shaped literal here would turn
this test file into a HIGH finding and redden the repository's own gate.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "skills" / "make-skill-and-publish" / "scripts"


def _load(module_name: str):
    spec = importlib.util.spec_from_file_location(
        f"skill_scripts_{module_name}", SCRIPTS / f"{module_name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scan_publish_ready = _load("scan_publish_ready")
validate_skill = _load("validate_skill")
new_skill = _load("new_skill")


def _join(*parts: str) -> str:
    """Assemble a fixture value at runtime, keeping this source file scan-clean."""
    return "".join(parts)


GH_TOKEN = _join("ghp_", "a" * 36)
PRIVATE_KEY_HEADER = _join("-----BEGIN ", "RSA PRIVATE KEY-----")
BACKSLASH = chr(92)
WINDOWS_USER_PATH = _join("C:", BACKSLASH, "Users", BACKSLASH, "Administrator")
REAL_LOOKING_EMAIL = _join("someone", "@", "gmail", ".", "com")
CN_MOBILE = _join("13", "8", "0013", "8000")
CN_ID = _join("110101", "19900307", "551X")

SKILL_TEMPLATE = (
    "---\n"
    "name: {name}\n"
    "description: Use when a fixture skill named {name} is validated offline in a test.\n"
    "license: MIT\n"
    "{extra}"
    "---\n\n"
    "{body}"
)
DEFAULT_BODY = "Body.\n"


def run(module, argv):
    """Call a script's main() in-process; return (exit_code, combined output)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = module.main(list(argv))
    return code, buffer.getvalue()


@contextlib.contextmanager
def chdir(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def make_skill(root: Path, name: str, *, description: str | None = None,
               extra_front: str = "", body: str = DEFAULT_BODY) -> Path:
    """Write a minimal skill directory and return it."""
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    if description is None:
        description = (f"Use when the fixture skill {name} is exercised "
                       "by the offline validator.")
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\nlicense: MIT\n{extra_front}"
        f"---\n\n{body}",
        encoding="utf-8")
    return skill_dir


def scan_json(target, *extra):
    """Run the scanner with --json and return (exit_code, parsed_report)."""
    code, out = run(scan_publish_ready, [str(target), "--json", *extra])
    return code, json.loads(out)


def rules(report) -> set:
    return {finding["rule"] for finding in report["findings"]}


def errors_of(skill_dir: Path):
    return validate_skill.check(skill_dir)[0]


def warnings_of(skill_dir: Path):
    return validate_skill.check(skill_dir)[1]


class TestValidateSkill(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_valid_skill_has_no_errors(self):
        skill = make_skill(self.root, "good-skill")
        self.assertEqual(errors_of(skill), [])

    def test_name_must_equal_directory_name(self):
        skill = make_skill(self.root, "actual-name")
        (skill / "SKILL.md").write_text(
            "---\nname: other-name\ndescription: Use when the directory and the "
            "frontmatter name disagree in a validation test.\nlicense: MIT\n---\n\nBody.\n",
            encoding="utf-8")
        self.assertTrue(any("must equal the directory name" in e for e in errors_of(skill)))

    def test_description_rejects_angle_brackets(self):
        skill = make_skill(self.root, "angle-skill",
                           description="Use when the user types a <placeholder> value.")
        self.assertTrue(any("'<' or '>'" in e for e in errors_of(skill)))

    def test_description_length_limit(self):
        skill = make_skill(self.root, "long-skill", description="x" * 1025)
        self.assertTrue(any("max 1024" in e for e in errors_of(skill)))

    def test_allowed_tools_as_yaml_list_is_rejected(self):
        skill = make_skill(self.root, "tools-list",
                           extra_front="allowed-tools:\n  - Read\n  - Bash\n")
        self.assertTrue(any("allowed-tools" in e for e in errors_of(skill)))

    def test_allowed_tools_as_string_is_accepted(self):
        skill = make_skill(self.root, "tools-string",
                           extra_front="allowed-tools: Read Bash\n")
        self.assertEqual(errors_of(skill), [])

    def test_unknown_frontmatter_key_is_a_warning_not_an_error(self):
        # Regression: an unknown key was a hard error, so a repo `gh skill publish`
        # accepts (it ignores unknown keys) failed the offline validator instead.
        skill = make_skill(self.root, "extra-key", extra_front="version: 2.0.0\n")
        self.assertEqual(errors_of(skill), [])
        self.assertTrue(any("unknown frontmatter key 'version'" in w
                            for w in warnings_of(skill)))

    def test_folded_block_scalar_description_is_accepted(self):
        # Regression: `description: >` kept the '>' as content and produced a bogus
        # "must not contain '>'" error on a file gh publishes happily.
        skill = make_skill(self.root, "folded-skill")
        (skill / "SKILL.md").write_text(
            "---\n"
            "name: folded-skill\n"
            "description: >\n"
            "  Use when the description is written as a YAML folded\n"
            "  scalar across several lines in the frontmatter.\n"
            "license: MIT\n"
            "---\n\nBody.\n",
            encoding="utf-8")
        self.assertEqual(errors_of(skill), [])

    def test_utf8_bom_is_reported_actionably(self):
        # Regression: a BOM only produced "must start with a '---' block", which is
        # misleading when the file visibly does start with one. gh rejects a BOM too.
        skill = make_skill(self.root, "bom-skill")
        raw = (skill / "SKILL.md").read_bytes()
        (skill / "SKILL.md").write_bytes(b"\xef\xbb\xbf" + raw)
        errors = errors_of(skill)
        self.assertTrue(any("BOM" in e for e in errors), errors)

    def test_todo_placeholder_in_frontmatter_is_an_error(self):
        # Regression: the [TODO:] check only looked at the body, so the placeholder
        # new_skill.py writes into `description` - the field that decides whether the
        # skill ever runs - slipped through both this validator and gh.
        skill = make_skill(
            self.root, "todo-desc",
            description="[TODO: what this skill does and when to use it]")
        self.assertTrue(any("frontmatter 'description'" in e and "[TODO:" in e
                            for e in errors_of(skill)))

    def test_todo_placeholder_in_body_is_an_error(self):
        skill = make_skill(self.root, "todo-body",
                           body="[TODO: write the real guidance here]\n")
        self.assertTrue(any("[TODO:" in e for e in errors_of(skill)))

    def test_broken_reference_link_is_an_error(self):
        skill = make_skill(self.root, "broken-link",
                           body="Read [the checklist](references/checklist.md) first.\n")
        self.assertTrue(any("linked file does not exist" in e for e in errors_of(skill)))

    def test_existing_reference_link_is_accepted(self):
        skill = make_skill(self.root, "good-link",
                           body="Read [the checklist](references/checklist.md) first.\n")
        (skill / "references").mkdir()
        (skill / "references" / "checklist.md").write_text("checklist\n", encoding="utf-8")
        self.assertEqual(errors_of(skill), [])

    def test_missing_skill_md_is_reported(self):
        empty = self.root / "empty-skill"
        empty.mkdir()
        self.assertTrue(any("SKILL.md not found" in e for e in errors_of(empty)))


class TestDiscovery(unittest.TestCase):
    # The six layouts `gh skill publish` 2.102.0 was verified by hand to find.
    LAYOUTS = {
        "skills/<name>/SKILL.md": "skills/alpha/SKILL.md",
        "skills/<scope>/<name>/SKILL.md": "skills/team/beta/SKILL.md",
        "<prefix>/skills/<name>/SKILL.md": "pack/skills/gamma/SKILL.md",
        "<prefix>/skills/<scope>/<name>/SKILL.md": "pack/skills/team/delta/SKILL.md",
        "<prefix>/SKILL.md": "epsilon/SKILL.md",
        "plugins/<scope>/skills/<name>/SKILL.md": "plugins/p/skills/zeta/SKILL.md",
    }

    def test_discovers_every_layout_gh_finds(self):
        # Regression: discover() knew only three of the six layouts and exited 2 with
        # "no SKILL.md found" on the rest, blocking repos gh publishes fine.
        for label, relative in self.LAYOUTS.items():
            with self.subTest(layout=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                name = Path(relative).parent.name
                target = root / relative
                target.parent.mkdir(parents=True)
                target.write_text(SKILL_TEMPLATE.format(
                    name=name, extra="", body=DEFAULT_BODY), encoding="utf-8")

                found = validate_skill.discover(root)
                self.assertEqual([p.name for p in found], [name], label)
                self.assertEqual(errors_of(found[0]), [], label)

    def test_repo_without_skills_yields_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "README.md").write_text("nothing here\n", encoding="utf-8")
            self.assertEqual(validate_skill.discover(Path(tmp)), [])

    def test_skill_directory_itself_is_discovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = make_skill(Path(tmp), "solo")
            self.assertEqual(validate_skill.discover(skill), [skill])

    def test_skill_md_file_path_is_discovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = make_skill(Path(tmp), "solo")
            self.assertEqual(validate_skill.discover(skill / "SKILL.md"), [skill])

    def test_missing_path_is_a_usage_error(self):
        code, _ = run(validate_skill, [str(Path(tempfile.gettempdir()) / "no-such-dir-xyz")])
        self.assertEqual(code, 2)


class TestScanPublishReady(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_detects_a_github_token(self):
        (self.root / "leak.js").write_text(_join('const t = "', GH_TOKEN, '";\n'),
                                           encoding="utf-8")
        code, report = scan_json(self.root)
        self.assertEqual(code, 1)
        self.assertIn("github-token", rules(report))

    def test_detects_a_private_key_block(self):
        (self.root / "k.txt").write_text(PRIVATE_KEY_HEADER + "\n", encoding="utf-8")
        code, report = scan_json(self.root)
        self.assertEqual(code, 1)
        self.assertIn("private-key-block", rules(report))

    def test_detects_pii(self):
        (self.root / "pii.txt").write_text(
            f"{CN_MOBILE}\n{CN_ID}\n{REAL_LOOKING_EMAIL}\n", encoding="utf-8")
        _, report = scan_json(self.root)
        self.assertIn("cn-mobile-number", rules(report))
        self.assertIn("cn-id-number", rules(report))
        self.assertIn("email-address", rules(report))

    def test_detects_a_windows_user_path(self):
        # Regression: the profile folder had to be preceded by a backslash, but
        # `[A-Za-z]:\\` had already eaten the one after the drive, so the rule missed
        # <drive>:\Users\<name> - the most common shape of a leaked path - and only
        # fired on deeper ones. Both shapes are asserted here.
        for value in (WINDOWS_USER_PATH,
                      _join("D:", BACKSLASH, "data", BACKSLASH, "Users", BACKSLASH, "bob")):
            with self.subTest(path=value):
                with tempfile.TemporaryDirectory() as tmp:
                    (Path(tmp) / "p.txt").write_text(value + "\n", encoding="utf-8")
                    _, report = scan_json(Path(tmp))
                    self.assertIn("windows-user-path", rules(report))

    def test_detects_a_unix_home_path(self):
        value = _join("/", "home", "/", "alice", "/", "notes.txt")
        (self.root / "p.txt").write_text(value + "\n", encoding="utf-8")
        _, report = scan_json(self.root)
        self.assertIn("unix-home-path", rules(report))

    def test_placeholders_and_example_domains_are_not_flagged(self):
        (self.root / "config.md").write_text(
            "TOKEN = ${{ secrets.GITHUB_TOKEN }}\n"
            "password: changeme\n"
            "contact: user@example.com\n",
            encoding="utf-8")
        code, report = scan_json(self.root)
        self.assertEqual(report["findings"], [])
        self.assertEqual(code, 0)

    def test_secret_in_a_large_single_line_file_is_found(self):
        # Regression: any file over 2 MB was skipped without a word, so a one-line
        # JSON dump holding a live-looking token reported HIGH=0 and exited 0.
        (self.root / "dump.json").write_text(
            _join('{"pad":"', "y" * (3 * 1024 * 1024), '","t":"', GH_TOKEN, '"}'),
            encoding="utf-8")
        code, report = scan_json(self.root)
        self.assertEqual(code, 1)
        self.assertIn("github-token", rules(report))

    def test_long_single_line_scan_is_fast(self):
        # Regression: the generic-secret rules were O(n^2) - 8 KB on one line took
        # ~3 s - so a minified bundle or one-line JSON hung the scanner. The old 2 MB
        # "cap" never protected a real file. Run in-process: before the fix this test
        # would not fail, it would hang.
        (self.root / "bundle.js").write_text(
            _join("y" * (1024 * 1024), ' t="', GH_TOKEN, '"'), encoding="utf-8")
        start = time.monotonic()
        code, report = scan_json(self.root)
        elapsed = time.monotonic() - start
        self.assertIn("github-token", rules(report))
        self.assertEqual(code, 1)
        self.assertLess(elapsed, 20.0, f"scanning 1 MB on one line took {elapsed:.1f}s")

    def test_oversized_file_is_reported_as_unscanned(self):
        # Regression: a file past the content limit was skipped silently, so the
        # report could call a repository clean without ever reading the file.
        (self.root / "big.txt").write_text("z" * (1536 * 1024), encoding="utf-8")

        code, report = scan_json(self.root, "--max-file-mb", "1")
        self.assertIn("content-not-scanned", rules(report))
        self.assertEqual(code, 0, "the default gate is high, so this should not fail")

        strict_code, _ = scan_json(self.root, "--max-file-mb", "1", "--fail-on", "medium")
        self.assertEqual(strict_code, 1)

    def test_root_dot_paths_have_no_leading_slash(self):
        # Regression: Path('.').name is '', so every finding was printed as '/leak.js'
        # - a leading slash that reads as an absolute path and drops the root name.
        # Both the documented default and the CI command scan '.'.
        (self.root / "leak.txt").write_text(CN_MOBILE, encoding="utf-8")
        with chdir(self.root):
            _, report = scan_json(Path("."))

        paths = [f["path"] for f in report["findings"]]
        self.assertIn("leak.txt", paths)
        for path in paths:
            self.assertFalse(path.startswith("/"), f"leading slash in {path!r}")
            self.assertNotIn(BACKSLASH, path)

    def test_exclude_prunes_a_directory_by_name(self):
        # Regression: only 'scratch/*' worked; '--exclude scratch' matched nothing
        # because the walk never tested directory names, despite the help text
        # promising to skip paths matching the glob.
        for sub in ("keep", "scratch"):
            (self.root / sub).mkdir()
            (self.root / sub / "leak.txt").write_text(GH_TOKEN, encoding="utf-8")

        _, without = scan_json(self.root)
        self.assertEqual(len(without["findings"]), 2)

        _, excluded = scan_json(self.root, "--exclude", "scratch")
        self.assertEqual(len(excluded["findings"]), 1)
        self.assertTrue(all("scratch" not in f["path"] for f in excluded["findings"]))

        _, globbed = scan_json(self.root, "--exclude", "scratch/*")
        self.assertEqual(len(globbed["findings"]), 1)

    def test_fail_on_thresholds(self):
        (self.root / "pii.txt").write_text(REAL_LOOKING_EMAIL, encoding="utf-8")
        medium_code, _ = scan_json(self.root)
        self.assertEqual(medium_code, 0, "a medium finding should not fail the default gate")

        strict_code, _ = scan_json(self.root, "--fail-on", "medium")
        self.assertEqual(strict_code, 1)

        none_code, _ = scan_json(self.root, "--fail-on", "none")
        self.assertEqual(none_code, 0)

    def test_missing_path_is_a_usage_error(self):
        code, _ = run(scan_publish_ready,
                      [str(Path(tempfile.gettempdir()) / "no-such-dir-xyz")])
        self.assertEqual(code, 2)

    def test_clean_tree_exits_zero(self):
        (self.root / "README.md").write_text("Nothing sensitive here.\n", encoding="utf-8")
        code, report = scan_json(self.root)
        self.assertEqual(code, 0)
        self.assertEqual(report["findings"], [])


class TestNewSkill(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_scaffolds_a_skill(self):
        code, out = run(new_skill, ["demo-skill", "--path", str(self.root),
                                    "--resources", "references,scripts"])
        self.assertEqual(code, 0)
        skill = self.root / "demo-skill"
        self.assertTrue((skill / "SKILL.md").is_file())
        self.assertTrue((skill / "agents" / "openai.yaml").is_file())
        self.assertTrue((skill / "references").is_dir())
        self.assertTrue((skill / "scripts").is_dir())
        self.assertNotIn("Traceback", out)

    def test_scaffold_fails_validation_until_todos_are_filled(self):
        run(new_skill, ["todo-skill", "--path", str(self.root)])
        errors = errors_of(self.root / "todo-skill")
        self.assertTrue(any("[TODO:" in e for e in errors), errors)
        # Both the body and the description carry a placeholder.
        self.assertTrue(any("frontmatter 'description'" in e for e in errors), errors)

    def test_duplicate_resources_does_not_crash(self):
        # Regression: `--resources scripts,scripts` died with an uncaught
        # FileExistsError on the second mkdir of the same folder.
        code, out = run(new_skill, ["dup-skill", "--path", str(self.root),
                                    "--resources", "scripts,scripts"])
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", out)
        self.assertTrue((self.root / "dup-skill" / "scripts").is_dir())

    def test_duplicate_resources_create_the_folder_once(self):
        run(new_skill, ["dup2", "--path", str(self.root), "--resources", "assets,assets"])
        children = sorted(p.name for p in (self.root / "dup2").iterdir())
        self.assertEqual(children.count("assets"), 1, children)

    def test_partial_creation_is_rolled_back_on_failure(self):
        # Regression: a failure mid-scaffold left a half-written skill directory, and
        # the retry then hit "target already exists" with no way forward.
        def boom(*_args, **_kwargs):
            raise OSError("simulated failure")

        original = new_skill.write_openai_yaml
        new_skill.write_openai_yaml = boom
        try:
            code, out = run(new_skill, ["rollback-skill", "--path", str(self.root)])
        finally:
            new_skill.write_openai_yaml = original

        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", out)
        self.assertFalse((self.root / "rollback-skill").exists(),
                         "a failed scaffold must not leave anything behind")

    def test_path_pointing_at_a_file_is_a_clean_error(self):
        # Regression: this raised an uncaught FileExistsError with a full traceback.
        afile = self.root / "afile"
        afile.write_text("x", encoding="utf-8")
        code, out = run(new_skill, ["x-skill", "--path", str(afile)])
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", out)
        self.assertIn("not a directory", out)

    def test_existing_target_is_a_distinct_exit_code(self):
        run(new_skill, ["taken", "--path", str(self.root)])
        code, out = run(new_skill, ["taken", "--path", str(self.root)])
        self.assertEqual(code, 2)
        self.assertIn("already exists", out)

    def test_unknown_resource_is_rejected(self):
        code, out = run(new_skill, ["bad", "--path", str(self.root),
                                    "--resources", "scripts,nonsense"])
        self.assertEqual(code, 1)
        self.assertIn("unknown resource", out)
        self.assertFalse((self.root / "bad").exists())

    def test_normalizes_the_skill_name(self):
        code, out = run(new_skill, ["Team Code Review", "--path", str(self.root)])
        self.assertEqual(code, 0)
        self.assertIn("normalized name to 'team-code-review'", out)
        self.assertTrue((self.root / "team-code-review").is_dir())

    def test_name_without_letters_or_digits_is_rejected(self):
        code, out = run(new_skill, ["!!!", "--path", str(self.root)])
        self.assertEqual(code, 1)
        self.assertIn("at least one letter or digit", out)


class TestRepoItself(unittest.TestCase):
    """The repository must satisfy its own gate."""

    def test_bundled_skill_validates_without_errors(self):
        errors, _ = validate_skill.check(REPO_ROOT / "skills" / "make-skill-and-publish")
        self.assertEqual(errors, [])

    def test_repository_scans_clean(self):
        # Includes this test file: if a fixture here ever leaks a literal secret,
        # the repository's own CI gate fails and this test says why.
        code, report = scan_json(REPO_ROOT)
        self.assertEqual(report["findings"], [], report["findings"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
