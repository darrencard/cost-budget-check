#!/usr/bin/env python3
"""Write the inputs of the committed sample: Acme's quote-drafting bet, followed through the Landing Loop.

Acme is an invented company (invoicing software for trades businesses). Every figure is illustrative.
The brief is the canonical one in examples/acme/briefs/quote-drafting.md, copied unchanged from the
landing-loop repository: 9,000 tokens per task at $0.000003 a token.

The story, two weeks against the two before:
  18 to 31 October   20 quotes a day on vendor-a/large, about 8,400 tokens each. Within budget.
  1 to 14 November   the prompt now carries a longer price-book excerpt, so each quote uses about 10,300
                     tokens (tokens per task stalled). From 8 November, one quote in five for large jobs
                     goes to vendor-a/xl, which costs twice as much a token, so cost per task drifts over
                     budget and the driver is vendor-a/xl.

Usage is an AI gateway log, one request per quote, with the quote id as the task id. Prices are
illustrative, not any provider's list price.

Usage:
  python3 evals/make_sample.py
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "examples" / "acme" / "inputs"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pricing = {
        "source": "Illustrative prices for the Acme sample. Not any provider's list price.",
        "retrieved": "2026-10-15",
        "currency": "USD",
        "illustrative": True,
        "models": [
            {"match": "vendor-a/large", "input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
            {"match": "vendor-a/xl", "input": 6.00, "output": 30.00, "cache_read": 0.60, "cache_write": 7.50},
        ],
    }
    (OUT / "pricing.json").write_text(json.dumps(pricing, indent=2) + "\n", encoding="utf-8")
    lines = []
    first = datetime.date(2026, 10, 18)
    for d in range(28):
        day = first + datetime.timedelta(days=d)
        grown = day >= datetime.date(2026, 11, 1)
        for q in range(20):
            at = datetime.datetime(day.year, day.month, day.day, 8, 0, tzinfo=datetime.timezone.utc) + datetime.timedelta(minutes=q * 23)  # noqa: UP017  (runs on 3.9)
            xl = day >= datetime.date(2026, 11, 8) and q % 5 == 0
            usage = (
                {"input_tokens": 2600, "output_tokens": 1400, "cache_read_input_tokens": 6300, "cache_creation_input_tokens": 0}
                if grown
                else {"input_tokens": 2000, "output_tokens": 900, "cache_read_input_tokens": 5500, "cache_creation_input_tokens": 0}
            )
            record = {
                "timestamp": at.isoformat(),
                "model": "vendor-a/xl" if xl else "vendor-a/large",
                "usage": usage,
                "metadata": {"feature": "quote-drafting", "task_id": f"quote-{day:%Y%m%d}-{q:02d}"},
            }
            lines.append(json.dumps(record, sort_keys=True))
    (OUT / "gateway.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
