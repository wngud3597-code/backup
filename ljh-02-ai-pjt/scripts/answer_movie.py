"""Explicit live movie RAG invocation; no credential or raw exception output."""

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from movie_lab.config import resolve_movies_path
from movie_lab.data import load_movies
from movie_lab.document_pipeline import safe_error
from movie_lab.rag import create_rag_service
from movie_lab.state import append_user_message, append_assistant_message, get_thread


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--movie-id", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--follow-up", action="append", default=[])
    parser.add_argument("--mode", choices=("general", "verify"), default="general")
    parser.add_argument("--source", choices=("auto", "snapshot"), default="auto")
    parser.add_argument("--max-answer-attempts", type=int, choices=(1, 2), default=2)
    parser.add_argument("--snapshot-archive")
    parser.add_argument("--output", help="Optional local validation JSON path")
    parser.add_argument("--quiet", action="store_true", help="Print a short result while keeping the complete output file")
    args = parser.parse_args()
    try:
        movies = load_movies(resolve_movies_path())
        if args.movie_id not in movies:
            raise ValueError
        threads, records = {}, []
        service = create_rag_service(args.snapshot_archive, source_mode=args.source, max_answer_attempts=args.max_answer_attempts)
        graph = service.graph.get_graph().draw_mermaid()
        for question in [args.question, *args.follow_up]:
            started = time.monotonic()
            append_user_message(threads, args.movie_id, question)
            result = service.answer(movies[args.movie_id], question, get_thread(threads, args.movie_id), mode=args.mode)
            record = {"movie_id": args.movie_id, "question": question, "mode": args.mode,
                      "elapsed_seconds": round(time.monotonic() - started, 3),
                      **{key: result.get(key) for key in ("trace", "preparation", "retrieval", "content", "sources", "checks", "validation", "error", "calls", "timings", "stage_calls", "cache", "failure_stage")}}
            records.append(record)
            if result.get("content"):
                append_assistant_message(threads, args.movie_id, result["content"], result["sources"])
            else:
                break
        report = {"graph": graph, "records": records,
                  "success": bool(records) and all(row.get("content") for row in records)}
        encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(encoded, encoding="utf-8")
        print(json.dumps({"success": report["success"], "records": [{key: row.get(key) for key in
            ("question", "elapsed_seconds", "content", "validation", "calls", "error")} for row in records]}, ensure_ascii=False, indent=2)
              if args.quiet else encoded)
        return 0 if report["success"] else 1
    except Exception as error:
        print(json.dumps({"success": False, "error": safe_error(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
