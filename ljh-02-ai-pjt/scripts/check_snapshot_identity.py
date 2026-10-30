"""Reproduce three known identity cases from the supplied archive, offline.

Run from the project root:
    python scripts/check_snapshot_identity.py --archive <movie-data.zip>
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from movie_lab.data import DataLoadError, classify_snapshot_identity, load_movies


def main() -> int:
    parser = argparse.ArgumentParser(description="실제 배포 스냅샷의 작품 식별 회귀 사례를 검사합니다. 외부 호출은 없습니다.")
    parser.add_argument("--archive", type=Path, required=True, help="영화 데이터 배포 ZIP 경로")
    parser.add_argument("--movies", type=Path, default=PROJECT_ROOT / "data" / "movies.json")
    args = parser.parse_args()
    try:
        movies = load_movies(args.movies)
        cases = (
            ("753091", "더 문", "불일치"),
            ("17431", "더 문", "일치"),
            ("753091", "달", "확인 필요"),
        )
        failures = 0
        with zipfile.ZipFile(args.archive) as archive:
            for movie_id, title, expected in cases:
                members = [
                    name for name in archive.namelist()
                    if name.endswith(f"/{movie_id}_{title.replace(' ', '_')}.json")
                ]
                if len(members) != 1:
                    raise ValueError(f"검사 대상 스냅샷을 하나로 식별하지 못했습니다: {movie_id}, {title}")
                document = json.loads(archive.read(members[0]).decode("utf-8-sig"))
                check = classify_snapshot_identity(movies[movie_id], document)
                failures += check.status != expected
                print(f"{movie_id} / {title}: {check.status} (기대: {expected})")
                print(f"  {check.reason}")
        return 1 if failures else 0
    except (DataLoadError, OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(f"검사를 완료할 수 없습니다: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
