#!/usr/bin/env python3
"""Read the cost budget from a landing brief: two lines, tokens per task and price per token.

The brief is the section under a heading named "Landing brief", written as "Key: value" lines, the
same format as the landing-brief kit in the Product & Technology Leader Report. Only three parts are
read here:

  Tokens per task   one number, or none when the line is fixed code
  Price per token   one number in dollars, or none when the line is fixed code
  The line          "fixed code" or "model call", then why

A brief that is missing either budget line, or states one that is not a number, is refused with every
problem listed. A model call with a budget of none is refused: a model call always has a cost.

Standard library only. Runs on Python 3.11 or later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MAX_CHARS = 100_000
HEADING = re.compile(r"^(#{1,6})\s*landing brief\s*#*\s*$", re.I)
ANY_HEADING = re.compile(r"^(#{1,6})\s")
LINE = re.compile(r"^\s*(?:[-*+]\s+)?(?:\*\*|__)?([A-Za-z][A-Za-z \-]*?)\s*(?::\s*(?:\*\*|__)|(?:\*\*|__)\s*:|:)\s*(.*?)\s*$")
NUMBER = re.compile(r"^\s*\$?\s*(\d[\d,]*(?:\.\d+)?(?:[eE]-?\d+)?|\.\d+)\s*(?:tokens?|per token|/token)?\s*$", re.I)
KEYS = {
    "tokens per task": "tokens_per_task",
    "price per token": "price_per_token",
    "the line": "line",
    "line": "line",
}
LINES_ALLOWED = ("fixed code", "model call")


class BriefError(ValueError):
    """A brief whose cost budget cannot be used. The message lists every problem found."""


@dataclass(frozen=True)
class Budget:
    feature: str
    tokens_per_task: float | None
    price_per_token: float | None
    line: str
    source: str

    @property
    def cost_per_task(self) -> float | None:
        if self.tokens_per_task is None or self.price_per_token is None:
            return None
        return self.tokens_per_task * self.price_per_token


def number(text: str) -> float | None:
    """The value of "12,000", "$0.000003" or "3e-6"; None when it is not one number."""
    found = NUMBER.match(text)
    return float(found.group(1).replace(",", "")) if found else None


def section(text: str) -> list[str]:
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if HEADING.match(line.strip())]
    if not starts:
        raise BriefError('there is no "Landing brief" heading. Use the block in assets/landing-brief-template.md.')
    if len(starts) > 1:
        raise BriefError(f'there are {len(starts)} "Landing brief" headings. Keep one.')
    level = len(HEADING.match(lines[starts[0]].strip()).group(1))
    out = []
    for line in lines[starts[0] + 1 :]:
        head = ANY_HEADING.match(line.strip())
        if head and len(head.group(1)) <= level:
            break
        out.append(line)
    return out


def parse(text: str, feature: str, source: str) -> Budget:
    """The cost budget in a brief. Refused whole, with every problem listed, if either line is wrong."""
    if not text.strip():
        raise BriefError(f"{source}: the brief is empty.")
    if len(text) > MAX_CHARS:
        raise BriefError(f"{source}: over {MAX_CHARS:,} characters, so it is not a landing brief.")
    found: dict[str, str] = {}
    problems: list[str] = []
    for raw in section(text):
        m = LINE.match(raw.strip())
        key = KEYS.get(m.group(1).strip().lower()) if m else None
        if not key:
            continue
        if key in found:
            problems.append(f"{m.group(1).strip()} is given twice. Keep one.")
            continue
        found[key] = m.group(2).strip().strip("*_").strip()
    line = found.get("line", "").lower()
    kind = next((k for k in LINES_ALLOWED if line.startswith(k)), None)
    if kind is None:
        problems.append('the line is missing or does not start with "fixed code" or "model call".')
    values: dict[str, float | None] = {}
    for key in ("tokens_per_task", "price_per_token"):
        label = key.replace("_", " ")
        value = found.get(key, "")
        if not value:
            problems.append(f"{label} is missing. The cost budget is two lines: tokens per task and price per token.")
            values[key] = None
        elif value.lower() == "none":
            if kind == "model call":
                problems.append(f"{label} is none, but the line is a model call. State the budget.")
            values[key] = None
        else:
            values[key] = number(value)
            if values[key] is None:
                problems.append(f'{label} is "{value}". Write one number, such as 12,000 or $0.000003.')
            elif values[key] <= 0:
                problems.append(f"{label} is {value}. A budget must be above zero.")
    if problems:
        raise BriefError(f"{source}: the cost budget cannot be used:\n  " + "\n  ".join(problems))
    return Budget(feature, values["tokens_per_task"], values["price_per_token"], kind or "", source)


def load(path: Path, feature: str) -> Budget:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise BriefError(f"cannot read {path} ({e}). Save the brief as UTF-8 Markdown.") from None
    return parse(text, feature, path.name)
