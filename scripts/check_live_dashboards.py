"""Explicit live-model smoke check. Each question can incur provider usage.

Run only on request: python scripts/check_live_dashboards.py --output .local/live
Responses are kept locally for inspection, never include provider credentials.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib import error, request

QUESTIONS = {
    "overview": "داشبورد بده",
    "management": "داشبورد گزارشی بده",
    "shipping": "داشبورد حمل بده",
    "strengths": "نقاط قوت و ضعف را نشان بده",
    "revenue": "روند درآمد را نشان بده",
    "compare": "فصل دوم و سوم را مقایسه کن",
    "unavailable": "تعداد محموله‌ها به تفکیک مسیر را نشان بده",
    "bridge": "چرا سود فصل سوم کمتر شد؟",
}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path, default=Path(".local/live"))
    parser.add_argument("--only", choices=tuple(QUESTIONS), nargs="+")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for key in args.only or QUESTIONS:
        question = QUESTIONS[key]
        req = request.Request(
            args.base + "/api/demo-finance/question",
            data=json.dumps({"question": question}, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"},
        )
        started = time.monotonic()
        try:
            with request.urlopen(req, timeout=150) as response:
                status, body = response.status, response.read()
        except error.HTTPError as exc:
            status, body = exc.code, exc.read()
        except (error.URLError, TimeoutError) as exc:
            status, body = 0, json.dumps({"transport_error": type(exc).__name__}).encode()
        try:
            result = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            result = {"transport_error": "non_json_response"}
        (args.output / (key + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        spec = result.get("spec") or {}
        summary = {
            "key": key, "question": question, "http": status,
            "seconds": round(time.monotonic() - started, 2),
            "status": result.get("status"), "error": result.get("detail"),
            "title": spec.get("title"), "answer": spec.get("answer", result.get("message")),
            "charts": [{k: chart.get(k) for k in ("type", "title", "dataset_id", "series")} for chart in spec.get("charts", [])],
            "cards": spec.get("cards", []), "tables": spec.get("tables", []),
            "insights": spec.get("insights", []), "meta": result.get("meta"),
        }
        summaries.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    (args.output / "summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
