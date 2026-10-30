"""One explicitly approved KOBIS request at most, with key-free evidence only.

No response table is saved; official terms restrict storing/redistributing API
results. There is exactly one explicit lookup and no follow-up lookup: caching
is disabled by default. Screen-only rerendering is verified separately in UI
tests. Failures are never retried here.
"""

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from movie_lab.kobis import KST, create_kobis_service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=(datetime.now(KST).date() - timedelta(days=1)).isoformat())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    service = create_kobis_service(cache_ttl=0)
    first = service.daily_box_office(args.date)
    evidence = {
        "checked_at": datetime.now(KST).isoformat(timespec="seconds"),
        "target_date": first["target_date"], "configured": service.configured,
        "status": first["status"], "real_call_attempted": first["calls"] == 1,
        "request_count": service.request_count, "row_count": len(first["rows"]),
        "source": first["source"], "error": first["error"],
        "retry_count": 0, "persistent_result_cache": False,
        "result_cache_ttl_seconds": service.cache_ttl,
        "note": "No API result table saved; one explicit lookup only; current-screen rerender checked separately.",
        "field_checks": {
            "daily_cumulative_separate": all(
                all(key in row for key in ("audience_daily", "audience_cumulative", "sales_daily", "sales_cumulative"))
                for row in first["rows"]
            ) if first["status"] == "success" else None,
            "missing_or_integer_only": all(
                row.get(key) is None or (isinstance(row.get(key), int) and not isinstance(row.get(key), bool))
                for row in first["rows"] for key in ("audience_daily", "audience_cumulative", "sales_daily", "sales_cumulative")
            ) if first["status"] == "success" else None,
        },
    }
    text = json.dumps(evidence, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if first["status"] in ("success", "unconfigured") else 1


if __name__ == "__main__":
    raise SystemExit(main())
