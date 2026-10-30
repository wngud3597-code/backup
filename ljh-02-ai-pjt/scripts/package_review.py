"""검토에 필요한 허용 파일만 로컬 ZIP으로 묶는다. 비밀 파일은 열지 않는다."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_FILES = (
    "app.py",
    "AGENTS.md",
    ".gitignore",
    "requirements-project.txt",
    "requirements.txt",
    "README.md",
    ".streamlit/config.toml",
    ".vscode/settings.json",
    ".env.example",
    # Actual replay artifacts are explicit, never a recursive JS glob.
    "artifacts/browser_stage4.cjs",
    "artifacts/browser_stage4_probe.cjs",
    # Retain the legacy replay location for existing package fixtures. No
    # placeholder is created or copied; only real files can enter the ZIP.
    "scripts/browser_stage4.cjs",
    "scripts/browser_demo.cjs",
    "scripts/browser_demo_server.py",
)
FIXTURE_FILES = (
    "tests/fixtures/conversations.json",
    "tests/fixtures/snapshot_identity.json",
)
EVIDENCE_FILES = (
    "baseline_tests_44.log",
    "final_tests.log",
    "first_implementation_core.diff",
    "stage2_changes.diff",
    "streamlit_config.diff",
    "dependency_versions.md",
    "environment_summary.json",
    "pip_check.log",
    "pip_install_summary.json",
    "gms_embedding_probe.json",
    "sample_index.jsonl",
    "sample_verify.jsonl",
    "sample_search.jsonl",
    "full_index.jsonl",
    "full_verify.jsonl",
    "rerun_index.jsonl",
    "semantic_search.jsonl",
    "embedding_consistency.json",
    "failure_evidence.json",
    "browser_evidence.json",
    "stage2-screen.png",
    "implementation_report.md",
    "commands.md",
    "baseline_tests.log",
    "final_tests.log",
    "discovery_inspection.md",
    "discovery_actual.json",
    "interstellar_initial.json",
    "interstellar_prepare.json",
    "moon_prepare.json",
    "interstellar_cached.json",
    "moon_cached.json",
    "snapshot_identity.json",
    "initial_selection_cleanup.json",
    "documents_summary.json",
    "isolation_and_reuse.json",
    "versions.json",
    "stage3_changes.diff",
    "discovery-screen.png",
    "prepared-screen.png",
)
STAGE3_EVIDENCE_FILES = (
    "baseline_tests.log", "baseline_hashes.json", "final_tests.log",
    "pip_check.log", "versions.json", "discovery_inspection.md",
    "discovery_actual.json", "interstellar_initial.json", "interstellar_prepare.json",
    "moon_prepare.json", "interstellar_cached.json", "moon_cached.json",
    "snapshot_identity.json", "initial_selection_cleanup.json", "documents_summary.json",
    "isolation_and_reuse.json", "stage3_changes.diff", "browser_evidence.json",
    "discovery-screen.png", "prepared-screen.png", "implementation_report.md", "commands.md",
)
STAGE4_EVIDENCE_FILES = (
    "final_tests.log", "pip_check.log", "versions.json", "storage_and_preservation.json",
    "stage4_changes.diff", "commands.md", "implementation_report.md", "actual_cases_summary.json",
    "actual_metadata.json", "actual_external_followup.json", "actual_verification.json",
    "actual_verification_positive.json", "requirements_status.md",
    "verification_server_failure.json",
    "verification_judgment_failure.json",
    "defect_fixes.json", "retrieval_comparison.json", "browser_evidence.json",
    "metadata-answer.png", "special-mode.png", "movie-switch.png",
    "requirements_reference.md", "source_conditions.md", "langgraph-resolver.json",
    "langgraph-install.json", "initial_regression.log",
    # These are the existing diagnostic artifacts, deliberately enumerated.
    # An arbitrary future *_failure.json is not automatically trusted.
    "abstention_review_diagnostic.json", "external_citation_failure.json",
    "external_failure_diagnostic.json", "external_quote_failure.json",
    "external_semantic_failure.json", "indexed_quote_semantic_failure.json",
    "indexed_verification_failure.json", "initial_external_failure.json",
    "initial_verification_failure.json", "verification_citation_diagnostic.json",
    "withheld_claim_review_failure.json",
    "semantic_false_positive.json", "semantic_blocked_failure.json",
)
STAGE4_FIX_EVIDENCE_FILES = (
    "final_tests.log", "pip_check.log", "environment.json",
    "baseline_related_tests.log", "related_tests.log", "before_after_answering.log",
    "discovery_tests.log", "before_after_discovery.json", "source_display_tests.log",
    "before_after_citations.json", "preflight_evidence.json", "after_store_evidence.json",
    "actual_cases.json", "implementation_report.md", "requirements_status.md",
    "commands.md", "changes.diff", "source_conditions.md", "focused_final_tests.log",
)
STAGE4_ITEMS_EVIDENCE_FILES = (
    "baseline_related_tests.log", "related_tests.log", "final_tests.log", "pip_check.log",
    "store_before.json", "store_after.json", "offline_contract.json", "actual_case.json",
    "implementation_report.md", "requirements_status.md", "commands.md", "changes.diff",
    "source_conditions.md", "environment.json", "package_tests.log",
)
BROWSER_DEMO_EVIDENCE_FILES = (
    "implementation_report.md", "requirements_status.md", "commands.md",
    "source_conditions.md", "changes.diff", "browser_results.json", "browser_replay.json", "api_events.jsonl",
    "browser_driver.log", "server_status.json", "related_ui_tests.log", "package_tests.log",
    "final_tests.log", "environment.json", "store_before.json", "store_after.json",
    "01-interstellar.png", "02-moon-verification.png", "03-status-replay.png",
)
DIRECTOR_FIELD_EVIDENCE_FILES = (
    "implementation_report.md", "requirements_status.md", "commands.md",
    "source_conditions.md", "changes.diff", "baseline_related_tests.log", "related_tests.log",
    "final_tests.log", "package_tests.log", "retrieval_tests.log", "offline_cases.json",
    "actual_case.json", "environment.json", "store_before.json", "store_after.json",
)
FORBIDDEN_PARTS = frozenset(
    {
        ".git",
        "venv",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".chroma",
        "chroma_db",
        "runtime",
    }
)
MANIFEST_NAME = "REVIEW_MANIFEST.json"
# These patterns inspect only allowlisted text. The real key is never read for
# comparison; this is an additional guard, not a claim of universal detection.
CREDENTIAL_PATTERNS = (
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"(?i)bearer[ \t]+[A-Za-z0-9_.-]{24,}"),
    re.compile(
        rb"(?im)^\s*(?:GMS_KEY|OPENAI_API_KEY)\s*=\s*['\"]?[A-Za-z0-9_.-]{20,}"
    ),
)


class ReviewPackageError(Exception):
    """허용 목록 또는 비밀정보 보호 검사 실패."""


def validate_entry_name(name: str) -> None:
    """ZIP slip, 비밀 파일, 저장소와 전체 데이터 경로를 차단한다."""
    entry = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or ":" in name
        or entry.is_absolute()
        or any(part in {"", ".", ".."} for part in name.split("/"))
    ):
        raise ReviewPackageError("ZIP 항목 경로 검사를 통과하지 못했습니다.")
    parts = tuple(part.lower() for part in entry.parts)
    if any(part in FORBIDDEN_PARTS for part in parts):
        raise ReviewPackageError("제외 대상 디렉터리가 포함되었습니다.")
    if any(part == ".env" or (part.startswith(".env.") and part != ".env.example") for part in parts):
        raise ReviewPackageError("환경변수 파일은 패키징할 수 없습니다.")
    if "data" in parts or entry.suffix.lower() in {".zip", ".pdf", ".sqlite3", ".db"}:
        raise ReviewPackageError("배포 데이터 또는 실행 저장소는 포함할 수 없습니다.")
    if entry.name.lower() == "secrets.toml":
        raise ReviewPackageError("비밀정보 설정 파일은 포함할 수 없습니다.")


def _inside_root(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ReviewPackageError("프로젝트 밖의 경로는 사용할 수 없습니다.")
    return resolved


def select_files(root: Path, evidence_dir: Path) -> tuple[dict[str, Path], list[str]]:
    """확장자 탐색도 지정된 코드 폴더의 바로 아래에서만 수행한다."""
    selected: dict[str, Path] = {}

    def add(path: Path, name: str) -> None:
        validate_entry_name(name)
        for component in (path, *path.parents):
            if component == root:
                break
            if component.is_symlink() or component.is_junction():
                raise ReviewPackageError("심볼릭 링크나 정션은 패키징할 수 없습니다.")
        resolved = _inside_root(path, root)
        validate_entry_name(resolved.relative_to(root).as_posix())
        if resolved.is_file():
            selected[name] = resolved

    for name in STATIC_FILES + FIXTURE_FILES:
        add(root / name, name)
    for directory in ("movie_lab", "tests", "scripts"):
        for path in sorted((root / directory).glob("*.py")):
            add(path, f"{directory}/{path.name}")

    for path in sorted((root / "prompts").glob("*.txt")):
        add(path, f"prompts/{path.name}")

    missing_evidence = []
    if evidence_dir.name == "review_director_field":
        evidence_names = DIRECTOR_FIELD_EVIDENCE_FILES
    elif evidence_dir.name == "review_browser_demo":
        evidence_names = BROWSER_DEMO_EVIDENCE_FILES
    elif evidence_dir.name == "review_stage4_items":
        evidence_names = STAGE4_ITEMS_EVIDENCE_FILES
    elif evidence_dir.name == "review_stage4_fix":
        evidence_names = STAGE4_FIX_EVIDENCE_FILES
    elif evidence_dir.name == "review_stage4":
        evidence_names = STAGE4_EVIDENCE_FILES
    elif evidence_dir.name == "review_stage3":
        evidence_names = STAGE3_EVIDENCE_FILES
    else:
        evidence_names = EVIDENCE_FILES
    for name in dict.fromkeys(evidence_names):
        path = evidence_dir / name
        if path.exists():
            add(path, f"{evidence_dir.relative_to(root).as_posix()}/{name}")
        else:
            missing_evidence.append(name)

    required = {"app.py", "AGENTS.md", ".gitignore", "requirements-project.txt"}
    if not required.issubset(selected):
        raise ReviewPackageError("필수 검토 파일이 없습니다.")
    return selected, missing_evidence


def build_review_archive(
    output: Path, evidence_dir: Path, *, project_root: Path = PROJECT_ROOT
) -> dict:
    """파일 SHA-256과 제외 검사를 기록하고 완성된 ZIP을 다시 검사한다."""
    root = project_root.resolve()
    output = _inside_root(output, root)
    evidence_dir = _inside_root(evidence_dir, root)
    if output.suffix.lower() != ".zip":
        raise ReviewPackageError("출력 확장자는 .zip이어야 합니다.")
    selected, missing_evidence = select_files(root, evidence_dir)
    if output in selected.values():
        raise ReviewPackageError("출력 파일이 입력 파일과 겹칩니다.")

    # Read only selected files. No recursive archive/data/environment reads.
    contents: dict[str, bytes] = {}
    manifest_files = []
    for name, path in sorted(selected.items()):
        content = path.read_bytes()
        if path.suffix.lower() != ".png" and any(
            pattern.search(content) for pattern in CREDENTIAL_PATTERNS
        ):
            raise ReviewPackageError(
                "허용 파일에서 자격증명 형태가 감지되어 패키징을 중단했습니다."
            )
        contents[name] = content
        manifest_files.append(
            {"path": name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        )
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": manifest_files,
        "missing_optional_evidence": missing_evidence,
        "exclusion_checks": {
            "relative_entry_paths_only": True,
            "allowlisted_files_only": True,
            "no_symbolic_links": True,
            "environment_and_secret_files_excluded": True,
            "virtualenv_caches_git_and_chroma_excluded": True,
            "full_distribution_data_excluded": True,
            "generic_credential_pattern_check_passed": True,
        },
        "secret_check_limit": (
            "Only allowlisted text is checked for generic credential patterns. "
            "The actual key and .env were never opened or compared."
        ),
    }
    contents[MANIFEST_NAME] = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="review-", suffix=".zip", dir=output.parent, delete=False
    ) as pending:
        temp_path = Path(pending.name)
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in contents.items():
                validate_entry_name(name)
                archive.writestr(name, content)
        with zipfile.ZipFile(temp_path) as archive:
            if set(archive.namelist()) != set(contents):
                raise ReviewPackageError("ZIP 항목 목록 재검사에 실패했습니다.")
            if archive.testzip() is not None:
                raise ReviewPackageError("ZIP 무결성 검사를 통과하지 못했습니다.")
            for item in manifest_files:
                digest = hashlib.sha256(archive.read(item["path"])).hexdigest()
                if digest != item["sha256"]:
                    raise ReviewPackageError("ZIP 파일 해시 재검사에 실패했습니다.")
        temp_path.replace(output)
    finally:
        temp_path.unlink(missing_ok=True)
    return {
        "success": True,
        "output": output.relative_to(root).as_posix(),
        "file_count": len(contents),
        "archive_bytes": output.stat().st_size,
        "archive_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "manifest": MANIFEST_NAME,
        "missing_optional_evidence": missing_evidence,
        "exclusion_checks": manifest["exclusion_checks"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts/movie_lab_director_field_review.zip")
    parser.add_argument("--evidence-dir", default="artifacts/review_director_field")
    args = parser.parse_args(argv)
    output = Path(args.output)
    evidence_dir = Path(args.evidence_dir)
    try:
        result = build_review_archive(
            output if output.is_absolute() else PROJECT_ROOT / output,
            evidence_dir if evidence_dir.is_absolute() else PROJECT_ROOT / evidence_dir,
        )
    except (ReviewPackageError, OSError, zipfile.BadZipFile):
        # Do not echo raw exception messages, environment values, or file content.
        print(json.dumps({"success": False, "error": "review_package_validation_failed"}))
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
