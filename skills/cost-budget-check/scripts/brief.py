#!/usr/bin/env python3
"""Read the cost budget from a landing brief: two lines, tokens per task and price per token.

The brief is parsed by the Leader Report's own landing_brief.py, vendored unchanged in vendor/ (see
vendor/VENDORED.md), so every skill in the Landing Loop reads one format the same way. A brief with any
missing, unknown or unreadable part is refused whole, with every problem listed. On top of that this
check refuses a budget of zero, since a model call always costs something.

The input is a Markdown file holding the project description, or the JSON Linear returns for one
project.

Standard library only. Runs on Python 3.11 or later.
"""

from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))

import landing_brief  # noqa: E402  (vendored, see vendor/VENDORED.md)


class BriefError(ValueError):
    """A brief whose cost budget cannot be used. The message lists every problem found."""


@dataclass(frozen=True)
class Budget:
    feature: str
    tokens_per_task: float | None
    price_per_token: float | None
    line: str
    source: str
    path: str = ""
    sha256: str = ""
    metric: str = ""
    title: str = ""
    decides: str = ""

    @property
    def cost_per_task(self) -> float | None:
        if self.tokens_per_task is None or self.price_per_token is None:
            return None
        return self.tokens_per_task * self.price_per_token


def title_of(text: str) -> str:
    """The brief's first "# " heading, which pages print instead of the feature's slug. Empty when there is none."""
    m = re.search(r"^#[ \t]+(.+?)[ \t#]*$", text, re.M)
    return m.group(1).strip() if m else ""


def parse(text: str, feature: str, source: str) -> Budget:
    """The cost budget in a brief. Refused whole, with every problem listed, if any part is wrong."""
    try:
        b = landing_brief.parse(text)
    except landing_brief.BriefError as e:
        raise BriefError(f"{source}: {e}") from None
    zero = [k.replace("_", " ") for k in ("tokens_per_task", "price_per_token") if getattr(b, k) is not None and getattr(b, k) <= 0]
    if zero:
        raise BriefError(f"{source}: the cost budget cannot be used:\n  " + "\n  ".join(f"{k} must be above zero." for k in zero))
    return Budget(feature, b.tokens_per_task, b.price_per_token, b.line, source, metric=b.metric, title=title_of(text), decides=b.decides)


def load(path: Path, feature: str) -> Budget:
    try:
        text = landing_brief.description_of(path)
    except landing_brief.BriefError as e:
        raise BriefError(str(e)) from None
    b = parse(text, feature, path.name)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return Budget(b.feature, b.tokens_per_task, b.price_per_token, b.line, b.source, str(path), digest, b.metric, b.title, b.decides)
