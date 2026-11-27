#!/usr/bin/env python3
"""Write the cost key of the Landing Loop record, landing/<bet>.json, and leave every other key alone.

The record is shared by the Landing Loop skills, the Leader Report among them (schema landing-loop/1):

  {"schema": "landing-loop/1", "bet": "...", "brief": {"path": "...", "sha256": "..."},
   "portfolio": {...}, "spec": {...}, "evals": {...}, "cost": {...}, "landed": {...}}

This check writes only "cost". Every figure in it carries value, unit, source, window (from, to) and
as_of. It is the single owner of cost per task, tokens per task and price per token in the loop: each
sits at the top of the key as its own figure, with its budget from the brief under "budget", so eval-kit
and the Leader Report cite them and compute none. A figure that could not be computed (no task count)
is named under "not_checked" with the reason, and is absent, never estimated.

A record already holding a different brief (by sha256) is refused: the cost would be checked against
one brief and filed under another. A record with another schema is refused too.

Standard library only. Runs on Python 3.11 or later.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "landing-loop/1"
KEY = "cost"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
OWNED = ("cost_per_task", "tokens_per_task", "price_per_token")
NOT_CHECKED = "no task count for this window, so this figure was not computed. Give a task count to cost-budget-check; do not compute it elsewhere."
UNITS = {"tokens_per_task": "tokens per task", "price_per_token": "USD per token", "cost_per_task": "USD per task"}
Json = dict[str, Any]


class LandingError(ValueError):
    """A loop record that cannot be written safely."""


def figure(value: Any, unit: str, source: str, window: Json, as_of: str) -> Json:
    return {"value": value, "unit": unit, "source": source, "window": window, "as_of": as_of}


def ledger_source(result: Json, fid: str) -> str:
    row = next((r for r in result["ledger"] if r["id"] == fid), None)
    if row is None:
        raise LandingError(f"no ledger row {fid}; the cost key takes only computed figures.")
    return f"cost-budget-check {result['version']}: {row['formula']}; " + "; ".join(row["sources"])


def cost_key(result: Json, f: Json) -> Json:
    window, as_of = result["window_used"], result["as_of"]
    name = f["feature"]
    key: Json = {"tool": f"cost-budget-check {result['version']}", "budget_status": f.get("status"), "lines": {}, "gaps": list(f["gaps"])}
    for line, c in f["checks"].items():
        unit = UNITS[line]
        entry: Json = {
            "actual": figure(c["actual"], unit, ledger_source(result, f"{name}.{line}"), window, as_of),
            "budget": figure(c["budget"], unit, f"landing brief {f['brief']}" + (" (tokens per task x price per token)" if line == "cost_per_task" else ""), window, as_of),
            "against_budget": figure(c["over"], "share over budget", ledger_source(result, f"{name}.{line}.over"), window, as_of),
            "budget_status": c["status"],
        }
        if "change" in c:
            prior = result["prior_window"].split("..")
            entry["prior"] = figure(c["prior"], unit, ledger_source(result, f"{name}.prior.{line}"), {"from": prior[0], "to": prior[1]}, as_of)
            entry["change"] = figure(c["change"], "share change since the prior window", ledger_source(result, f"{name}.{line}.change"), window, as_of)
        key["lines"][line] = entry
    if "tokens_per_task" in key["lines"]:
        key["tokens_per_task"] = key["lines"]["tokens_per_task"]["actual"]
    if "price_per_token" in key["lines"]:
        key["price_per_token"] = key["lines"]["price_per_token"]["actual"]
    if "cost_per_task" in key["lines"]:
        key["cost_per_task"] = key["lines"]["cost_per_task"]["actual"]
    # The three figures this check owns in the Landing Loop. A reader cites them from here and computes none.
    key["not_checked"] = {k: NOT_CHECKED for k in OWNED if k not in key}
    key["budget"] = {k: key["lines"][k]["budget"] for k in OWNED if k in key["lines"]}
    if "cost" in f:
        key["priced_cost"] = figure(f["cost"], "USD", ledger_source(result, f"{name}.cost"), window, as_of)
    if "drift" in f:
        key["over_budget"] = figure(f["drift"], "USD", ledger_source(result, f"{name}.drift"), window, as_of)
        drivers = [d for d in result["drivers"] if d["feature"] == name]
        if drivers:
            key["driver"] = {"model": drivers[0]["model"], "over_budget": figure(drivers[0]["drift"], "USD", ledger_source(result, f"{name}.{drivers[0]['model']}.drift"), window, as_of)}
    if "tasks" in f:
        key["tasks"] = figure(f["tasks"], "tasks", f["tasks_source"], window, as_of)
    if "cost_per_success" in f:
        key["cost_per_successful_task"] = figure(f["cost_per_success"], "USD per successful task", ledger_source(result, f"{name}.cost_per_success"), window, as_of)
    return key


def write_atomic(path: Path, data: Json) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write(result: Json, folder: Path, bets: dict[str, str]) -> list[Path]:
    """Write the cost key for each briefed, checked feature. Returns the paths written."""
    if not result["window_used"]["from"]:
        raise LandingError("the usage has no dates and no --window was given, so the figures have no window. Pass --window.")
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for f in result["features"]:
        if not f["checks"]:
            continue
        slug = bets.get(f["feature"], f["feature"])
        if not SLUG.match(slug):
            raise LandingError(f'bet "{slug}" is not a slug (lower case letters, digits and hyphens). Pass --bet {f["feature"]}=<slug>.')
        path = folder / f"{slug}.json"
        record: Json = {"schema": SCHEMA, "bet": slug, "brief": {"path": f["brief_path"], "sha256": f["brief_sha256"]}}
        if path.exists():
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
                raise LandingError(f"{path} cannot be read as JSON ({e}). Fix or move it; it is never overwritten blind.") from None
            if not isinstance(record, dict) or record.get("schema") != SCHEMA:
                raise LandingError(f"{path} is not a {SCHEMA} record.")
            held = (record.get("brief") or {}).get("sha256")
            if held and held != f["brief_sha256"]:
                raise LandingError(f"{path} holds a different brief (sha256 {held[:12]}...) from {f['brief']} ({f['brief_sha256'][:12]}...). Check the same brief, or name another bet.")
            record.setdefault("brief", {"path": f["brief_path"], "sha256": f["brief_sha256"]})
        record[KEY] = cost_key(result, f)
        write_atomic(path, record)
        written.append(path)
    return written
