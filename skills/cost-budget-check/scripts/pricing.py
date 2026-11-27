#!/usr/bin/env python3
"""Load a pricing table that carries its own source and date, and price token counts with it.

The table is JSON (see assets/pricing-template.json):

  {"source": "where these prices come from (a URL or the contract)",
   "retrieved": "YYYY-MM-DD",
   "currency": "USD",
   "models": [{"match": "provider-a/large", "input": 3.00, "output": 15.00,
               "cache_read": 0.30, "cache_write": 3.75}]}

Prices are dollars per million tokens. Each of the four token types is priced separately, so cache
reads never bill at the input rate. A match ending in * matches any model id with that prefix; the
longest match wins. A model no row matches is refused by name. There is no default rate: a guessed
price would make every figure after it wrong.

Standard library only. Runs on Python 3.11 or later.
"""

from __future__ import annotations

import datetime
import json
import math
from dataclasses import dataclass
from pathlib import Path

TOKEN_TYPES = ("input", "output", "cache_read", "cache_write")
# One-hour cache writes bill above five-minute ones on some providers. Priced only where a table gives it.
OPTIONAL_TYPES = ("cache_write_1h",)
ALL_TOKEN_TYPES = TOKEN_TYPES + OPTIONAL_TYPES
STALE_DAYS = 90
PER = 1_000_000


class PricingError(ValueError):
    """A pricing table that cannot be used. The message lists every problem found."""


@dataclass(frozen=True)
class Rate:
    match: str
    input: float
    output: float
    cache_read: float
    cache_write: float
    cache_write_1h: float | None = None

    def cost(self, tokens: dict[str, int]) -> float:
        if tokens.get("cache_write_1h") and self.cache_write_1h is None:
            raise PricingError(f"{self.match} has one-hour cache writes in the usage but no cache_write_1h price. Add it from the provider's pricing.")
        parts = [tokens.get(t, 0) * getattr(self, t) for t in TOKEN_TYPES] + [tokens.get("cache_write_1h", 0) * (self.cache_write_1h or 0)]
        return math.fsum(parts) / PER  # fsum: the same total on every Python version


@dataclass(frozen=True)
class Pricing:
    source: str
    retrieved: datetime.date
    currency: str
    rates: tuple[Rate, ...]
    file: str
    illustrative: bool

    def rate_for(self, model: str) -> Rate | None:
        m = model.strip().lower()
        best: Rate | None = None
        for r in self.rates:
            key = r.match.lower()
            hit = m.startswith(key[:-1]) if key.endswith("*") else m == key
            if hit and (best is None or len(key) > len(best.match)):
                best = r
        return best

    def age_days(self, as_of: datetime.date) -> int:
        return (as_of - self.retrieved).days

    def stale(self, as_of: datetime.date) -> bool:
        return self.age_days(as_of) > STALE_DAYS


def load(path: Path) -> Pricing:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        raise PricingError(f"cannot read {path} ({e}).") from None
    except json.JSONDecodeError as e:
        raise PricingError(f"{path.name} is not valid JSON ({e.msg}, line {e.lineno}).") from None
    if not isinstance(data, dict):
        raise PricingError(f"{path.name} must be one JSON object with source, retrieved, currency and models.")
    problems: list[str] = []
    source = str(data.get("source") or "").strip()
    if not source:
        problems.append("source is missing. Say where the prices come from: the provider's pricing page URL or your contract.")
    retrieved = None
    try:
        retrieved = datetime.date.fromisoformat(str(data.get("retrieved") or ""))
    except ValueError:
        problems.append("retrieved is missing or not YYYY-MM-DD. Date the prices so a reader can tell if they are current.")
    currency = str(data.get("currency") or "").strip().upper()
    if not currency:
        problems.append("currency is missing. Write the currency the prices are in, such as USD.")
    rows = data.get("models")
    rates: list[Rate] = []
    if not isinstance(rows, list) or not rows:
        problems.append("models is missing or empty.")
        rows = []
    seen: set[str] = set()
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not str(row.get("match") or "").strip():
            problems.append(f"models row {i} has no match.")
            continue
        match = str(row["match"]).strip()
        if match.lower() in seen:
            problems.append(f"{match} is priced twice. Keep one row.")
            continue
        seen.add(match.lower())
        values = {}
        for t in TOKEN_TYPES:
            v = row.get(t)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                problems.append(f"{match}: {t} is {v!r}. Give a price per million tokens, 0 or more; every token type is priced separately.")
            else:
                values[t] = float(v)
        hour = row.get("cache_write_1h")
        if hour is not None and (isinstance(hour, bool) or not isinstance(hour, (int, float)) or hour < 0):
            problems.append(f"{match}: cache_write_1h is {hour!r}. Give a price per million tokens, or leave it out.")
        elif hour is not None:
            values["cache_write_1h"] = float(hour)
        if all(t in values for t in TOKEN_TYPES):
            rates.append(Rate(match=match, **values))
    if problems:
        raise PricingError(f"{path.name}: the pricing table cannot be used:\n  " + "\n  ".join(problems))
    assert retrieved is not None  # noqa: S101  (narrowed by the checks above)
    return Pricing(source, retrieved, currency, tuple(rates), path.name, bool(data.get("illustrative")))
