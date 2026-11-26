#!/usr/bin/env python3
"""Write the Acme fixture: two AI features, their landing briefs, usage, task counts, a bill and prices.

Acme is an invented company: invoicing software for trades businesses, Series C, about 400 people,
12 squads. Its AI assistant drafts quotes and chases invoices. Every figure here is illustrative.

The story the fixture tells, for November 2026:
  quote-drafter   gateway log, 10 quotes a day, two requests each. The prompt grew to 13,500 tokens
                  per task against a budget of 12,000 (stalled), but cache reads keep price per token
                  and cost per task under budget (landed).
  invoice-chaser  provider usage CSV. Tokens per task hold at budget, but from 16 November part of the
                  traffic moved to the large model, so price per token and cost per task go over
                  budget (stalled). It is the driver, on vendor-a/large.
  search-assist   a small spend with no landing brief.

Run it again after changing it; the tests read the files it writes.

Usage:
  python3 evals/make_fixtures.py
"""

from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "fixtures" / "acme"
NOTE = "Illustrative: Acme is an invented company and every figure here is made up."


def brief(problem: str, metric: str, bar: str, tokens: str, price: str, line: str) -> str:
    return f"""# {metric}

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
- **Decides the next step:** Head of Product, Acme
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "briefs").mkdir(exist_ok=True)
    (OUT / "briefs" / "quote-drafter.md").write_text(
        brief(
            "Tradespeople lose evenings writing quotes by hand, so quotes go out late.",
            "Quotes sent within a day",
            "70%",
            "12,000",
            "$0.000004",
            "model call. Line items and tax stay in fixed code; only the scope wording calls a model.",
        ),
        encoding="utf-8",
    )
    (OUT / "briefs" / "invoice-chaser.md").write_text(
        brief(
            "Overdue invoices wait weeks for a reminder, so cash comes in late.",
            "Invoices paid within 30 days",
            "60%",
            "3,000",
            "$0.0000012",
            "model call. Timing rules stay in fixed code; only the reminder wording calls a model.",
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

    # quote-drafter: one request writes the scope, a second, mostly cached, revises it.
    lines = []
    start = datetime.datetime(2026, 10, 31, 9, 0, tzinfo=datetime.UTC)
    for d in range(31):  # 31 October is outside the November window and must be dropped
        for q in range(10):
            at = start + datetime.timedelta(days=d, minutes=q * 7)
            task = f"quote-{at:%Y%m%d}-{q:02d}"
            for usage in (
                {"prompt_tokens": 6500, "completion_tokens": 700, "prompt_tokens_details": {"cached_tokens": 0}},
                {"prompt_tokens": 5600, "completion_tokens": 700, "prompt_tokens_details": {"cached_tokens": 4800}},
            ):
                lines.append(
                    json.dumps(
                        {"timestamp": at.isoformat(), "model": "vendor-a/large", "usage": usage, "metadata": {"feature": "quote-drafter", "task_id": task}},
                        sort_keys=True,
                    )
                )
    (OUT / "gateway.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    rows = []
    for d in range(1, 31):
        date = f"2026-11-{d:02d}"
        if d < 16:
            rows.append([date, "acme-invoice-chaser", "vendor-a/small", 5_000_000, 1_200_000, 2_500_000, 0, 9000])
        else:
            rows.append([date, "acme-invoice-chaser", "vendor-a/small", 4_000_000, 1_000_000, 2_400_000, 0, 7500])
            rows.append([date, "acme-invoice-chaser", "vendor-a/large", 1_000_000, 300_000, 0, 0, 1500])
        rows.append([date, "acme-search", "vendor-b/mini-1", 200_000, 20_000, 0, 0, 400])
    with (OUT / "usage.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "api_key_name", "model", "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "requests"])
        w.writerows(rows)
    with (OUT / "tasks.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["feature", "tasks", "source"])
        w.writerow(["invoice-chaser", 90000, "invoice reminders sent in November 2026, from the billing events table"])
    with (OUT / "finance.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["line", "period", "plan", "actual"])
        w.writerow(["Model API: Vendor A", "2026-11", "", 420.00])
        w.writerow(["Model API: Vendor B", "2026-11", "", 4.20])


if __name__ == "__main__":
    main()
