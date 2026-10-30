import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from scripts.package_review import (ReviewPackageError, STAGE4_FIX_EVIDENCE_FILES,
                                    STAGE4_ITEMS_EVIDENCE_FILES, BROWSER_DEMO_EVIDENCE_FILES,
                                    DIRECTOR_FIELD_EVIDENCE_FILES,
                                    build_review_archive, main, validate_entry_name)


class ReviewPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.evidence = self.root / "artifacts/review"
        self.evidence.mkdir(parents=True)
        for name in ("app.py", "AGENTS.md", ".gitignore", "requirements-project.txt"):
            (self.root / name).write_text("# test-only content\n", encoding="utf-8")
        self.output = self.root / "artifacts/review.zip"

    def test_allowlist_excludes_environment_runtime_data_and_cache(self):
        for name in (".env", "data/movies.json", "data/runtime/chroma/chroma.sqlite3", "venv/hidden.txt", "tests/__pycache__/cache.pyc"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic-forbidden-file-marker", encoding="utf-8")
        (self.evidence / "commands.md").write_text("test command", encoding="utf-8")
        result = build_review_archive(self.output, self.evidence, project_root=self.root)
        self.assertTrue(result["success"])
        with ZipFile(self.output) as archive:
            self.assertIn("app.py", archive.namelist())
            self.assertIn("artifacts/review/commands.md", archive.namelist())
            self.assertTrue(all("synthetic-forbidden-file-marker" not in archive.read(name).decode("utf-8") for name in archive.namelist()))
            manifest = json.loads(archive.read("REVIEW_MANIFEST.json"))
            self.assertTrue(manifest["exclusion_checks"]["environment_and_secret_files_excluded"])
            self.assertTrue(all(len(item["sha256"]) == 64 for item in manifest["files"]))

    def test_forbidden_and_escaping_entry_names_are_rejected(self):
        for name in ("../.env", "C:/private.txt", "/absolute.txt", ".env", ".env.local", "data/movies.json", "data/runtime/db", "venv/file.py", "tests/__pycache__/file.pyc", ".streamlit/secrets.toml"):
            with self.subTest(name=name), self.assertRaises(ReviewPackageError):
                validate_entry_name(name)

    def test_credential_shaped_content_is_rejected_without_echo(self):
        (self.root / "app.py").write_text("sk-" + "a" * 24, encoding="utf-8")
        with self.assertRaises(ReviewPackageError) as caught:
            build_review_archive(self.output, self.evidence, project_root=self.root)
        self.assertNotIn("a" * 24, str(caught.exception))
        self.assertFalse(self.output.exists())

    def test_missing_required_source_prevents_incomplete_archive(self):
        (self.root / "app.py").unlink()
        with self.assertRaises(ReviewPackageError):
            build_review_archive(self.output, self.evidence, project_root=self.root)

    def test_stage4_allows_named_evidence_and_replay_without_including_arbitrary_diagnostics(self):
        stage4 = self.root / "artifacts/review_stage4"
        stage4.mkdir()
        for name in ("final_tests.log", "actual_cases_summary.json", "external_quote_failure.json",
                     "source_conditions.md", "stage4_changes.diff"):
            (stage4 / name).write_text("safe test-only evidence", encoding="utf-8")
        (stage4 / "unlisted_failure.json").write_text("synthetic-excluded-marker", encoding="utf-8")
        scripts = self.root / "scripts"
        scripts.mkdir()
        (scripts / "browser_stage4.cjs").write_text("// replay fixture", encoding="utf-8")
        (scripts / "browser_stage4_private.cjs").write_text("synthetic-excluded-marker", encoding="utf-8")
        result = build_review_archive(self.output, stage4, project_root=self.root)
        self.assertTrue(result["success"])
        with ZipFile(self.output) as archive:
            names = set(archive.namelist())
            self.assertIn("scripts/browser_stage4.cjs", names)
            self.assertIn("artifacts/review_stage4/actual_cases_summary.json", names)
            self.assertIn("artifacts/review_stage4/external_quote_failure.json", names)
            self.assertNotIn("artifacts/review_stage4/unlisted_failure.json", names)
            self.assertNotIn("scripts/browser_stage4_private.cjs", names)
            self.assertTrue(all("synthetic-excluded-marker" not in archive.read(name).decode("utf-8")
                                for name in names))
            manifest = json.loads(archive.read("REVIEW_MANIFEST.json"))
            self.assertIn("metadata-answer.png", manifest["missing_optional_evidence"])

    def test_stage4_fix_named_evidence_and_existing_source_globs_remain_bounded(self):
        evidence = self.root / "artifacts/review_stage4_fix"
        evidence.mkdir()
        for name in STAGE4_FIX_EVIDENCE_FILES:
            (evidence / name).write_text("safe isolated evidence", encoding="utf-8")
        (evidence / "unlisted.json").write_text("excluded-fixture-marker", encoding="utf-8")
        for directory, name in (("movie_lab", "utility.py"), ("scripts", "replay.py"),
                                ("tests", "test_utility.py"), ("prompts", "new_role.txt")):
            folder = self.root / directory
            folder.mkdir(exist_ok=True)
            (folder / name).write_text("safe isolated source", encoding="utf-8")
        (self.root / "prompts" / "private.json").write_text("excluded-fixture-marker", encoding="utf-8")
        result = build_review_archive(self.output, evidence, project_root=self.root)
        self.assertTrue(result["success"])
        with ZipFile(self.output) as archive:
            names = set(archive.namelist())
            for name in STAGE4_FIX_EVIDENCE_FILES:
                self.assertIn(f"artifacts/review_stage4_fix/{name}", names)
            for name in ("movie_lab/utility.py", "scripts/replay.py", "tests/test_utility.py", "prompts/new_role.txt"):
                self.assertIn(name, names)
            self.assertNotIn("artifacts/review_stage4_fix/unlisted.json", names)
            self.assertNotIn("prompts/private.json", names)
            manifest = json.loads(archive.read("REVIEW_MANIFEST.json"))
            self.assertEqual(manifest["missing_optional_evidence"], [])

    def test_stage4_items_uses_only_named_evidence(self):
        evidence = self.root / "artifacts/review_stage4_items"
        evidence.mkdir()
        for name in STAGE4_ITEMS_EVIDENCE_FILES:
            (evidence / name).write_text("safe isolated items evidence", encoding="utf-8")
        (evidence / "unlisted.json").write_text("excluded-fixture-marker", encoding="utf-8")
        result = build_review_archive(self.output, evidence, project_root=self.root)
        self.assertTrue(result["success"])
        with ZipFile(self.output) as archive:
            names = set(archive.namelist())
            for name in STAGE4_ITEMS_EVIDENCE_FILES:
                self.assertIn(f"artifacts/review_stage4_items/{name}", names)
            self.assertNotIn("artifacts/review_stage4_items/unlisted.json", names)
            self.assertEqual(json.loads(archive.read("REVIEW_MANIFEST.json"))["missing_optional_evidence"], [])

    def test_browser_demo_allows_named_replays_and_only_three_screenshots(self):
        evidence = self.root / "artifacts/review_browser_demo"
        evidence.mkdir()
        for name in BROWSER_DEMO_EVIDENCE_FILES:
            (evidence / name).write_bytes(b"isolated browser evidence fixture")
        (evidence / "04-extra.png").write_bytes(b"excluded screenshot fixture")
        (evidence / "03-interstellar-restored.png").write_bytes(b"excluded obsolete screenshot fixture")
        (evidence / "unlisted.json").write_text("excluded-fixture-marker", encoding="utf-8")
        scripts = self.root / "scripts"
        scripts.mkdir()
        for name in ("browser_demo.cjs", "browser_demo_server.py"):
            (scripts / name).write_text("# isolated replay fixture", encoding="utf-8")
        (scripts / "browser_demo_private.cjs").write_text("excluded-fixture-marker", encoding="utf-8")
        result = build_review_archive(self.output, evidence, project_root=self.root)
        self.assertTrue(result["success"])
        with ZipFile(self.output) as archive:
            names = archive.namelist()
            for name in BROWSER_DEMO_EVIDENCE_FILES:
                self.assertIn(f"artifacts/review_browser_demo/{name}", names)
            self.assertEqual(sum(name.endswith(".png") for name in names), 3)
            self.assertEqual(names.count("scripts/browser_demo.cjs"), 1)
            self.assertEqual(names.count("scripts/browser_demo_server.py"), 1)
            self.assertNotIn("scripts/browser_demo_private.cjs", names)
            self.assertNotIn("artifacts/review_browser_demo/unlisted.json", names)
            self.assertNotIn("artifacts/review_browser_demo/04-extra.png", names)
            self.assertNotIn("artifacts/review_browser_demo/03-interstellar-restored.png", names)
            self.assertIn("artifacts/review_browser_demo/03-status-replay.png", names)
            self.assertIn("artifacts/review_browser_demo/browser_replay.json", names)

    def test_director_field_selects_named_evidence_without_browser_or_extra_images(self):
        evidence = self.root / "artifacts/review_director_field"
        evidence.mkdir()
        for name in DIRECTOR_FIELD_EVIDENCE_FILES:
            (evidence / name).write_text("safe isolated director evidence", encoding="utf-8")
        (evidence / "browser_results.json").write_text("excluded browser fixture", encoding="utf-8")
        (evidence / "extra.png").write_bytes(b"excluded screenshot fixture")
        result = build_review_archive(self.output, evidence, project_root=self.root)
        self.assertTrue(result["success"])
        with ZipFile(self.output) as archive:
            names = archive.namelist()
            for name in DIRECTOR_FIELD_EVIDENCE_FILES:
                self.assertIn(f"artifacts/review_director_field/{name}", names)
            self.assertNotIn("artifacts/review_director_field/browser_results.json", names)
            self.assertFalse(any(name.endswith(".png") for name in names))

    def test_default_cli_targets_director_field_without_building_real_archive_and_stage3_still_supported(self):
        with patch("scripts.package_review.PROJECT_ROOT", self.root), \
                patch("scripts.package_review.build_review_archive", return_value={"success": True}) as builder, \
                redirect_stdout(StringIO()):
            self.assertEqual(main([]), 0)
        builder.assert_called_once_with(self.root / "artifacts/movie_lab_director_field_review.zip",
                                        self.root / "artifacts/review_director_field")
        stage3 = self.root / "artifacts/review_stage3"
        stage3.mkdir()
        (stage3 / "discovery_actual.json").write_text("safe prior-stage evidence", encoding="utf-8")
        (stage3 / "actual_cases.json").write_text("excluded-fixture-marker", encoding="utf-8")
        build_review_archive(self.output, stage3, project_root=self.root)
        with ZipFile(self.output) as archive:
            self.assertIn("artifacts/review_stage3/discovery_actual.json", archive.namelist())
            self.assertNotIn("artifacts/review_stage3/actual_cases.json", archive.namelist())


if __name__ == "__main__":
    unittest.main()
