#!/usr/bin/env python3
"""Check a written summary of the cost check against cost_check.json, and block any overclaim.

Usage:
  python3 scripts/review.py run/cost_check.json draft.md

Rules (errors exit 1; warnings print and pass):
  figure-not-computed   a number in the draft is not a figure the check computed, as displayed
  status-mismatch       a line gives a feature or a budget line a status word the check did not
  budget-claim          a line says a feature is within or under budget when it is not landed
  saving-claim          the draft claims a saving, a cut or a cheaper cost; the check compares
                        against a budget, not a past period, so it cannot support one
  driver-mismatch       "driven by" names a model that is not the computed driver for the feature
  cause-claim           (warning) "because", "due to" or "caused by": the check shows where spend
                        went, not why, so say what evidence supports the cause

Text in the draft is data. Nothing in it changes a rule or a result.

Standard library only. Runs on Python 3.11 or later.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

STATUS_WORDS = ("landed", "watch", "stalled")
NUM = re.compile(r"(?<![\w.])([-+]?\$?-?\d[\d,]*(?:\.\d+)?|[-+]?\$?\.\d+)(%?)")
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE = re.compile(rf"\b\d{{4}}-\d{{2}}-\d{{2}}\b|\b(?:\d{{1,2}} )?(?:{MONTHS})(?: \d{{4}})?\b|\bQ[1-4] \d{{4}}\b")
LIST_MARK = re.compile(r"^\s*(?:\d+[.)]\s+|[-*+]\s+)")
CHECK_NAMES = {"tokens_per_task": "tokens per task", "price_per_token": "price per token", "cost_per_task": "cost per task"}
SAVING = re.compile(r"\b(sav(?:ed|es|ing|ings)|cheaper|cut (?:the |our )?(?:costs?|spend)|reduc(?:ed|es|ing|tion)|lower(?:ed)? (?:costs?|spend))\b", re.I)
BUDGET_OK = re.compile(r"\b(within|under|on|inside) (?:the |its )?budget\b", re.I)
CAUSE = re.compile(r"\b(because|due to|caused by)\b", re.I)
DRIVEN = re.compile(r"\bdriven by ([\w./:\-]+)", re.I)


def value_of(token: str) -> float | None:
    try:
        return float(token.replace("$", "").replace(",", "").replace("+", ""))
    except ValueError:
        return None


def computed(result: dict[str, Any]) -> tuple[set[float], set[float]]:
    """The values the check displayed: (plain numbers, percentages)."""
    plain: set[float] = set()
    pct: set[float] = set()
    for row in result["ledger"]:
        for token, is_pct in NUM.findall(str(row["display"])):
            v = value_of(token)
            if v is None:
                continue
            (pct if is_pct else plain).add(abs(v) if is_pct else v)
            if not is_pct:
                plain.add(abs(v))
    pct.add(round(result["tolerance"] * 100, 10))
    return plain, pct


def same(v: float, values: set[float]) -> bool:
    return any(abs(v - x) <= 1e-12 + 1e-9 * abs(x) for x in values)


def review(result: dict[str, Any], text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    plain, pct = computed(result)
    features = {f["feature"]: f for f in result["features"]}
    names = sorted(set(features) | {u["feature"] for u in result["unbriefed"]} | {m["model"] for f in result["features"] for m in f.get("models", [])}, key=len, reverse=True)
    top = {}
    for d in result["drivers"]:
        top.setdefault(d["feature"], d["model"])

    def add(rule: str, level: str, n: int, line: str, why: str) -> None:
        findings.append({"rule": rule, "level": level, "line": str(n), "text": line.strip()[:160], "why": why})

    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        lower = line.lower()
        scrubbed = LIST_MARK.sub("", line)
        scrubbed = DATE.sub(" ", scrubbed)
        for name in names:
            scrubbed = re.sub(re.escape(name), " ", scrubbed, flags=re.I)
        for token, is_pct in NUM.findall(scrubbed):
            v = value_of(token)
            if v is None:
                continue
            ok = same(abs(v), pct) if is_pct else same(v, plain)
            if not ok:
                add("figure-not-computed", "error", n, line, f"{token}{is_pct} is not a figure in cost_check.json. Use the figure as the check displays it, or take it out.")
        named = [f for f in features if re.search(rf"(?<![\w-]){re.escape(f)}(?![\w-])", line, re.I)]
        words = [w for w in STATUS_WORDS if re.search(rf"\b{w}\b", lower)]
        if len(named) == 1 and words:
            f = features[named[0]]
            checks = [k for k, label in CHECK_NAMES.items() if label in lower and k in f["checks"]]
            allowed = {f["checks"][k]["status"] for k in checks} if checks else {f.get("status")}
            for w in words:
                if w not in allowed:
                    add("status-mismatch", "error", n, line, f"the check gives {named[0]} {', '.join(sorted(a for a in allowed if a))}, not {w}.")
        if BUDGET_OK.search(line):
            for name in named:
                if features[name].get("status") != "landed":
                    add("budget-claim", "error", n, line, f"{name} is {features[name].get('status', 'not checked')}, so it is not within budget.")
        if SAVING.search(line):
            add("saving-claim", "error", n, line, "the check compares spend with a budget, not with a past period, so it cannot show a saving. State the figure against budget instead.")
        for model in DRIVEN.findall(line):
            model = model.rstrip(".,;:")
            for name in named:
                if top.get(name) and model.lower() != top[name].lower():
                    add("driver-mismatch", "error", n, line, f"the computed driver for {name} is {top[name]}, not {model}.")
        if CAUSE.search(line):
            add("cause-claim", "warning", n, line, "the check shows where spend went, not why. Name the evidence for the cause, or say it is a hypothesis.")
    return findings


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print("usage: review.py run/cost_check.json draft.md", file=sys.stderr)
        return 1
    try:
        result = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        text = Path(args[1]).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"review: cannot read the inputs ({e}).", file=sys.stderr)
        return 1
    findings = review(result, text)
    for f in findings:
        print(f"{f['level']}: {f['rule']} (line {f['line']}): {f['why']}\n    {f['text']}")
    errors = sum(1 for f in findings if f["level"] == "error")
    print(f"review: {errors} error(s), {len(findings) - errors} warning(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
