"""Prepare documents for one selected movie; never generates a final answer."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from movie_lab.config import resolve_movies_path
from movie_lab.data import load_movies
from movie_lab.document_pipeline import create_document_pipeline, safe_error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--movie-id", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--snapshot-archive")
    parser.add_argument("--source", choices=("auto", "snapshot"), default="auto")
    parser.add_argument("--search", action="store_true")
    args = parser.parse_args()
    pipeline = None
    try:
        movies = load_movies(resolve_movies_path())
        if args.movie_id not in movies:
            raise ValueError("unknown movie ID")
        pipeline = create_document_pipeline(args.snapshot_archive, args.source)
        result = pipeline.prepare(movies[args.movie_id], args.question)
        if args.search and result["complete"]:
            hits = pipeline.index.search(args.movie_id, args.question, pipeline.embedder)
            result["search_hits"] = [{**{key: value for key, value in hit.items() if key != "text"},
                                      "quote": hit.get("text", "")[:180]} for hit in hits]
            result["search_embedding_requests"] = 1
        pipeline.close()
        pipeline = None
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0 if result["complete"] else 1
    except Exception as error:
        print(json.dumps({"complete": False, "error": safe_error(error)}, ensure_ascii=False))
        return 1
    finally:
        if pipeline is not None:
            try:
                pipeline.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
