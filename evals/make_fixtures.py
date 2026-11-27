#!/usr/bin/env python3
"""Write the demo fixture: two small AI features, their landing briefs, usage, task counts, a bill and prices.

This is a second, smaller fixture behind `--demo`, separate from the Landing Loop sample in examples/acme/
(the quote-drafting bet). Its features, visit-notes and quote-follow-up, are not that bet and their
budgets are their own. Acme is an invented company; every figure here is illustrative.

The story the fixture tells, for November 2026 against October:
  visit-notes      gateway log, 10 visit notes a day, two requests each. The prompt grew to 13,500 tokens
                   per task against a budget of 12,000 (over budget), up from 11,500 in October, but cache
                   reads keep price per token and cost per task within budget.
  quote-follow-up  provider usage CSV. Tokens per task hold at budget, but from 16 November part of the
                   traffic moved to the large model, so price per token and cost per task go over
                   budget. October ran on the small model only. It is the driver, on
                   vendor-a/large.
  search-assist    a small spend with no landing brief.

Run it again after changing it; the tests read the files it writes.

Usage:
  python3 evals/make_fixtures.py
"""

from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "skills" / "cost-budget-check" / "assets" / "acme"
NOTE = "Illustrative: Acme is an invented company and every figure here is made up. A demo fixture for cost-budget-check `--demo`, not the quote-drafting bet in the Landing Loop sample."


def brief(title: str, problem: str, metric: str, bar: str, tokens: str, price: str, line: str) -> str:
    return f"""# {title}

{NOTE}

## Landing brief

- **Problem:** {problem}
- **Metric:** {metric}
- **Bar:** {bar}
- **Better:** higher
- **By:** 2026-12-31
- **Non-goals:** No new pricing tiers.
- **Tokens per task:** {tokens}
- **Price per token:** {price}
- **The line:** {line}
- **Decides the next step:** Head of Product, Quoting squad
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "briefs").mkdir(exist_ok=True)
    (OUT / "briefs" / "visit-notes.md").write_text(
        brief(
            "Visit notes",
            "Tradespeople type site visit notes late at night, so the notes are thin and the quote waits.",
            "Visit notes written the same day",
            "70%",
            "12,000",
            "$0.000004",
            "model call. Job details and photos stay in fixed code; only the note wording calls a model.",
        ),
        encoding="utf-8",
    )
    (OUT / "briefs" / "quote-follow-up.md").write_text(
        brief(
            "Quote follow-up",
            "Sent quotes go quiet because nobody has time to follow up, so jobs are lost.",
            "Quotes answered within 14 days",
            "60%",
            "3,000",
            "$0.0000012",
            "model call. Timing rules stay in fixed code; only the follow-up wording calls a model.",
        ),
        encoding="utf-8",
    )
    pricing = {
        "source": "Illustrative prices for the Acme fixture. Not any provider's list price.",
        "retrieved": "2026-11-02",
        "currency": "USD",
        "illustrative": True,
        "models": [
            {"match": "vendor-a/large", "input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
            {"match": "vendor-a/small", "input": 0.80, "output": 4.00, "cache_read": 0.08, "cache_write": 1.00},
            {"match": "vendor-b/mini*", "input": 0.15, "output": 0.60, "cache_read": 0.075, "cache_write": 0.15},
        ],
    }
    (OUT / "pricing.json").write_text(json.dumps(pricing, indent=2) + "\n", encoding="utf-8")

    # visit-notes: one request writes the note, a second, mostly cached, revises it.
    lines = []
    start = datetime.datetime(2026, 10, 1, 9, 0, tzinfo=datetime.UTC)
    for d in range(61):  # October is the prior window; 1 December is outside both and must be dropped
        grown = d >= 31
        for q in range(10):
            at = start + datetime.timedelta(days=d, minutes=q * 7)
            task = f"visit-{at:%Y%m%d}-{q:02d}"
            for usage in (
                {"prompt_tokens": 6500 if grown else 5500, "completion_tokens": 700, "prompt_tokens_details": {"cached_tokens": 0}},
                {"prompt_tokens": 5600 if grown else 4600, "completion_tokens": 700, "prompt_tokens_details": {"cached_tokens": 4800 if grown else 3800}},
            ):
                lines.append(
                    json.dumps(
                        {"timestamp": at.isoformat(), "model": "vendor-a/large", "usage": usage, "metadata": {"feature": "visit-notes", "task_id": task}},
                        sort_keys=True,
                    )
                )
    (OUT / "gateway.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    rows = []
    for d in range(1, 32):
        date = f"2026-10-{d:02d}"
        rows.append([date, "acme-quote-follow-up", "vendor-a/small", 5_000_000, 1_200_000, 2_500_000, 0, 9000])
        rows.append([date, "acme-search", "vendor-b/mini-1", 200_000, 20_000, 0, 0, 400])
    for d in range(1, 31):
        date = f"2026-11-{d:02d}"
        if d < 16:
            rows.append([date, "acme-quote-follow-up", "vendor-a/small", 5_000_000, 1_200_000, 2_500_000, 0, 9000])
        else:
            rows.append([date, "acme-quote-follow-up", "vendor-a/small", 4_000_000, 1_000_000, 2_400_000, 0, 7500])
            rows.append([date, "acme-quote-follow-up", "vendor-a/large", 1_000_000, 300_000, 0, 0, 1500])
        rows.append([date, "acme-search", "vendor-b/mini-1", 200_000, 20_000, 0, 0, 400])
    with (OUT / "usage.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "api_key_name", "model", "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "requests"])
        w.writerows(rows)
    with (OUT / "tasks.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["feature", "tasks", "succeeded", "start", "end", "source"])
        source = "follow-up messages sent, from the quote events table; succeeded passed the follow-up eval"
        w.writerow(["quote-follow-up", 90000, 86400, "2026-11-01", "2026-11-30", source])
        w.writerow(["quote-follow-up", 93000, 89280, "2026-10-01", "2026-10-31", source])
    with (OUT / "finance.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["line", "period", "plan", "actual"])
        w.writerow(["Model API: Vendor A", "2026-11", "", 420.00])
        w.writerow(["Model API: Vendor B", "2026-11", "", 4.20])


if __name__ == "__main__":
    main()
