"""Compare unchanged representative questions; reuses successful query caches."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from movie_lab.config import resolve_movies_path
from movie_lab.data import load_movies
from movie_lab.discovery import discover_movies
from movie_lab.services import search_catalog


def main():
    from movie_lab.embeddings import failure_details
    try:
        old = [json.loads(line) for line in (PROJECT_ROOT / "artifacts/review/semantic_search.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        movies = load_movies(resolve_movies_path())
        comparison = []
        for before in old:
            after = search_catalog(before["query"], movies)
            comparison.append({"query": before["query"], "before": before["hits"], "after": after})
        checks = {query: discover_movies(query, movies) for query in (
            "더 문", "2023년 더 문", "Interstellar", "1917",
            "크리스토퍼 놀란 감독 2010년대 SF 영화", "크리스토퍼 놀란 감독 1900년 영화",
            "넷플릭스에서 볼 수 있는 영화")}
        print(json.dumps({"comparison": comparison, "additional_checks": checks}, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps(failure_details(error), ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
